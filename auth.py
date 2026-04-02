import json
import hashlib
import secrets
import os
import socket
from pathlib import Path
from datetime import datetime

USERS_FILE = Path("users.json")


def _load() -> dict:
    if not USERS_FILE.exists():
        return {}
    with open(USERS_FILE) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}

    changed = False
    for user in data.values():
        if isinstance(user, dict) and "token" not in user:
            # Backfill field so users.json always contains token + hash.
            user["token"] = None
            changed = True

    if changed:
        _save(data)
    return data


def _find_user_key(users: dict, username: str) -> str | None:
    """Case-insensitive username lookup. Returns the stored key or None."""
    for key in users:
        if key.lower() == username.lower():
            return key
    return None


def _save(data: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _host_id() -> str:
    # Allow override for advanced deployments; default to hostname.
    return os.getenv("LANSTORE_HOST_ID", socket.gethostname()).strip().lower()


def _is_local_admin_record(user: dict) -> bool:
    return user.get("role") == "admin" and user.get("host_id") == _host_id()


def _demote_other_admins(users: dict, keep_username: str):
    for username, user in users.items():
        if username == keep_username:
            continue
        if user.get("role") == "admin":
            user["role"] = "user"
            perms = user.get("permissions") or {}
            perms["delete"] = False
            user["permissions"] = perms
            user.pop("host_id", None)


def is_setup_done() -> bool:
    users = _load()
    return any(_is_local_admin_record(u) for u in users.values())


def enroll(username: str) -> dict | None:
    """Register a new user. Returns token dict or None if username taken."""
    users = _load()
    setup_done = is_setup_done()
    # Case-insensitive check for existing user
    stored_key = _find_user_key(users, username)
    existing = users.get(stored_key) if stored_key else None
    if existing and setup_done:
        return None  # already exists once local setup is done
    # Use stored key if exists (preserves original casing)
    if stored_key:
        username = stored_key

    token = secrets.token_urlsafe(32)
    role = "admin" if not setup_done else "user"
    if role == "admin":
        _demote_other_admins(users, username)

    previous = existing or {}
    perms = previous.get("permissions") or {}
    if role == "admin":
        perms = {"upload": True, "download": True, "delete": True}
    else:
        perms = {
            "upload": perms.get("upload", True),
            "download": perms.get("download", True),
            "delete": perms.get("delete", False),
        }

    users[username] = {
        "token": token,
        "token_hash": _hash(token),
        "role": role,
        "permissions": perms,
        "enrolled_at": previous.get("enrolled_at", datetime.utcnow().isoformat()),
        "last_seen": datetime.utcnow().isoformat(),
    }
    if role == "admin":
        users[username]["host_id"] = _host_id()
    else:
        users[username].pop("host_id", None)

    _save(users)
    return {"username": username, "token": token, "role": role}


def authenticate(username: str, token: str) -> dict | None:
    """Validate credentials, update last_seen. Returns user record or None."""
    users = _load()
    # Case-insensitive username lookup
    stored_key = _find_user_key(users, username)
    if not stored_key:
        return None
    username = stored_key
    user = users[username]
    if user["token_hash"] != _hash(token):
        return None
    # Keep plaintext token in users.json for account recovery requests.
    users[username]["token"] = token
    # update last_seen
    users[username]["last_seen"] = datetime.utcnow().isoformat()
    _save(users)
    out = {**users[username], "username": username}
    if out.get("role") == "admin" and not _is_local_admin_record(out):
        out["role"] = "user"
        perms = out.get("permissions") or {}
        out["permissions"] = {
            "upload": perms.get("upload", True),
            "download": perms.get("download", True),
            "delete": False,
        }
    return out


def get_all_users() -> list:
    users = _load()
    return [
        {
            "username": k,
            "role": v["role"],
            "token": v.get("token"),
            "permissions": v["permissions"],
            "enrolled_at": v.get("enrolled_at"),
            "last_seen": v.get("last_seen"),
        }
        for k, v in users.items()
    ]


def update_user(username: str, data: dict) -> bool:
    users = _load()
    stored_key = _find_user_key(users, username)
    if not stored_key:
        return False
    username = stored_key
    if "permissions" in data:
        users[username]["permissions"].update(data["permissions"])
    if "role" in data:
        users[username]["role"] = data["role"]
        if data["role"] == "admin":
            users[username]["host_id"] = _host_id()
        else:
            users[username].pop("host_id", None)
    _save(users)
    return True


def remove_user(username: str) -> bool:
    users = _load()
    stored_key = _find_user_key(users, username)
    if not stored_key:
        return False
    username = stored_key
    del users[username]
    _save(users)
    return True


def get_user(username: str) -> dict | None:
    users = _load()
    stored_key = _find_user_key(users, username)
    u = users.get(stored_key) if stored_key else None
    if u:
        return {**u, "username": username}
    return None


def is_admin_for_current_host(user: dict) -> bool:
    return user.get("role") == "admin" and user.get("host_id") == _host_id()
