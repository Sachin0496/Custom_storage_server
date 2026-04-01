import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

FILES_META = Path("files.json")
COPY_BUFFER_SIZE = 8 * 1024 * 1024  # 8 MiB chunks for better throughput


def _ensure_storage(storage_path: Path):
    storage_path.mkdir(parents=True, exist_ok=True)


def _load_meta() -> dict:
    if not FILES_META.exists():
        return {}
    with open(FILES_META) as f:
        return json.load(f)


def _save_meta(data: dict):
    with open(FILES_META, "w") as f:
        json.dump(data, f, indent=2)


def save_file(upload_file, owner: str, storage_path: Path) -> dict:
    _ensure_storage(storage_path)
    file_id = str(uuid.uuid4())
    original_name = upload_file.filename
    safe_name = f"{file_id}_{original_name}"
    dest = storage_path / safe_name

    with open(dest, "wb") as out:
        shutil.copyfileobj(upload_file.file, out, length=COPY_BUFFER_SIZE)

    size = dest.stat().st_size
    meta = _load_meta()
    meta[file_id] = {
        "id": file_id,
        "original_name": original_name,
        "stored_name": safe_name,
        "owner": owner,
        "size": size,
        "uploaded_at": datetime.utcnow().isoformat(),
    }
    _save_meta(meta)
    return meta[file_id]


def list_files() -> list:
    meta = _load_meta()
    return list(meta.values())


def get_file(file_id: str, storage_path: Path) -> tuple[Path, str] | None:
    meta = _load_meta()
    if file_id not in meta:
        return None
    entry = meta[file_id]
    path = storage_path / entry["stored_name"]
    if not path.exists():
        return None
    return path, entry["original_name"]


def delete_file(file_id: str, storage_path: Path) -> bool:
    meta = _load_meta()
    if file_id not in meta:
        return False
    entry = meta[file_id]
    path = storage_path / entry["stored_name"]
    if path.exists():
        path.unlink()
    del meta[file_id]
    _save_meta(meta)
    return True


def storage_stats(storage_path: Path) -> dict:
    _ensure_storage(storage_path)
    total = sum(f.stat().st_size for f in storage_path.iterdir() if f.is_file())
    count = len(_load_meta())
    return {"total_bytes": total, "file_count": count}

