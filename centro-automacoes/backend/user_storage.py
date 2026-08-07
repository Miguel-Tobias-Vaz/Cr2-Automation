"""Pastas por usuário e recebimento de uploads (planilha / ZIP)."""

from __future__ import annotations

import os
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
USERS_ROOT = ROOT / "data" / "users"

MAX_UPLOAD_BYTES = max(
    1, int(os.getenv("OPTO_MAX_UPLOAD_MB", "150"))
) * 1024 * 1024
MAX_ZIP_FILES = max(100, int(os.getenv("OPTO_MAX_ZIP_FILES", "5000")))
MAX_ZIP_UNCOMPRESSED = max(
    10, int(os.getenv("OPTO_MAX_ZIP_MB", "500"))
) * 1024 * 1024

ALLOWED_SINGLE = frozenset(
    {".xlsx", ".xlsm", ".xls", ".csv", ".pdf", ".zip"}
)

_PASTA_KEYS = (
    "pasta_base",
    "pasta_saida",
    "pasta_rgf",
    "pasta_rreo",
    "pasta_balancete",
    "pasta_balanco",
)

_WIN_DEFAULTS = (
    r"c:\downloads",
    r"c:\downloads\inhangapi",
    r"c:\downloads\licitacoes",
    r"c:\downloads\contratos",
    r"c:\downloads\repasses",
)


def normalize_owner(owner: str | None) -> str:
    raw = (owner or "local").strip().lower()
    safe = re.sub(r"[^a-z0-9._-]", "_", raw)[:48]
    return safe or "local"


def user_root(owner: str | None) -> Path:
    return USERS_ROOT / normalize_owner(owner)


def ensure_user_dirs(owner: str | None) -> dict[str, Path]:
    base = user_root(owner)
    uploads = base / "uploads"
    output = base / "output"
    for p in (base, uploads, output):
        p.mkdir(parents=True, exist_ok=True)
    return {"root": base, "uploads": uploads, "output": output}


def workspace_info(owner: str | None) -> dict[str, str]:
    dirs = ensure_user_dirs(owner)
    return {
        "username": normalize_owner(owner),
        "output_dir": str(dirs["output"].resolve()),
        "uploads_dir": str(dirs["uploads"].resolve()),
        "root_dir": str(dirs["root"].resolve()),
    }


def _is_blank_or_win_default(value: str | None) -> bool:
    if not value or not str(value).strip():
        return True
    norm = str(value).strip().replace("/", "\\").lower().rstrip("\\")
    return norm in _WIN_DEFAULTS or norm.startswith(r"c:\downloads\\")


def apply_user_defaults(
    config: dict[str, Any] | None, owner: str | None
) -> dict[str, Any]:
    """Preenche pastas vazias ou defaults Windows com a pasta output do usuário."""
    cfg = dict(config or {})
    dirs = ensure_user_dirs(owner)
    out = str(dirs["output"].resolve())
    for key in _PASTA_KEYS:
        if _is_blank_or_win_default(cfg.get(key)):
            cfg[key] = out
    cfg["_workspace"] = workspace_info(owner)
    return cfg


def _safe_name(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\- ()]", "_", base)
    return base[:180] or "arquivo"


def _zip_safe(target: Path, root: Path) -> None:
    resolved = target.resolve()
    root_res = root.resolve()
    if not str(resolved).startswith(str(root_res)):
        raise ValueError("Entrada inválida no ZIP (path traversal).")


def save_upload(
    owner: str | None,
    filename: str,
    data: bytes,
    *,
    extract: bool = False,
) -> dict[str, Any]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(
            "Arquivo muito grande (máx. {0} MB).".format(MAX_UPLOAD_BYTES // (1024 * 1024))
        )
    dirs = ensure_user_dirs(owner)
    safe = _safe_name(filename)
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_SINGLE:
        raise ValueError(
            "Tipo não permitido. Use: {0}".format(", ".join(sorted(ALLOWED_SINGLE)))
        )

    upload_id = uuid.uuid4().hex[:10]
    dest_dir = dirs["uploads"] / upload_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / safe
    dest_file.write_bytes(data)

    result: dict[str, Any] = {
        "id": upload_id,
        "filename": safe,
        "path": str(dest_file.resolve()),
        "size": len(data),
        "kind": ext.lstrip("."),
    }

    if ext == ".zip" and extract:
        extract_dir = dest_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        count = 0
        with zipfile.ZipFile(dest_file, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                count += 1
                if count > MAX_ZIP_FILES:
                    shutil.rmtree(dest_dir, ignore_errors=True)
                    raise ValueError("ZIP com arquivos demais.")
                total += info.file_size
                if total > MAX_ZIP_UNCOMPRESSED:
                    shutil.rmtree(dest_dir, ignore_errors=True)
                    raise ValueError("ZIP descompactado excede o limite permitido.")
                member = _safe_name(info.filename)
                out_path = extract_dir / member
                _zip_safe(out_path, extract_dir)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        result["extracted_dir"] = str(extract_dir.resolve())
        result["extracted_files"] = count
        # pasta_base típica = conteúdo extraído
        result["suggested_pasta_base"] = str(extract_dir.resolve())

    return result
