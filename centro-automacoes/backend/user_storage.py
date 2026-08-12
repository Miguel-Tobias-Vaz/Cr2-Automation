"""Pastas por usuário e recebimento de uploads (planilha / ZIP)."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import unicodedata
import uuid
import zipfile
from pathlib import Path
from typing import Any

from backend.zip_fast import write_zip_file

ROOT = Path(__file__).resolve().parent.parent
USERS_ROOT = ROOT / "data" / "users"

MAX_UPLOAD_BYTES = max(
    1, int(os.getenv("OPTO_MAX_UPLOAD_MB", "150"))
) * 1024 * 1024
MAX_ZIP_FILES = max(100, int(os.getenv("OPTO_MAX_ZIP_FILES", "50000")))
MAX_ZIP_UNCOMPRESSED = max(
    10, int(os.getenv("OPTO_MAX_ZIP_MB", "2048"))
) * 1024 * 1024

FOLDER_SIZE_ENABLED = os.getenv("OPTO_FOLDER_SIZE", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
FOLDER_SIZE_MAX_FILES = max(100, int(os.getenv("OPTO_FOLDER_SIZE_MAX_FILES", "25000")))

ALLOWED_SINGLE = frozenset(
    {".xlsx", ".xlsm", ".xls", ".csv", ".pdf", ".zip"}
)

_PASTA_KEYS = (
    "pasta_base",
    "pasta_saida",
    "pasta_sessoes",
    "pasta_rgf",
    "pasta_rreo",
    "pasta_balancete",
    "pasta_balanco",
)

_PUBLICACAO_PASTA_KEYS = frozenset(
    {"pasta_rgf", "pasta_rreo", "pasta_balancete", "pasta_balanco"}
)

_PUBLICACAO_FOLDER_ALIASES: dict[str, tuple[str, ...]] = {
    "pasta_rgf": ("rgf", "relatorio de gestao fiscal", "gestao fiscal"),
    "pasta_rreo": ("rreo", "relatorio resumido", "relatorio rreo"),
    "pasta_balancete": ("balancete", "balancete financeiro"),
    "pasta_balanco": (
        "balanco",
        "balanco e relatorios",
        "relatorios anuais",
        "balanco e relatorio",
    ),
}

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


def user_jobs_dir(owner: str | None) -> Path:
    p = user_root(owner) / "jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_output_dir(owner: str | None, service_id: str | None = None) -> Path:
    dirs = ensure_user_dirs(owner)
    if service_id:
        p = dirs["output"] / service_id
        p.mkdir(parents=True, exist_ok=True)
        return p.resolve()
    return dirs["output"].resolve()


def path_belongs_to_user(value: str | Path | None, owner: str | None) -> bool:
    if not value:
        return False
    try:
        resolved = Path(str(value)).resolve()
        root = user_root(owner).resolve()
        if resolved == root:
            return True
        return str(resolved).startswith(str(root) + os.sep)
    except OSError:
        return False


def _should_rewrite_pasta(
    value: str | None,
    owner: str | None,
    service_id: str | None,
) -> bool:
    if is_local_mode():
        return _is_blank_or_win_default(value)
    if _is_blank_or_win_default(value):
        return True
    if not path_belongs_to_user(value, owner):
        return True
    if service_id:
        try:
            shared = user_output_dir(owner, None)
            if Path(str(value)).resolve() == shared:
                return True
        except OSError:
            return True
    return False


def ensure_user_dirs(owner: str | None) -> dict[str, Path]:
    base = user_root(owner)
    uploads = base / "uploads"
    output = base / "output"
    jobs = base / "jobs"
    for p in (base, uploads, output, jobs):
        p.mkdir(parents=True, exist_ok=True)
    return {"root": base, "uploads": uploads, "output": output, "jobs": jobs}


def workspace_info(owner: str | None) -> dict[str, str]:
    dirs = ensure_user_dirs(owner)
    user = normalize_owner(owner)
    return {
        "username": user,
        "output_dir": str(dirs["output"].resolve()),
        "uploads_dir": str(dirs["uploads"].resolve()),
        "jobs_dir": str(dirs["jobs"].resolve()),
        "root_dir": str(dirs["root"].resolve()),
        "layout": "data/users/{0}/{{uploads|output|jobs}}".format(user),
    }


def _is_blank_or_win_default(value: str | None) -> bool:
    if not value or not str(value).strip():
        return True
    norm = str(value).strip().replace("/", "\\").lower().rstrip("\\")
    return norm in _WIN_DEFAULTS or norm.startswith(r"c:\downloads\\")


def is_local_mode() -> bool:
    return os.getenv("OPTO_LOCAL", "").strip().lower() in ("1", "true", "yes", "on")


def apply_user_defaults(
    config: dict[str, Any] | None,
    owner: str | None,
    *,
    service_id: str | None = None,
) -> dict[str, Any]:
    """Preenche pastas vazias ou fora do workspace do usuário (VPS)."""
    cfg = dict(config or {})
    if is_local_mode():
        return cfg
    default_out = str(user_output_dir(owner, service_id))
    for key in _PASTA_KEYS:
        if key in _PUBLICACAO_PASTA_KEYS:
            val = cfg.get(key)
            if _is_blank_or_win_default(val) or not path_belongs_to_user(val, owner):
                cfg[key] = ""
            continue
        if _should_rewrite_pasta(cfg.get(key), owner, service_id):
            cfg[key] = default_out
    cfg["_workspace"] = workspace_info(owner)
    return cfg


def _fold_ascii(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _match_publicacao_key(folder_name: str) -> str | None:
    folded = _fold_ascii(folder_name)
    order = (
        "pasta_rgf",
        "pasta_rreo",
        "pasta_balancete",
        "pasta_balanco",
    )
    for key in order:
        aliases = _PUBLICACAO_FOLDER_ALIASES[key]
        if not any(alias in folded for alias in aliases):
            continue
        if key == "pasta_balanco" and "balancete" in folded:
            continue
        return key
    return None


def detect_publicacao_folders(base: Path) -> dict[str, str]:
    """Mapeia subpastas conhecidas (RGF, RREO, etc.) para paths absolutos."""
    if not base.is_dir():
        return {}
    found: dict[str, str] = {}
    scan_roots = [base]
    for child in base.iterdir():
        if child.is_dir():
            scan_roots.append(child)
    for root in scan_roots:
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            key = _match_publicacao_key(entry.name)
            if key and key not in found:
                found[key] = str(entry.resolve())
    return found


def output_publicacao_hints(owner: str | None) -> dict[str, str]:
    """Sugere pastas de publicação a partir de extrações anteriores em output/."""
    hints: dict[str, str] = {}
    output = user_output_dir(owner, None)
    roots = [output]
    try:
        roots.extend(p for p in output.iterdir() if p.is_dir())
    except OSError:
        pass
    for root in roots:
        for key, path in detect_publicacao_folders(root).items():
            hints.setdefault(key, path)
    return hints


def resolve_user_path(owner: str | None, subpath: str = "") -> Path:
    """Resolve subpath relativo ao workspace do usuário (seguro)."""
    root = user_root(owner).resolve()
    rel = (subpath or "").strip().replace("\\", "/").lstrip("/")
    if rel in ("", "."):
        target = root
    else:
        parts = [p for p in rel.split("/") if p and p not in (".", "..")]
        target = root.joinpath(*parts) if parts else root
    resolved = target.resolve()
    if resolved != root and not str(resolved).startswith(str(root) + os.sep):
        raise ValueError("Caminho fora do workspace.")
    return resolved


def list_workspace_owners() -> list[dict[str, Any]]:
    """Lista workspaces existentes em data/users/ (admin)."""
    if not USERS_ROOT.is_dir():
        return []
    owners: list[dict[str, Any]] = []
    for entry in sorted(USERS_ROOT.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        uploads = entry / "uploads"
        output = entry / "output"
        jobs = entry / "jobs"
        size_bytes = 0
        try:
            for p in entry.rglob("*"):
                if p.is_file():
                    try:
                        size_bytes += p.stat().st_size
                    except OSError:
                        pass
        except OSError:
            pass
        owners.append(
            {
                "id": entry.name,
                "root_dir": str(entry.resolve()),
                "uploads_dir": str(uploads.resolve()) if uploads.is_dir() else "",
                "output_dir": str(output.resolve()) if output.is_dir() else "",
                "jobs_dir": str(jobs.resolve()) if jobs.is_dir() else "",
                "size_bytes": size_bytes,
            }
        )
    return owners


def ensure_owner_workspace(owner_id: str) -> str:
    """Valida id de usuário (pasta em data/users)."""
    safe = normalize_owner(owner_id)
    root = user_root(safe)
    if not root.is_dir():
        raise ValueError("Workspace do usuário não encontrado.")
    return safe


def _dir_size(path: Path, *, max_files: int | None = None) -> tuple[int, bool]:
    """
    Soma bytes dos arquivos dentro da pasta (recursivo).
    Retorna (total, partial) — partial=True se atingiu o limite de arquivos.
    """
    cap = max_files if max_files is not None else FOLDER_SIZE_MAX_FILES
    total = 0
    count = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                            count += 1
                            if count >= cap:
                                return total, True
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            continue
    return total, False


def list_workspace_files(
    owner: str | None,
    subpath: str = "",
) -> dict[str, Any]:
    """Lista diretório dentro do workspace do usuário."""
    root = user_root(owner).resolve()
    target = resolve_user_path(owner, subpath)
    if not target.is_dir():
        raise ValueError("Pasta não encontrada.")
    rel = target.relative_to(root).as_posix()
    if rel == ".":
        rel = ""
    entries: list[dict[str, Any]] = []
    for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        try:
            stat = item.stat()
        except OSError:
            continue
        child_rel = item.relative_to(root).as_posix()
        entry: dict[str, Any] = {
            "name": item.name,
            "path": child_rel,
            "abs_path": str(item.resolve()),
            "kind": "dir" if item.is_dir() else "file",
            "size": stat.st_size if item.is_file() else None,
            "modified": stat.st_mtime,
        }
        if item.is_dir() and FOLDER_SIZE_ENABLED:
            total, partial = _dir_size(item)
            entry["size"] = total
            if partial:
                entry["size_partial"] = True
        entries.append(entry)
    return {
        "path": rel,
        "abs_path": str(target.resolve()),
        "parent": str(target.parent.relative_to(root).as_posix())
        if target != root
        else "",
        "entries": entries,
    }


def mkdir_workspace(owner: str | None, subpath: str) -> dict[str, str]:
    target = resolve_user_path(owner, subpath)
    target.mkdir(parents=True, exist_ok=True)
    root = user_root(owner).resolve()
    rel = target.relative_to(root).as_posix()
    return {"path": rel, "abs_path": str(target.resolve())}


def delete_workspace_path(owner: str | None, subpath: str) -> None:
    root = user_root(owner).resolve()
    target = resolve_user_path(owner, subpath)
    if target == root:
        raise ValueError("Não é permitido apagar a raiz do workspace.")
    rel = target.relative_to(root).as_posix()
    if rel == "jobs" or rel.startswith("jobs/"):
        raise ValueError("Não é permitido apagar logs de processos (pasta jobs).")
    if not target.exists():
        raise ValueError("Arquivo ou pasta não encontrado.")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def _assert_download_allowed(owner: str | None, target: Path, root: Path) -> None:
    if not target.exists():
        raise ValueError("Arquivo ou pasta não encontrado.")
    rel = target.relative_to(root).as_posix()
    if rel == "jobs" or rel.startswith("jobs/"):
        raise ValueError("Download da pasta jobs não permitido.")


def prepare_workspace_download(
    owner: str | None, subpath: str
) -> tuple[Path, str, Path | None]:
    """Prepara arquivo ou ZIP de pasta. Retorna (caminho, nome, pasta_temp_ou_None)."""
    root = user_root(owner).resolve()
    target = resolve_user_path(owner, subpath)
    _assert_download_allowed(owner, target, root)

    safe_name = _safe_name(target.name) or "download"
    if target.is_file():
        return target.resolve(), safe_name, None

    tmp_dir = Path(tempfile.mkdtemp(prefix="opto-dl-"))
    zip_path = tmp_dir / f"{safe_name}.zip"
    file_count = 0
    total_size = 0
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(target.rglob("*")):
                if not file_path.is_file():
                    continue
                file_count += 1
                if file_count > MAX_ZIP_FILES:
                    raise ValueError("Pasta com arquivos demais para compactar.")
                try:
                    total_size += file_path.stat().st_size
                except OSError:
                    pass
                if total_size > MAX_ZIP_UNCOMPRESSED:
                    raise ValueError(
                        "Pasta excede o limite de "
                        f"{MAX_ZIP_UNCOMPRESSED // (1024 * 1024)} MB para download."
                    )
                arc = str(file_path.relative_to(target)).replace("\\", "/")
                write_zip_file(zf, file_path, arc)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if file_count == 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError("Pasta vazia — nada para baixar.")

    return zip_path.resolve(), zip_path.name, tmp_dir


def _safe_name(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\- ()]", "_", base)
    return base[:180] or "arquivo"


def _safe_zip_relative(filename: str) -> Path:
    parts: list[str] = []
    for part in Path(filename.replace("\\", "/")).parts:
        if part in ("", ".", ".."):
            continue
        parts.append(_safe_name(part))
    if not parts:
        raise ValueError("Entrada inválida no ZIP (path traversal).")
    return Path(*parts)


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
                member = _safe_zip_relative(info.filename)
                out_path = extract_dir / member
                _zip_safe(out_path, extract_dir)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        result["extracted_dir"] = str(extract_dir.resolve())
        result["extracted_files"] = count
        # pasta_base típica = conteúdo extraído
        result["suggested_pasta_base"] = str(extract_dir.resolve())
        pub = detect_publicacao_folders(extract_dir)
        if pub:
            result["suggested_publicacao"] = pub

    return result
