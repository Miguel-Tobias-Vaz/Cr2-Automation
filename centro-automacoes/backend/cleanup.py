"""Limpeza de arquivos temporários (admin)."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.jobs import JobManager, JobStatus

ROOT = Path(__file__).resolve().parent.parent
DATA_JOBS = ROOT / "data" / "jobs"
AUTOMACOES = ROOT.parent / "automacoes"
USERS_ROOT = ROOT / "data" / "users"

SCREENSHOT_GLOBS = (
    "publicacao-repasses/screenshots_pub",
    "publicacao-sessao/screenshots_pub",
    "publicacao-cr2/screenshots_pub",
)
IA_CACHE_DIRS = (
    AUTOMACOES / "download-licitacoes" / "cache_ia",
    AUTOMACOES / "_comum" / "cache_ia_nome",
)


@dataclass
class CleanupBucket:
    key: str
    label: str
    files: int = 0
    bytes: int = 0
    paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "files": self.files,
            "bytes": self.bytes,
            "mb": round(self.bytes / (1024 * 1024), 2),
            "sample_paths": self.paths[:8],
        }


def _dir_size(path: Path) -> tuple[int, int]:
    total = 0
    count = 0
    if not path.exists():
        return 0, 0
    if path.is_file():
        try:
            return 1, path.stat().st_size
        except OSError:
            return 0, 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
                count += 1
            except OSError:
                pass
    return count, total


def _protected_job_ids(manager: JobManager) -> set[str]:
    from backend.jobs import JobStatus

    out: set[str] = set()
    with manager._lock:
        for j in manager._jobs.values():
            if j.status in (JobStatus.PENDING, JobStatus.RUNNING):
                out.add(j.id)
    return out


def _finished_job_dirs(manager: JobManager, older_than_days: int = 0) -> list[Path]:
    from backend.job_paths import iter_all_job_dirs
    from backend.jobs import JobStatus

    protected = _protected_job_ids(manager)
    cutoff = time.time() - max(0, older_than_days) * 86400
    dirs: list[Path] = []

    mem: dict[str, Any] = {}
    with manager._lock:
        mem = {j.id: j for j in manager._jobs.values()}

    for p in iter_all_job_dirs():
        jid = p.name
        if jid in protected:
            continue
        job = mem.get(jid)
        if job is not None:
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                continue
            finished = job.finished_at or job.created_at
            if older_than_days > 0 and finished > cutoff:
                continue
        dirs.append(p)
    return dirs


def _collect_screenshots() -> list[Path]:
    files: list[Path] = []
    for rel in SCREENSHOT_GLOBS:
        d = AUTOMACOES.joinpath(*rel.split("/"))
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() and f.suffix.lower() in (
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            ):
                files.append(f)
    return files


def _collect_ia_cache() -> list[Path]:
    files: list[Path] = []
    for d in IA_CACHE_DIRS:
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file():
                files.append(f)
    return files


def _collect_upload_temp(older_than_days: int = 7) -> list[Path]:
    cutoff = time.time() - max(0, older_than_days) * 86400
    dirs: list[Path] = []
    if not USERS_ROOT.is_dir():
        return dirs
    for user_dir in USERS_ROOT.iterdir():
        if not user_dir.is_dir():
            continue
        uploads = user_dir / "uploads"
        if not uploads.is_dir():
            continue
        for batch in uploads.iterdir():
            if not batch.is_dir():
                continue
            try:
                if batch.stat().st_mtime > cutoff:
                    continue
            except OSError:
                continue
            dirs.append(batch)
    return dirs


def preview(manager: JobManager, *, job_days: int = 0, upload_days: int = 7) -> dict[str, Any]:
    buckets: list[CleanupBucket] = []

    job_dirs = _finished_job_dirs(manager, job_days)
    b_jobs = CleanupBucket("job_dirs", "Pastas de jobs finalizados / órfãos")
    for d in job_dirs:
        n, sz = _dir_size(d)
        b_jobs.files += n
        b_jobs.bytes += sz
        b_jobs.paths.append(str(d))
    buckets.append(b_jobs)

    shots = _collect_screenshots()
    b_sh = CleanupBucket("screenshots", "Prints de tela (screenshots_pub)")
    for f in shots:
        try:
            b_sh.bytes += f.stat().st_size
            b_sh.files += 1
            b_sh.paths.append(str(f))
        except OSError:
            pass
    buckets.append(b_sh)

    cache_files = _collect_ia_cache()
    b_ia = CleanupBucket("ia_cache", "Cache de IA (licitações / nomes)")
    for f in cache_files:
        try:
            b_ia.bytes += f.stat().st_size
            b_ia.files += 1
            b_ia.paths.append(str(f))
        except OSError:
            pass
    buckets.append(b_ia)

    up_dirs = _collect_upload_temp(upload_days)
    b_up = CleanupBucket("upload_temp", f"Uploads temporários (>{upload_days} dias)")
    for d in up_dirs:
        n, sz = _dir_size(d)
        b_up.files += n
        b_up.bytes += sz
        b_up.paths.append(str(d))
    buckets.append(b_up)

    total_bytes = sum(b.bytes for b in buckets)
    return {
        "buckets": [b.to_dict() for b in buckets],
        "total_files": sum(b.files for b in buckets),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "job_days": job_days,
        "upload_days": upload_days,
    }


def run_cleanup(
    manager: JobManager,
    *,
    job_dirs: bool = False,
    job_days: int = 0,
    screenshots: bool = False,
    ia_cache: bool = False,
    upload_temp: bool = False,
    upload_days: int = 7,
) -> dict[str, Any]:
    deleted_files = 0
    deleted_bytes = 0
    removed_dirs = 0
    errors: list[str] = []

    def _add_removed(n: int, sz: int) -> None:
        nonlocal deleted_files, deleted_bytes
        deleted_files += n
        deleted_bytes += sz

    if job_dirs:
        for d in _finished_job_dirs(manager, job_days):
            n, sz = _dir_size(d)
            try:
                shutil.rmtree(d)
                removed_dirs += 1
                _add_removed(n, sz)
            except OSError as exc:
                errors.append("{0}: {1}".format(d.name, exc))

    if screenshots:
        for f in _collect_screenshots():
            try:
                sz = f.stat().st_size
                f.unlink()
                _add_removed(1, sz)
            except OSError as exc:
                errors.append("{0}: {1}".format(f.name, exc))

    if ia_cache:
        for f in _collect_ia_cache():
            try:
                sz = f.stat().st_size
                f.unlink()
                _add_removed(1, sz)
            except OSError as exc:
                errors.append("{0}: {1}".format(f.name, exc))

    if upload_temp:
        for d in _collect_upload_temp(upload_days):
            n, sz = _dir_size(d)
            try:
                shutil.rmtree(d)
                removed_dirs += 1
                _add_removed(n, sz)
            except OSError as exc:
                errors.append("{0}: {1}".format(d.name, exc))

    return {
        "ok": True,
        "deleted_files": deleted_files,
        "deleted_bytes": deleted_bytes,
        "deleted_mb": round(deleted_bytes / (1024 * 1024), 2),
        "removed_dirs": removed_dirs,
        "errors": errors[:20],
    }
