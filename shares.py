import json
import uuid
import shutil
import stat
import subprocess
import getpass
from datetime import datetime
from pathlib import Path
import os

SHARES_FILE = Path("shares.json")
COPY_BUFFER_SIZE = 8 * 1024 * 1024  # 8 MiB chunks for better throughput


def _make_writable(path_str: str):
    try:
        os.chmod(path_str, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _windows_grant_full_access(path: Path, recursive: bool = False):
    """Best-effort ACL grant for current user on Windows."""
    if os.name != "nt":
        return
    user = os.getenv("USERNAME") or getpass.getuser()
    if not user:
        return
    if not path.exists():
        return

    # Directory permissions should propagate to children.
    is_dir = path.is_dir()
    user_perm = f"{user}:(OI)(CI)F" if is_dir else f"{user}:F"
    everyone_perm = "Everyone:(OI)(CI)F" if is_dir else "Everyone:F"
    cmd = ["icacls", str(path), "/inheritance:e", "/grant", user_perm, everyone_perm, "/C", "/Q"]
    if recursive and path.is_dir():
        cmd.append("/T")
    try:
        subprocess.run(cmd, check=False, capture_output=True, text=True)
    except OSError:
        pass


def _windows_take_ownership(path: Path, recursive: bool = False):
    """Best-effort ownership takeover to unblock permission-denied deletes."""
    if os.name != "nt" or not path.exists():
        return
    cmd = ["takeown", "/F", str(path)]
    if recursive and path.is_dir():
        cmd.extend(["/R", "/D", "Y"])
    try:
        subprocess.run(cmd, check=False, capture_output=True, text=True)
    except OSError:
        pass


def _windows_clear_attributes(path: Path, recursive: bool = False):
    """Remove read-only/system/hidden attributes that can block deletes on Windows."""
    if os.name != "nt" or not path.exists():
        return
    cmd = ["attrib", "-R", "-S", "-H", str(path)]
    if recursive and path.is_dir():
        cmd.extend(["/S", "/D"])
    try:
        subprocess.run(cmd, check=False, capture_output=True, text=True)
    except OSError:
        pass


def _can_write_dir(path: Path) -> bool:
    return path.exists() and path.is_dir() and os.access(path, os.W_OK)


def _ensure_share_root_access(root: Path) -> bool:
    """Best-effort to ensure server process can create/delete under share root."""
    if _can_write_dir(root):
        return True
    _windows_take_ownership(root, recursive=True)
    _windows_grant_full_access(root, recursive=True)
    _windows_clear_attributes(root, recursive=True)
    return _can_write_dir(root)


def _rmtree_force(path: Path):
    def _onerror(func, path_str, exc_info):
        _make_writable(path_str)
        func(path_str)

    shutil.rmtree(path, onerror=_onerror)


def _load() -> dict:
    if not SHARES_FILE.exists():
        return {}
    with open(SHARES_FILE) as f:
        return json.load(f)


def _save(data: dict):
    with open(SHARES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_share(name: str, path: str) -> dict | None:
    p = Path(path).resolve()
    if not p.exists() or not p.is_dir():
        return None  # Invalid path
    # Ensure the server user can manage files inside this mapped drive.
    _windows_grant_full_access(p, recursive=True)
    _windows_clear_attributes(p, recursive=True)
    
    shares = _load()
    share_id = str(uuid.uuid4())
    entry = {
        "id": share_id,
        "name": name,
        "path": str(p),
        "created_at": datetime.utcnow().isoformat()
    }
    shares[share_id] = entry
    _save(shares)
    return entry


def remove_share(share_id: str) -> bool:
    shares = _load()
    if share_id in shares:
        del shares[share_id]
        _save(shares)
        return True
    return False


def list_shares() -> list:
    shares = _load()
    return list(shares.values())


def shares_stats() -> dict:
    """Aggregate statistics across mapped drives."""
    shares = _load()
    file_count = 0
    total_bytes = 0
    reachable_shares = 0

    for entry in shares.values():
        root = Path(entry.get("path", "")).resolve()
        if not root.exists() or not root.is_dir():
            continue
        reachable_shares += 1
        try:
            for p in root.rglob("*"):
                try:
                    if p.is_file():
                        st = p.stat()
                        file_count += 1
                        total_bytes += st.st_size
                except (OSError, ValueError):
                    pass
        except OSError:
            pass

    return {
        "mapped_drives": len(shares),
        "reachable_drives": reachable_shares,
        "file_count": file_count,
        "total_bytes": total_bytes,
    }


def _safe_resolve(share_path: str, subpath: str) -> Path | None:
    root = Path(share_path).resolve()
    subpath = subpath.lstrip("/\\")
    
    target = (root / subpath).resolve()
    
    try:
        target.relative_to(root)
        return target
    except ValueError:
        return None  


def _safe_resolve_new_item(share_path: str, subpath: str, name: str) -> Path | None:
    root = Path(share_path).resolve()
    subpath = subpath.lstrip("/\\")
    
    parent = (root / subpath).resolve()
    try:
        parent.relative_to(root)
    except ValueError:
        return None
        
    if not parent.exists() or not parent.is_dir():
        return None
        
    return parent / name


def list_share_dir(share_id: str, subpath: str = "") -> list | None:
    shares = _load()
    if share_id not in shares:
        return None

    share = shares[share_id]
    target = _safe_resolve(share["path"], subpath)
    if not target or not target.exists() or not target.is_dir():
        return None

    items = []
    try:
        for p in target.iterdir():
            if p.name.startswith("."):
                continue
            try:
                st = p.stat()
                is_dir = p.is_dir()
                items.append({
                    "name": p.name,
                    "type": "dir" if is_dir else "file",
                    "size": st.st_size if not is_dir else 0,
                    "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat()
                })
            except (OSError, ValueError):
                pass
    except OSError:
        return None 
    
    items.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
    return items


def get_share_file(share_id: str, subpath: str) -> tuple[Path, str] | None:
    shares = _load()
    if share_id not in shares:
        return None
    share = shares[share_id]
    target = _safe_resolve(share["path"], subpath)
    
    if not target or not target.exists() or not target.is_file():
        return None

    return target, target.name


def create_share_dir(share_id: str, parent_subpath: str, new_dir_name: str) -> bool | str:
    """Returns True if created, string error message if failed."""
    shares = _load()
    if share_id not in shares:
        return "Share not found"
        
    share_root = Path(shares[share_id]["path"]).resolve()
    if not _ensure_share_root_access(share_root):
        return "PERMISSION_DENIED"

    target = _safe_resolve_new_item(str(share_root), parent_subpath, new_dir_name)
    if not target:
        return "Invalid path"
        
    if target.exists():
        return "Directory already exists"
        
    try:
        target.mkdir()
        return True
    except PermissionError:
        _windows_take_ownership(target.parent, recursive=False)
        _windows_grant_full_access(target.parent, recursive=False)
        try:
            target.mkdir()
            return True
        except PermissionError:
            return "PERMISSION_DENIED"
    except OSError as e:
        return str(e)


def delete_share_item(share_id: str, subpath: str) -> bool | str:
    """Returns True if deleted, string error message if failed."""
    shares = _load()
    if share_id not in shares:
        return "Share not found"
        
    share_root = Path(shares[share_id]["path"]).resolve()
    _ensure_share_root_access(share_root)

    target = _safe_resolve(str(share_root), subpath)
    if not target or not target.exists():
        return "Item not found or invalid path"
        
    # Prevent deleting the root share itself!
    if target == share_root:
        return "Cannot delete the root mapped drive directory"
        
    try:
        if target.is_dir():
            _windows_clear_attributes(target, recursive=True)
            _rmtree_force(target)
        else:
            try:
                _windows_clear_attributes(target, recursive=False)
                target.unlink()
            except PermissionError:
                _make_writable(str(target))
                _windows_clear_attributes(target, recursive=False)
                target.unlink()
        return True
    except PermissionError:
        _windows_take_ownership(target, recursive=target.is_dir())
        _windows_grant_full_access(target, recursive=target.is_dir())
        _windows_clear_attributes(target, recursive=target.is_dir())
        _windows_grant_full_access(target.parent, recursive=False)
        try:
            if target.is_dir():
                _rmtree_force(target)
            else:
                _make_writable(str(target))
                _windows_clear_attributes(target, recursive=False)
                target.unlink()
            return True
        except PermissionError as e2:
            if getattr(e2, "winerror", None) == 32:
                return "FILE_IN_USE"
            return "PERMISSION_DENIED"
    except OSError as e:
        if getattr(e, "winerror", None) == 5:
            _windows_take_ownership(target, recursive=target.is_dir())
            _windows_grant_full_access(target, recursive=target.is_dir())
            _windows_clear_attributes(target, recursive=target.is_dir())
            _windows_grant_full_access(target.parent, recursive=False)
            try:
                if target.is_dir():
                    _rmtree_force(target)
                else:
                    _make_writable(str(target))
                    _windows_clear_attributes(target, recursive=False)
                    target.unlink()
                return True
            except PermissionError as e2:
                if getattr(e2, "winerror", None) == 32:
                    return "FILE_IN_USE"
                return "PERMISSION_DENIED"
        if getattr(e, "winerror", None) == 32:
            return "FILE_IN_USE"
        return str(e)


def upload_share_file(share_id: str, parent_subpath: str, file_obj, filename: str, overwrite: bool) -> bool | str:
    """Returns True if uploaded, string error message if failed."""
    shares = _load()
    if share_id not in shares:
        return "Share not found"
        
    share_root = Path(shares[share_id]["path"]).resolve()
    if not _ensure_share_root_access(share_root):
        return "PERMISSION_DENIED"

    target = _safe_resolve_new_item(str(share_root), parent_subpath, filename)
    if not target:
        return "Invalid path"
        
    if target.exists() and not overwrite:
        return "FILE_EXISTS"
        
    try:
        with open(target, "wb") as out:
            shutil.copyfileobj(file_obj.file, out, length=COPY_BUFFER_SIZE)
        return True
    except PermissionError:
        _windows_take_ownership(target.parent, recursive=False)
        _windows_grant_full_access(target.parent, recursive=False)
        _windows_clear_attributes(target.parent, recursive=False)
        if target.exists():
            _windows_take_ownership(target, recursive=False)
            _windows_grant_full_access(target, recursive=False)
            _windows_clear_attributes(target, recursive=False)
            _make_writable(str(target))
        try:
            with open(target, "wb") as out:
                shutil.copyfileobj(file_obj.file, out, length=COPY_BUFFER_SIZE)
            return True
        except PermissionError as e2:
            if getattr(e2, "winerror", None) == 32:
                return "FILE_IN_USE"
            return "PERMISSION_DENIED"
    except OSError as e:
        return str(e)

