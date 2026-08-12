"""Artefato de saída (ZIP) ao finalizar jobs."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.jobs import Job, JobManager, JobStatus

ZIP_LOGIC_VERSION = 2

ZIP_FILENAMES = ("resultado.zip", "download.zip")

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
    return build_download_zip(job)


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
    rel = file_path.relative_to(base)
    return str(rel).replace("\\", "/")


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
            zf.write(f, arc)
            n += 1
    return n


def _zip_tree(dest: Path, folder: Path, arc_prefix: str) -> int:
    n = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(folder.rglob("*")):
            if not f.is_file() or _skip_zip_file(f):
                continue
            rel = f.relative_to(folder)
            zf.write(f, arc_prefix + str(rel).replace("\\", "/"))
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

    existing = job.result.get("zip")
    if existing:
        path = Path(str(existing))
        if path.is_file() and job.result.get("_zip_v") == ZIP_LOGIC_VERSION:
            return path

    explicit_files, explicit_dirs = _collect_explicit_artifacts(job)

    # Artefatos explícitos + arquivos da pasta de saída deste job
    if explicit_files or explicit_dirs:
        entries: list[Path] = list(explicit_files)
        for d in explicit_dirs:
            entries.extend(f for f in d.rglob("*") if f.is_file())
        for folder in _folder_candidates(job):
            if _is_shared_output_root(job, folder) and job.started_at:
                entries.extend(_files_modified_since(folder, job.started_at))
            elif not _is_shared_output_root(job, folder):
                entries.extend(f for f in folder.rglob("*") if f.is_file())
        if entries:
            root = _user_output_root(job)
            if root:
                base = root
            else:
                bases = {f.parent for f in entries if f.is_file()}
                base = min(bases, key=lambda p: len(str(p))) if bases else entries[0].parent
            dest = job.dir / "resultado.zip"
            count = _zip_file_list(dest, base, entries)
            if count > 0:
                job.result["zip"] = str(dest)
                job.result["download_files"] = count
                job.result["_zip_v"] = ZIP_LOGIC_VERSION
                return dest

    for folder in _folder_candidates(job):
        if _is_shared_output_root(job, folder) and job.started_at:
            files = _files_modified_since(folder, job.started_at)
            if not files:
                sub = _service_output_folder(job)
                if sub and sub != folder.resolve():
                    files = [f for f in sub.rglob("*") if f.is_file()]
                    if files:
                        folder = sub
            if not files:
                continue
            dest = job.dir / "resultado.zip"
            count = _zip_file_list(dest, folder, files)
        else:
            dest = job.dir / "resultado.zip"
            prefix = folder.name + "/"
            count = _zip_tree(dest, folder, prefix)
        if count > 0:
            job.result["zip"] = str(dest)
            job.result["download_files"] = count
            job.result["_zip_v"] = ZIP_LOGIC_VERSION
            return dest

    # Planilha única sem pasta (fallback legado)
    for key in _FILE_KEYS:
        raw = (job.result or {}).get(key)
        if not raw:
            continue
        p = Path(str(raw))
        if p.is_file():
            dest = job.dir / "resultado.zip"
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(p, p.name)
            job.result["zip"] = str(dest)
            job.result["download_files"] = 1
            job.result["_zip_v"] = ZIP_LOGIC_VERSION
            return dest

    return None


def finalize_job_output(manager: JobManager, job: Job) -> None:
    from backend.jobs import JobStatus

    if job.status != JobStatus.COMPLETED:
        return
    if job.result.get("zip") and job.result.get("_zip_v") == ZIP_LOGIC_VERSION:
        return
    path = build_download_zip(job)
    if path:
        job.emit(
            "info",
            "Pacote de download pronto ({0} arquivo(s)).".format(
                job.result.get("download_files", "?")
            ),
        )
    else:
        job.emit(
            "warn",
            "Nenhum arquivo encontrado para montar o ZIP — use Arquivos no menu "
            "ou baixe a pasta de saída pelo admin.",
        )
