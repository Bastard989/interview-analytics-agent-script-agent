from __future__ import annotations

import os
from pathlib import Path


def _base_dir() -> Path:
    # В docker-compose будет /data/chunks, локально можно ./data/chunks
    return Path(os.getenv("CHUNKS_DIR", "./data/chunks")).resolve()


def _key_to_path(key: str) -> Path:
    # защита от path traversal
    key = key.lstrip("/")
    if ".." in key.split("/"):
        raise ValueError("invalid key")
    return _base_dir() / key


def put_bytes(key: str, data: bytes) -> str:
    """Сохранить bytes и вернуть ключ."""
    p = _key_to_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return key


def get_bytes(key: str) -> bytes:
    return _key_to_path(key).read_bytes()


def exists(key: str) -> bool:
    return _key_to_path(key).exists()


def delete(key: str) -> None:
    p = _key_to_path(key)
    try:
        p.unlink()
    except FileNotFoundError:
        pass
