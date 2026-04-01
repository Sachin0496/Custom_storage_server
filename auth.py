import json
import hashlib
import secrets
import os
from pathlib import Path
from datetime import datetime

USERS_FILE = Path("users.json")


def _load() -> dict:
    if not USERS_FILE.exists():
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)


def _save(data: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_setup_done() -> bool:
    users = _load()
    return any(u["role"] == "admin" for u in users.values())


def enroll(username: str) -> dict | None:
    """Register a new user. Returns token dict or None if username taken."""
    users = _load()
    if username in users:
        return None  # already exists

    token = secrets.token_urlsafe(32)
    role = "admin" if not is_setup_done() else "user"
    users[username] = {
        "token_hash": _hash(token),
        "role": role,
        "permissions": {
            "upload": True,
            "download": True,
            "delete": role == "admin",
        },
        "enrolled_at": datetime.utcnow().isoformat(),
        "last_seen": datetime.utcnow().isoformat(),
    }
    _save(users)
    return {"username": username, "token": token, "role": role}


def authenticate(username: str, token: str) -> dict | None:
    """Validate credentials, update last_seen. Returns user record or None."""
    users = _load()
    user = users.get(username)
    if not user:
        return None
    if user["token_hash"] != _hash(token):
        return None
    # update last_seen
    users[username]["last_seen"] = datetime.utcnow().isoformat()
    _save(users)
    return {**user, "username": username}


def get_all_users() -> list:
    users = _load()
    return [
        {
            "username": k,
            "role": v["role"],
            "permissions": v["permissions"],
            "enrolled_at": v.get("enrolled_at"),
            "last_seen": v.get("last_seen"),
        }
        for k, v in users.items()
    ]


def update_user(username: str, data: dict) -> bool:
    users = _load()
    if username not in users:
        return False
    if "permissions" in data:
        users[username]["permissions"].update(data["permissions"])
    if "role" in data:
        users[username]["role"] = data["role"]
    _save(users)
    return True


def remove_user(username: str) -> bool:
    users = _load()
    if username not in users:
        return False
    del users[username]
    _save(users)
    return True


def get_user(username: str) -> dict | None:
    users = _load()
    u = users.get(username)
    if u:
        return {**u, "username": username}
    return None
