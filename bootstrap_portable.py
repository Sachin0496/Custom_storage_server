import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _can_write(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".lanstore_write_test.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _pick_portable_dir(root: Path) -> Path:
    home = Path.home()
    candidates = [
        root.parent / "PortableShare",
        home / "PortableShare",
        home / "Desktop" / "PortableShare",
        home / "Documents" / "PortableShare",
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            if _can_write(candidate):
                return candidate.resolve()
        except OSError:
            continue
    # Last resort outside app directory (still beginner-friendly).
    fallback = (home / "PortableShare").resolve()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def main() -> int:
    root = Path(__file__).resolve().parent
    shares_file = root / "shares.json"
    portable_dir = _pick_portable_dir(root)

    try:
        if shares_file.exists():
            shares = json.loads(shares_file.read_text(encoding="utf-8"))
            if not isinstance(shares, dict):
                shares = {}
        else:
            shares = {}
    except (OSError, json.JSONDecodeError):
        shares = {}

    existing_has_writable = False
    for entry in shares.values():
        try:
            p = Path(entry.get("path", "")).expanduser()
            if p.exists() and p.is_dir() and _can_write(p):
                existing_has_writable = True
                break
        except Exception:
            continue

    portable_path_str = str(portable_dir)
    portable_id = None
    for sid, entry in shares.items():
        if str(entry.get("path", "")).lower() == portable_path_str.lower():
            portable_id = sid
            break
    if portable_id is None:
        for sid, entry in shares.items():
            if str(entry.get("name", "")).strip().lower().startswith("portable"):
                portable_id = sid
                break

    if portable_id is None:
        portable_id = str(uuid.uuid4())
        shares[portable_id] = {
            "id": portable_id,
            "name": "Portable (Writable)",
            "path": portable_path_str,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        action = "added"
    else:
        shares[portable_id]["name"] = "Portable (Writable)"
        shares[portable_id]["path"] = portable_path_str
        shares[portable_id].setdefault("created_at", datetime.now(timezone.utc).isoformat())
        action = "updated"

    shares_file.write_text(json.dumps(shares, indent=2), encoding="utf-8")

    if not existing_has_writable:
        print(f"[startup] No writable mapped drives found. {action} default: {portable_path_str}")
    else:
        print(f"[startup] Portable drive {action}: {portable_path_str}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
