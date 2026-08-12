"""Artefato de saída (ZIP) ao finalizar jobs."""

from __future__ import annotations

import json
import threading
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.user_storage import MAX_ZIP_FILES, MAX_ZIP_UNCOMPRESSED
from backend.zip_fast import write_zip_file

if TYPE_CHECKING:
    from backend.jobs import Job, JobManager, JobStatus

ZIP_LOGIC_VERSION = 2

ZIP_FILENAMES = ("resultado.zip", "download.zip")

_zip_build_locks: dict[str, threading.Lock] = {}

_FILE_KEYS = (
    "planilha",
    "planilha_normas",
    "planilha_auditoria",
    "planilha_materias",
    "planilha_diarias",
    "planilha_licitacoes",
    "planilha_documentos",
    "planilha_preenchida",
    "pendentes_relatorio",
    "arquivo_nao_publicadas",
)

_DIR_KEYS = ("pasta_contratos",)

_SKIP_ZIP_NAMES = frozenset({"runtime.json", "config.json", "cancel.flag"})


def _skip_zip_file(path: Path) -> bool:
    return path.name in _SKIP_ZIP_NAMES


def find_job_zip_file(job_dir: Path) -> Path | None:
    """Localiza ZIP de download já gerado na pasta do job."""
    for name in ZIP_FILENAMES:
        path = job_dir / name
        if path.is_file():
            return path
    return None


def job_has_download(job: Job) -> bool:
    """True se o job tem ZIP pronto (memória ou disco)."""
    zip_ref = (job.result or {}).get("zip")
    if zip_ref:
        path = Path(str(zip_ref))
        if path.is_file():
            return True
    found = find_job_zip_file(job.dir)
    if found:
        job.result["zip"] = str(found)
        return True
    return False


def ensure_download_zip(job: Job) -> Path | None:
    """Garante ZIP existente; tenta montar se ainda não houver."""
    if job_has_download(job):
        return Path(str(job.result["zip"]))
    if job.result.get("_zip_building"):
        return None
    lock = _zip_build_locks.setdefault(job.id, threading.Lock())
    if not lock.acquire(blocking=False):
        return None
    try:
        if job_has_download(job):
            return Path(str(job.result["zip"]))
        return build_download_zip(job)
    finally:
        lock.release()


def ensure_disk_download(job_id: str, owner: str | None = None) -> bool:
    """Tenta montar ZIP a partir de meta/config no disco (após restart)."""
    from backend.job_log import read_job_meta
    from backend.job_paths import find_job_dir
    from backend.jobs import Job, JobStatus

    job_dir = find_job_dir(job_id, owner)
    if not job_dir:
        return False
    if find_job_zip_file(job_dir):
        return True
    meta = read_job_meta(job_dir)
    if meta.get("status") != JobStatus.COMPLETED.value:
        return False
    config: dict[str, Any] = {}
    config_path = job_dir / "config.json"
    if config_path.is_file():
        try:
            with open(config_path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                config = loaded
        except (OSError, json.JSONDecodeError):
            pass
    job = Job(
        id=job_id,
        service_id=str(meta.get("service_id") or "unknown"),
        config=config,
        status=JobStatus.COMPLETED,
        started_at=meta.get("started_at"),
        finished_at=meta.get("finished_at"),
        owner=meta.get("owner") or owner,
    )
    job.result.update(meta.get("result") or {})
    return bool(build_download_zip(job))


def _user_output_root(job: Job) -> Path | None:
    ws = (job.config or {}).get("_workspace") or {}
    raw = ws.get("output_dir")
    if not raw:
        return None
    p = Path(str(raw))
    if p.is_dir():
        return p.resolve()
    return None


def _service_output_folder(job: Job) -> Path | None:
    root = _user_output_root(job)
    if not root or not job.service_id:
        return None
    sub = root / job.service_id
    if sub.is_dir():
        return sub.resolve()
    return None


def _is_shared_output_root(job: Job, folder: Path) -> bool:
    root = _user_output_root(job)
    if not root:
        return False
    try:
        return folder.resolve() == root
    except OSError:
        return False


def _files_modified_since(folder: Path, since: float, *, margin: float = 3.0) -> list[Path]:
    cutoff = since - margin
    found: list[Path] = []
    for f in folder.rglob("*"):
        if not f.is_file():
            continue
        try:
            if f.stat().st_mtime >= cutoff:
                found.append(f)
        except OSError:
            continue
    return found


def _arcname_for(base: Path, file_path: Path) -> str:
    try:
        rel = file_path.resolve().relative_to(base.resolve())
        return str(rel).replace("\\", "/")
    except ValueError:
        return file_path.name


def _iter_folder_files(job: Job, folder: Path) -> list[Path]:
    if _is_shared_output_root(job, folder) and job.started_at:
        files = _files_modified_since(folder, job.started_at)
        if not files:
            sub = _service_output_folder(job)
            if sub and sub.is_dir() and sub != folder.resolve():
                files = [f for f in sub.rglob("*") if f.is_file()]
        return [f for f in files if f.is_file() and not _skip_zip_file(f)]
    return [
        f
        for f in folder.rglob("*")
        if f.is_file() and not _skip_zip_file(f)
    ]


def _collect_zip_entries(job: Job) -> list[tuple[Path, str]]:
    """Monta lista (arquivo, caminho dentro do zip) preservando subpastas."""
    explicit_files, explicit_dirs = _collect_explicit_artifacts(job)
    items: list[tuple[Path, str]] = []
    seen: set[str] = set()

    def add(path: Path, arc: str) -> None:
        arc = arc.replace("\\", "/").lstrip("/")
        if not arc or arc in seen or not path.is_file() or _skip_zip_file(path):
            return
        seen.add(arc)
        items.append((path.resolve(), arc))

    for f in explicit_files:
        add(f, f.name)

    for d in explicit_dirs:
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file():
                add(
                    f,
                    "{0}/{1}".format(d.name, f.relative_to(d)).replace("\\", "/"),
                )

    folders = _folder_candidates(job)
    multi_root = len(folders) > 1
    for folder in folders:
        if not folder.is_dir():
            continue
        prefix = (folder.name + "/") if multi_root else ""
        for f in _iter_folder_files(job, folder):
            add(f, prefix + str(f.relative_to(folder)).replace("\\", "/"))

    return items


def _check_zip_limits(items: list[tuple[Path, str]]) -> str | None:
    if len(items) > MAX_ZIP_FILES:
        return (
            "Muitos arquivos para o ZIP ({0} > limite {1}). "
            "Baixe a pasta em Arquivos ou aumente OPTO_MAX_ZIP_FILES."
        ).format(len(items), MAX_ZIP_FILES)
    total = 0
    for path, _ in items:
        try:
            total += path.stat().st_size
        except OSError:
            continue
        if total > MAX_ZIP_UNCOMPRESSED:
            mb = MAX_ZIP_UNCOMPRESSED // (1024 * 1024)
            return (
                "Saída muito grande para o ZIP (~{0} MB+). "
                "Baixe a pasta em Arquivos ou aumente OPTO_MAX_ZIP_MB."
            ).format(mb)
    return None


def _write_zip_items(dest: Path, items: list[tuple[Path, str]], job: Job | None = None) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".zip.part")
    n = 0
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, arc in sorted(items, key=lambda x: x[1].lower()):
                write_zip_file(zf, path, arc)
                n += 1
                if job and n % 500 == 0:
                    job.emit("info", "Montando ZIP… {0} arquivo(s)".format(n))
        tmp.replace(dest)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return n


def _zip_file_list(dest: Path, base: Path, files: list[Path]) -> int:
    if not files:
        return 0
    seen: set[str] = set()
    n = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(set(files)):
            if not f.is_file() or _skip_zip_file(f):
                continue
            try:
                arc = _arcname_for(base, f.resolve())
            except ValueError:
                arc = f.name
            if arc in seen:
                continue
            seen.add(arc)
            write_zip_file(zf, f, arc)
            n += 1
    return n


def _zip_tree(dest: Path, folder: Path, arc_prefix: str) -> int:
    n = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(folder.rglob("*")):
            if not f.is_file() or _skip_zip_file(f):
                continue
            rel = f.relative_to(folder)
            write_zip_file(zf, f, arc_prefix + str(rel).replace("\\", "/"))
            n += 1
    return n


def _collect_explicit_artifacts(job: Job) -> tuple[list[Path], list[Path]]:
    files: list[Path] = []
    dirs: list[Path] = []
    result = job.result or {}
    for key in _FILE_KEYS:
        raw = result.get(key)
        if not raw:
            continue
        p = Path(str(raw))
        if p.is_file():
            files.append(p.resolve())
    for key in _DIR_KEYS:
        raw = result.get(key)
        if not raw:
            continue
        p = Path(str(raw))
        if p.is_dir():
            dirs.append(p.resolve())
    return files, dirs


def _folder_candidates(job: Job) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for key in ("pasta", "pasta_saida", "pasta_base"):
        raw = (job.result or {}).get(key) or (job.config or {}).get(key)
        if not raw:
            continue
        p = Path(str(raw))
        if p.is_dir():
            resolved = str(p.resolve())
        elif p.is_file():
            resolved = str(p.parent.resolve())
        else:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(Path(resolved))
    job_out = job.dir / "output"
    if job_out.is_dir() and any(job_out.iterdir()):
        resolved = str(job_out.resolve())
        if resolved not in seen:
            seen.add(resolved)
            out.append(job_out)
    return out


def build_download_zip(job: Job) -> Path | None:
    """Monta ZIP de saída em job.dir. Retorna path ou None."""
    if job.result.get("_zip_v") != ZIP_LOGIC_VERSION:
        job.result.pop("zip", None)
        job.result.pop("download_files", None)
        job.result.pop("_zip_error", None)

    existing = job.result.get("zip")
    if existing:
        path = Path(str(existing))
        if path.is_file() and job.result.get("_zip_v") == ZIP_LOGIC_VERSION:
            return path

    items = _collect_zip_entries(job)
    if not items:
        return None

    limit_err = _check_zip_limits(items)
    if limit_err:
        job.result["_zip_error"] = limit_err
        if hasattr(job, "emit"):
            job.emit("warn", limit_err)
        return None

    dest = job.dir / "resultado.zip"
    try:
        count = _write_zip_items(dest, items, job)
    except OSError as exc:
        msg = "Falha ao gravar ZIP: {0}".format(str(exc)[:160])
        job.result["_zip_error"] = msg
        if hasattr(job, "emit"):
            job.emit("error", msg)
        return None

    if count > 0:
        job.result["zip"] = str(dest)
        job.result["download_files"] = count
        job.result["_zip_v"] = ZIP_LOGIC_VERSION
        job.result.pop("_zip_error", None)
        return dest
    return None


def finalize_job_output(manager: JobManager, job: Job) -> None:
    from backend.jobs import JobStatus

    if job.status != JobStatus.COMPLETED:
        return
    if job.result.get("zip") and job.result.get("_zip_v") == ZIP_LOGIC_VERSION:
        return
    job.result["_zip_building"] = True
    try:
        path = build_download_zip(job)
        if path:
            job.emit(
                "info",
                "Pacote de download pronto ({0} arquivo(s)).".format(
                    job.result.get("download_files", "?")
                ),
            )
        elif job.result.get("_zip_error"):
            pass
        else:
            job.emit(
                "warn",
                "Nenhum arquivo encontrado para montar o ZIP — use Arquivos no menu "
                "ou baixe a pasta de saída.",
            )
    except Exception as exc:
        msg = "Falha ao montar ZIP: {0}".format(str(exc)[:200])
        job.result["_zip_error"] = msg
        job.emit("error", msg)
    finally:
        job.result.pop("_zip_building", None)


def schedule_finalize_job_output(manager: JobManager, job: Job) -> None:
    """Monta ZIP em thread separada para não segurar o status concluído."""
    from backend.jobs import JobStatus

    if job.status != JobStatus.COMPLETED:
        return
    if job_has_download(job):
        return

    def _run() -> None:
        try:
            finalize_job_output(manager, job)
        finally:
            try:
                manager._persist()
            except Exception:
                pass
            try:
                from backend import queue_store

                queue_store.save_completed(manager)
            except Exception:
                pass

    job.result["_zip_building"] = True
    threading.Thread(target=_run, daemon=True, name="zip-{0}".format(job.id)).start()
