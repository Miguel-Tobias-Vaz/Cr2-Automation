"""ZIP rápido: não recomprime PDFs e formatos já compactados."""

from __future__ import annotations

import zipfile
from pathlib import Path

_STORED_SUFFIXES = frozenset(
    {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".zip",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".mp3",
        ".mp4",
        ".mkv",
        ".xlsx",
        ".xls",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".odt",
        ".ods",
    }
)


def compress_type(path: Path) -> int:
    """PDFs e binários já compactados → armazenar sem recomprimir."""
    ext = path.suffix.lower()
    if ext in _STORED_SUFFIXES:
        return zipfile.ZIP_STORED
    return zipfile.ZIP_DEFLATED


def write_zip_file(zf: zipfile.ZipFile, file_path: Path, arcname: str) -> None:
    zf.write(file_path, arcname, compress_type=compress_type(file_path))
