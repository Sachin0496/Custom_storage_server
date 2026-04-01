import json
import os
import base64
import io
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import qrcode
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Request, Query
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import auth
import storage as store
import shares
from discovery import start_mdns, stop_mdns, get_lan_ip, get_all_ips

# ── Config ─────────────────────────────────────────────────────────────────────
with open("config.json") as f:
    CONFIG = json.load(f)

PORT = CONFIG.get("port", 8080)
STORAGE_PATH = Path(CONFIG.get("storage_path", "./storage"))
APP_NAME = CONFIG.get("app_name", "LAN Store")
DOWNLOAD_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB chunks for faster LAN transfers

# ── App ────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_mdns(PORT, APP_NAME)
    ips = get_all_ips()
    print(f"\n{'='*50}")
    print(f"  {APP_NAME} is running!")
    print(f"  Local:   http://localhost:{PORT}")
    for ip in ips:
        print(f"  Network: http://{ip}:{PORT}")
    print(f"{'='*50}\n")
    yield
    stop_mdns()

app = FastAPI(title=APP_NAME, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE_PATH.mkdir(parents=True, exist_ok=True)


# ── Auth helpers ───────────────────────────────────────────────────────────────
def _parse_token(
    authorization: Optional[str] = Header(None),
    auth_q: Optional[str] = Query(None, alias="auth"),
) -> tuple[str, str]:
    token_blob = None
    if authorization and authorization.startswith("Bearer "):
        token_blob = authorization.split(" ", 1)[1]
    elif auth_q:
        token_blob = auth_q

    if not token_blob:
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    parts = token_blob.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=401, detail="Token format: username:token")
    return parts[0], parts[1]


def _require_user(
    authorization: Optional[str] = Header(None),
    auth_q: Optional[str] = Query(None, alias="auth"),
) -> dict:
    username, token = _parse_token(authorization, auth_q)
    user = auth.authenticate(username, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user["token"] = token
    return user


def _iter_file_chunks(path: Path, chunk_size: int = DOWNLOAD_CHUNK_SIZE):
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


def _stream_download(path: Path, original_name: str) -> StreamingResponse:
    size = path.stat().st_size
    quoted_name = quote(original_name)
    disposition = f"attachment; filename*=UTF-8''{quoted_name}"
    return StreamingResponse(
        _iter_file_chunks(path),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(size),
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-store",
        },
    )


def _require_admin(authorization: Optional[str] = Header(None)) -> dict:
    user = _require_user(authorization)
    if not auth.is_admin_for_current_host(user):
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ── Pydantic models ────────────────────────────────────────────────────────────
class EnrollRequest(BaseModel):
    username: str

class LoginRequest(BaseModel):
    username: str
    token: str

class UpdateUserRequest(BaseModel):
    permissions: Optional[dict] = None
    role: Optional[str] = None

class AddShareRequest(BaseModel):
    name: str
    path: str


# ── Setup / Status ─────────────────────────────────────────────────────────────
@app.get("/api/status")
def status():
    ips = get_all_ips()
    return {
        "setup_done": auth.is_setup_done(),
        "app_name": APP_NAME,
        "lan_ips": ips,
        "primary_ip": get_lan_ip(),
        "port": PORT,
        "storage": store.storage_stats(STORAGE_PATH),
        "shares": shares.shares_stats(),
    }


@app.get("/api/qr")
def get_qr():
    """Return a QR code PNG (base64) for the LAN URL."""
    ip = get_lan_ip()
    url = f"http://{ip}:{PORT}"
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"url": url, "qr_base64": b64}


# ── Auth routes ────────────────────────────────────────────────────────────────
@app.post("/api/enroll")
def enroll(req: EnrollRequest):
    username = req.username.strip()
    if not username or len(username) < 2:
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters")
    result = auth.enroll(username)
    if result is None:
        raise HTTPException(status_code=409, detail="Username already taken")
    # Return composite token: username:raw_token
    result["bearer"] = f"{result['username']}:{result['token']}"
    return result


@app.post("/api/login")
def login(req: LoginRequest):
    user = auth.authenticate(req.username, req.token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or token")
    user["bearer"] = f"{user['username']}:{req.token}"
    return user


@app.get("/api/me")
def me(user: dict = Depends(_require_user)):
    return user


# ── File routes ────────────────────────────────────────────────────────────────
@app.get("/api/files")
def list_files(user: dict = Depends(_require_user)):
    if not user["permissions"].get("download"):
        raise HTTPException(status_code=403, detail="No download permission")
    return store.list_files()


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(_require_user),
):
    if not user["permissions"].get("upload"):
        raise HTTPException(status_code=403, detail="No upload permission")
    result = store.save_file(file, user["username"], STORAGE_PATH)
    return result


@app.get("/api/download/{file_id}")
def download_file(file_id: str, user: dict = Depends(_require_user)):
    if not user["permissions"].get("download"):
        raise HTTPException(status_code=403, detail="No download permission")
    result = store.get_file(file_id, STORAGE_PATH)
    if not result:
        raise HTTPException(status_code=404, detail="File not found")
    path, original_name = result
    return _stream_download(path, original_name)


@app.delete("/api/files/{file_id}")
def delete_file(file_id: str, user: dict = Depends(_require_user)):
    files = store.list_files()
    target = next((f for f in files if f["id"] == file_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="File not found")
    is_owner = target["owner"] == user["username"]
    can_delete = user["permissions"].get("delete") or is_owner
    if not can_delete:
        raise HTTPException(status_code=403, detail="No delete permission")
    store.delete_file(file_id, STORAGE_PATH)
    return {"ok": True}


# ── Share routes ───────────────────────────────────────────────────────────────
@app.get("/api/shares")
def get_shares(user: dict = Depends(_require_user)):
    if not user["permissions"].get("download"):
        raise HTTPException(status_code=403, detail="No download permission")
    return shares.list_shares()


@app.get("/api/shares/{share_id}/browse")
def browse_share(share_id: str, path: str = "", user: dict = Depends(_require_user)):
    if not user["permissions"].get("download"):
        raise HTTPException(status_code=403, detail="No download permission")
    items = shares.list_share_dir(share_id, path)
    if items is None:
        raise HTTPException(status_code=404, detail="Directory not found or access denied")
    return items


@app.get("/api/shares/{share_id}/download")
def download_share_file(share_id: str, path: str, user: dict = Depends(_require_user)):
    if not user["permissions"].get("download"):
        raise HTTPException(status_code=403, detail="No download permission")
    result = shares.get_share_file(share_id, path)
    if not result:
        raise HTTPException(status_code=404, detail="File not found or access denied")
    
    file_path, original_name = result
    return _stream_download(file_path, original_name)


@app.post("/api/shares/{share_id}/mkdir")
def create_share_folder(share_id: str, path: str, name: str, user: dict = Depends(_require_user)):
    if not user["permissions"].get("upload"):
        raise HTTPException(status_code=403, detail="No upload permission")
    result = shares.create_share_dir(share_id, path, name)
    if result == "PERMISSION_DENIED":
        raise HTTPException(status_code=403, detail="Server has no write access to this drive path. Start with start.bat (Run as Administrator) or remap to a writable folder.")
    if result is not True:
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True}


@app.delete("/api/shares/{share_id}/item")
def delete_share_item(share_id: str, path: str, user: dict = Depends(_require_user)):
    if not user["permissions"].get("delete") and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="No delete permission")
    result = shares.delete_share_item(share_id, path)
    if result == "PERMISSION_DENIED":
        raise HTTPException(status_code=403, detail="Server has no delete access for this item. Start with start.bat (Run as Administrator) so ACL/ownership can be fixed.")
    if result == "FILE_IN_USE":
        raise HTTPException(status_code=409, detail="Item is in use by another process")
    if result is not True:
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True}


@app.post("/api/shares/{share_id}/upload")
async def upload_share_file(
    share_id: str, 
    path: str, 
    overwrite: bool = False,
    file: UploadFile = File(...), 
    user: dict = Depends(_require_user)
):
    if not user["permissions"].get("upload"):
        raise HTTPException(status_code=403, detail="No upload permission")
    
    result = shares.upload_share_file(share_id, path, file, file.filename, overwrite)
    if result == "FILE_EXISTS":
        raise HTTPException(status_code=409, detail="File already exists")
    elif result == "FILE_IN_USE":
        raise HTTPException(status_code=409, detail="Target file is currently in use")
    elif result == "PERMISSION_DENIED":
        raise HTTPException(status_code=403, detail="Server has no write access to this drive path. Start with start.bat (Run as Administrator) or remap to a writable folder.")
    elif result is not True:
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True}


# ── Admin routes ───────────────────────────────────────────────────────────────
@app.get("/api/admin/users")
def admin_list_users(admin: dict = Depends(_require_admin)):
    return auth.get_all_users()


@app.patch("/api/admin/users/{username}")
def admin_update_user(
    username: str,
    req: UpdateUserRequest,
    admin: dict = Depends(_require_admin),
):
    if not auth.update_user(username, req.dict(exclude_none=True)):
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@app.delete("/api/admin/users/{username}")
def admin_remove_user(username: str, admin: dict = Depends(_require_admin)):
    if username == admin["username"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    if not auth.remove_user(username):
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@app.post("/api/admin/shares")
def admin_add_share(
    req: AddShareRequest,
    admin: dict = Depends(_require_admin),
):
    result = shares.add_share(req.name, req.path)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid path or directory does not exist")
    return result


@app.delete("/api/admin/shares/{share_id}")
def admin_remove_share(share_id: str, admin: dict = Depends(_require_admin)):
    if not shares.remove_share(share_id):
        raise HTTPException(status_code=404, detail="Share not found")
    return {"ok": True}


# ── Serve frontend ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
@app.get("/{full_path:path}", response_class=HTMLResponse)
def serve_spa(full_path: str = ""):
    index = Path("static/index.html")
    if index.exists():
        return FileResponse(path=str(index), media_type="text/html; charset=utf-8")
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=500)


# ── Lifecycle ──────────────────────────────────────────────────────────────────
# The lifespan context manager handles both startup and shutdown.


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)
