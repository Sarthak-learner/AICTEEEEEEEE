"""Content-addressed document storage.

Files are stored as: STORAGE_ROOT / sha256[:2] / sha256[2:4] / sha256
This gives a flat, deduplication-safe store.
"""
import hashlib
import os
import shutil
from pathlib import Path
from app.config import get_settings

settings = get_settings()


def _storage_path(sha256: str) -> Path:
    root = Path(settings.STORAGE_ROOT)
    return root / sha256[:2] / sha256[2:4] / sha256


def store_file(tmp_path: Path) -> tuple[str, str]:
    """Store a file by content hash. Returns (sha256, storage_key)."""
    sha256 = _sha256_file(tmp_path)
    dest = _storage_path(sha256)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_path, dest)
    key = f"{sha256[:2]}/{sha256[2:4]}/{sha256}"
    return sha256, key


def retrieve_path(storage_key: str) -> Path:
    """Return the absolute path for a storage key."""
    root = Path(settings.STORAGE_ROOT)
    return root / storage_key


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
