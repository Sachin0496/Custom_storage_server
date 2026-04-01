import json
import uuid
from datetime import datetime
from pathlib import Path
import os
import stat

SHARES_FILE = Path("shares.json")


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


def _safe_resolve(share_path: str, subpath: str) -> Path | None:
    root = Path(share_path).resolve()
    
    # Strip leading slashes to prevent absolute path injection via subpath
    subpath = subpath.lstrip("/\\")
    
    target = (root / subpath).resolve()
    
    # Check if target is still within root
    try:
        target.relative_to(root)
        return target
    except ValueError:
        return None  # Path escaped the root directory


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
            # Skip hidden files and symlinks that might break out
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
        return None # Permission denied etc.
    
    # Sort folders first, then files
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
