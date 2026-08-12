"""Pastas por usuário e recebimento de uploads (planilha / ZIP)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
import uuid
import zipfile
import logging
from pathlib import Path
from typing import Any, Iterator

from backend.zip_fast import write_zip_file

_log = logging.getLogger("uvicorn.error")

ROOT = Path(__file__).resolve().parent.parent
USERS_ROOT = ROOT / "data" / "users"

MAX_UPLOAD_BYTES = max(
    1, int(os.getenv("OPTO_MAX_UPLOAD_MB", "150"))
) * 1024 * 1024
MAX_ZIP_FILES = max(100, int(os.getenv("OPTO_MAX_ZIP_FILES", "50000")))
MAX_ZIP_UNCOMPRESSED = max(
    10, int(os.getenv("OPTO_MAX_ZIP_MB", "2048"))
) * 1024 * 1024
# Tamanho máximo por lote (cada licitação/ano fica inteira em um lote)
LOTE_MAX_BYTES = max(
    10,
    int(os.getenv("OPTO_ZIP_LOTE_MB", os.getenv("OPTO_MAX_ZIP_MB", "2048"))),
) * 1024 * 1024
DOWNLOAD_CACHE_TTL_S = max(300, int(os.getenv("OPTO_DL_CACHE_TTL_S", "86400")))
PREBUILD_LOTS = os.getenv("OPTO_DL_PREBUILD", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)

_lot_build_locks: dict[str, threading.Lock] = {}

FOLDER_SIZE_ENABLED = os.getenv("OPTO_FOLDER_SIZE", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
FOLDER_SIZE_MAX_FILES = max(100, int(os.getenv("OPTO_FOLDER_SIZE_MAX_FILES", "25000")))
# False = listagem rápida; tamanho de pasta vem depois (endpoint folder-size)
FOLDER_SIZE_ON_LIST = os.getenv("OPTO_FOLDER_SIZE_ON_LIST", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

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


def workspace_folder_size(owner: str | None, subpath: str) -> dict[str, Any]:
    """Tamanho total de uma pasta (recursivo). Usado após listagem rápida."""
    root = user_root(owner).resolve()
    target = resolve_user_path(owner, subpath)
    if not target.is_dir():
        raise ValueError("Pasta não encontrada.")
    rel = target.relative_to(root).as_posix()
    if not FOLDER_SIZE_ENABLED:
        return {"path": rel, "size": None}
    total, partial = _dir_size(target)
    out: dict[str, Any] = {"path": rel, "size": total}
    if partial:
        out["size_partial"] = True
    return out


def list_workspace_files(
    owner: str | None,
    subpath: str = "",
    *,
    include_folder_sizes: bool | None = None,
) -> dict[str, Any]:
    """Lista diretório dentro do workspace do usuário."""
    root = user_root(owner).resolve()
    target = resolve_user_path(owner, subpath)
    if not target.is_dir():
        raise ValueError("Pasta não encontrada.")
    rel = target.relative_to(root).as_posix()
    if rel == ".":
        rel = ""
    compute_sizes = (
        include_folder_sizes
        if include_folder_sizes is not None
        else FOLDER_SIZE_ON_LIST
    )
    entries: list[dict[str, Any]] = []
    for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if item.name.startswith("."):
            continue
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
        if item.is_dir() and FOLDER_SIZE_ENABLED and compute_sizes:
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


def workspace_download_target(
    owner: str | None, subpath: str
) -> tuple[Path, Path, str]:
    """Retorna (root, alvo, nome_seguro)."""
    root = user_root(owner).resolve()
    target = resolve_user_path(owner, subpath)
    _assert_download_allowed(owner, target, root)
    safe_name = _safe_name(target.name) or "download"
    return root, target, safe_name


def _count_files_under(path: Path) -> int:
    n = 0
    for item in path.rglob("*"):
        if item.is_file():
            n += 1
    return n


def _unit_display_name(unit: dict[str, Any]) -> str:
    if unit["kind"] == "dir":
        return str(unit["name"])
    return "Arquivos na raiz"


def _collect_download_units(folder: Path) -> list[dict[str, Any]]:
    """
    Unidades atômicas para lotes: cada subpasta ou grupo de arquivos na raiz.
    Nunca divide uma licitação/ano entre lotes.
    """
    units: list[dict[str, Any]] = []
    root_files: list[Path] = []
    root_bytes = 0
    for item in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        try:
            if item.is_dir():
                total, partial = _dir_size(item)
                units.append(
                    {
                        "name": item.name,
                        "kind": "dir",
                        "bytes": total,
                        "files": _count_files_under(item),
                        "partial_size": partial,
                    }
                )
            elif item.is_file():
                root_files.append(item)
                root_bytes += item.stat().st_size
        except OSError:
            continue
    if root_files:
        units.append(
            {
                "name": "__root_files__",
                "kind": "root_files",
                "bytes": root_bytes,
                "files": len(root_files),
                "file_names": sorted(f.name for f in root_files),
            }
        )
    return units


def _partition_download_units(
    units: list[dict[str, Any]],
    max_bytes: int,
    max_files: int,
) -> list[dict[str, Any]]:
    lots: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None

    def _new_lot() -> dict[str, Any]:
        return {"units": [], "bytes": 0, "files": 0, "names": []}

    for unit in units:
        label = _unit_display_name(unit)
        u_bytes = int(unit["bytes"])
        u_files = int(unit["files"])
        if u_files > max_files:
            raise ValueError(
                f'"{label}" tem arquivos demais para um lote ({u_files}). '
                "Aumente OPTO_MAX_ZIP_FILES ou baixe essa pasta separadamente."
            )
        if u_bytes > max_bytes:
            mb = max_bytes // (1024 * 1024)
            got = max(1, u_bytes // (1024 * 1024))
            raise ValueError(
                f'"{label}" sozinha tem ~{got} MB (máx. {mb} MB por lote). '
                "Baixe essa pasta separadamente."
            )
        if cur is None:
            cur = _new_lot()
        elif cur["bytes"] + u_bytes > max_bytes or cur["files"] + u_files > max_files:
            lots.append(cur)
            cur = _new_lot()
        cur["units"].append(unit)
        cur["bytes"] += u_bytes
        cur["files"] += u_files
        cur["names"].append(label)
    if cur and cur["units"]:
        lots.append(cur)
    return lots


def _download_cache_dir(owner: str | None, subpath: str) -> Path:
    key = hashlib.sha256(subpath.encode("utf-8")).hexdigest()[:24]
    cache = user_root(owner) / ".dl-cache" / key
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _lot_zip_names(units: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for unit in units:
        if unit["kind"] == "dir":
            names.append(unit["name"])
        elif unit["kind"] == "root_files":
            names.extend(unit.get("file_names") or [])
    return names


def _fingerprint_lot_units(folder: Path, units: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for unit in units:
        if unit["kind"] == "dir":
            p = folder / unit["name"]
            try:
                st = p.stat()
                parts.append(f"d:{unit['name']}:{st.st_mtime_ns}:{st.st_size}")
            except OSError:
                parts.append(f"d:{unit['name']}:0:0")
        else:
            fn = ",".join(unit.get("file_names") or [])
            parts.append(f"r:{fn}:{unit.get('bytes', 0)}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _lot_cache_paths(owner: str | None, subpath: str, lot_index: int) -> tuple[Path, Path]:
    base = _download_cache_dir(owner, subpath)
    n = lot_index
    return base / f"lote-{n:02d}.zip", base / f"lote-{n:02d}.json"


def lot_cache_ready(
    owner: str | None,
    subpath: str,
    lot_index: int,
    folder: Path,
    units: list[dict[str, Any]],
) -> bool:
    zip_path, meta_path = _lot_cache_paths(owner, subpath, lot_index)
    if not zip_path.is_file() or not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        age = time.time() - zip_path.stat().st_mtime
        if age > DOWNLOAD_CACHE_TTL_S:
            return False
        return meta.get("fingerprint") == _fingerprint_lot_units(folder, units)
    except (OSError, json.JSONDecodeError, ValueError):
        return False


def get_lot_cache_file(
    owner: str | None,
    subpath: str,
    lot_index: int,
    folder: Path,
    units: list[dict[str, Any]],
) -> Path | None:
    if lot_cache_ready(owner, subpath, lot_index, folder, units):
        return _lot_cache_paths(owner, subpath, lot_index)[0]
    return None


def _build_lot_zip_on_disk(folder: Path, units: list[dict[str, Any]], dest: Path) -> None:
    names = _lot_zip_names(units)
    if not names:
        raise ValueError("Lote vazio.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(".zip.part")
    partial.unlink(missing_ok=True)
    if can_stream_folder_zip():
        cmd = ["zip", "-r", "-0", str(partial), *names]
        proc = subprocess.run(
            cmd,
            cwd=folder,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace")
            raise RuntimeError(err[:400] or "zip falhou")
        partial.replace(dest)
        return
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as zf:
        _write_lot_zip_file(zf, folder, units)
    partial.replace(dest)


def ensure_lot_cached(
    owner: str | None,
    subpath: str,
    lot_index: int,
    folder: Path,
    units: list[dict[str, Any]],
) -> Path:
    """Gera ZIP do lote em cache (reutilizado nos próximos downloads)."""
    if cached := get_lot_cache_file(owner, subpath, lot_index, folder, units):
        return cached

    lock_key = f"{owner}:{subpath}:{lot_index}"
    lock = _lot_build_locks.setdefault(lock_key, threading.Lock())
    with lock:
        if cached := get_lot_cache_file(owner, subpath, lot_index, folder, units):
            return cached
        zip_path, meta_path = _lot_cache_paths(owner, subpath, lot_index)
        fingerprint = _fingerprint_lot_units(folder, units)
        _build_lot_zip_on_disk(folder, units, zip_path)
        meta_path.write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "built_at": time.time(),
                    "path": subpath,
                    "lot": lot_index,
                }
            ),
            encoding="utf-8",
        )
        return zip_path


def schedule_lots_prebuild(owner: str | None, subpath: str) -> None:
    """Monta lotes em background — download fica instantâneo quando pronto."""
    if not PREBUILD_LOTS:
        return

    def _worker() -> None:
        try:
            _root, target, _safe = workspace_download_target(owner, subpath)
            if not target.is_dir():
                return
            units = _collect_download_units(target)
            if not units:
                return
            rel = target.relative_to(_root).as_posix()
            if rel == ".":
                rel = ""
            lots = _partition_download_units(units, LOTE_MAX_BYTES, MAX_ZIP_FILES)
            for i, lot in enumerate(lots, 1):
                ensure_lot_cached(owner, rel, i, target, lot["units"])
        except Exception as exc:
            _log.warning("Pré-montagem de lotes falhou (%s): %s", subpath, exc)

    threading.Thread(target=_worker, daemon=True, name="opto-lot-prebuild").start()


def _folder_lots_partitioned(
    owner: str | None, subpath: str
) -> tuple[Path, str, list[dict[str, Any]], list[dict[str, Any]]]:
    _root, target, safe_name = workspace_download_target(owner, subpath)
    if not target.is_dir():
        raise ValueError("Não é uma pasta.")
    units = _collect_download_units(target)
    if not units:
        raise ValueError("Pasta vazia — nada para baixar.")
    rel = target.relative_to(_root).as_posix()
    if rel == ".":
        rel = ""
    lots = _partition_download_units(units, LOTE_MAX_BYTES, MAX_ZIP_FILES)
    return target, rel, safe_name, lots


def folder_download_plan(owner: str | None, subpath: str) -> dict[str, Any]:
    """Plano de download: um ZIP ou vários lotes (subpastas inteiras)."""
    root, target, safe_name = workspace_download_target(owner, subpath)
    rel = target.relative_to(root).as_posix()
    if rel == ".":
        rel = ""

    if target.is_file():
        try:
            size = target.stat().st_size
        except OSError:
            size = 0
        return {
            "mode": "file",
            "path": rel,
            "name": safe_name,
            "bytes": size,
            "files": 1,
            "lots": [],
        }

    target, rel, safe_name, lots = _folder_lots_partitioned(owner, subpath)
    total_lots = len(lots)
    lot_rows: list[dict[str, Any]] = []
    for i, lot in enumerate(lots):
        n = i + 1
        cached = lot_cache_ready(owner, rel, n, target, lot["units"])
        lot_rows.append(
            {
                "lot": n,
                "total_lots": total_lots,
                "bytes": lot["bytes"],
                "files": lot["files"],
                "units": lot["names"],
                "unit_count": len(lot["units"]),
                "cached": cached,
                "label": f"Lote {n} de {total_lots}" if total_lots > 1 else safe_name,
                "filename": (
                    f"{safe_name}-lote{n:02d}-de-{total_lots:02d}.zip"
                    if total_lots > 1
                    else f"{safe_name}.zip"
                ),
            }
        )

    if total_lots > 1:
        schedule_lots_prebuild(owner, rel)

    return {
        "mode": "lots" if total_lots > 1 else "single",
        "path": rel,
        "name": safe_name,
        "bytes": sum(l["bytes"] for l in lots),
        "files": sum(l["files"] for l in lots),
        "lot_count": total_lots,
        "lote_max_mb": LOTE_MAX_BYTES // (1024 * 1024),
        "prebuild": PREBUILD_LOTS,
        "lots": lot_rows,
    }


def _resolve_lot_units(
    owner: str | None, subpath: str, lot_index: int
) -> tuple[Path, str, dict[str, Any], list[dict[str, Any]], str]:
    _root, target, safe_name = workspace_download_target(owner, subpath)
    if target.is_file():
        if lot_index not in (0, 1):
            raise ValueError("Lote inválido.")
        return target, safe_name, {"filename": safe_name}, [], ""

    target, rel, safe_name, lots = _folder_lots_partitioned(owner, subpath)
    if lot_index < 1 or lot_index > len(lots):
        raise ValueError("Lote inválido.")
    lot = lots[lot_index - 1]
    n = lot_index
    total_lots = len(lots)
    lot_meta = {
        "lot": n,
        "total_lots": total_lots,
        "bytes": lot["bytes"],
        "files": lot["files"],
        "units": lot["names"],
        "unit_count": len(lot["units"]),
        "cached": lot_cache_ready(owner, rel, n, target, lot["units"]),
        "label": f"Lote {n} de {total_lots}" if total_lots > 1 else safe_name,
        "filename": (
            f"{safe_name}-lote{n:02d}-de-{total_lots:02d}.zip"
            if total_lots > 1
            else f"{safe_name}.zip"
        ),
    }
    return target, safe_name, lot_meta, lot["units"], rel


def can_stream_folder_zip() -> bool:
    return shutil.which("zip") is not None


def _zip_args_for_units(units: list[dict[str, Any]]) -> list[str]:
    args = ["zip", "-r", "-0", "-"]
    for unit in units:
        if unit["kind"] == "dir":
            args.append(unit["name"])
        elif unit["kind"] == "root_files":
            args.extend(unit.get("file_names") or [])
    if len(args) <= 3:
        raise ValueError("Lote vazio.")
    return args


def iter_lot_zip_stream(folder: Path, units: list[dict[str, Any]]) -> Iterator[bytes]:
    """ZIP em streaming só das unidades do lote (subpastas inteiras)."""
    folder = folder.resolve()
    proc = subprocess.Popen(
        _zip_args_for_units(units),
        cwd=folder,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.stdout is None:
        proc.kill()
        proc.wait()
        raise RuntimeError("Falha ao iniciar compactação.")
    try:
        while True:
            chunk = proc.stdout.read(512 * 1024)
            if not chunk:
                break
            yield chunk
        rc = proc.wait()
        if rc != 0:
            err = (proc.stderr.read() if proc.stderr else b"").decode(
                "utf-8", errors="replace"
            )
            _log.error("zip lote falhou (rc=%s): %s", rc, err[:800])
            raise RuntimeError("Falha ao compactar lote para download.")
    except GeneratorExit:
        proc.kill()
        proc.wait()
        raise
    except Exception:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise


def _write_lot_zip_file(
    zf: zipfile.ZipFile, folder: Path, units: list[dict[str, Any]]
) -> None:
    for unit in units:
        if unit["kind"] == "dir":
            base = folder / unit["name"]
            for file_path in sorted(base.rglob("*")):
                if not file_path.is_file():
                    continue
                arc = str(file_path.relative_to(folder)).replace("\\", "/")
                write_zip_file(zf, file_path, arc)
        elif unit["kind"] == "root_files":
            for fname in unit.get("file_names") or []:
                fp = folder / fname
                if fp.is_file():
                    write_zip_file(zf, fp, fname)


def prepare_lot_download(
    owner: str | None, subpath: str, lot_index: int
) -> tuple[Path, str, Path | None]:
    """ZIP do lote — usa cache em disco quando possível."""
    target, _safe, lot_meta, units, rel = _resolve_lot_units(owner, subpath, lot_index)
    if not units:
        return target.resolve(), lot_meta["filename"], None
    zip_path = ensure_lot_cached(owner, rel, lot_index, target, units)
    return zip_path, lot_meta["filename"], None


def prepare_workspace_download(
    owner: str | None, subpath: str, *, lot: int = 1
) -> tuple[Path, str, Path | None]:
    """Prepara download de arquivo ou lote de pasta."""
    _root, target, safe_name = workspace_download_target(owner, subpath)
    if target.is_file():
        return target.resolve(), safe_name, None
    _resolve_lot_units(owner, subpath, lot)
    return prepare_lot_download(owner, subpath, lot)


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
