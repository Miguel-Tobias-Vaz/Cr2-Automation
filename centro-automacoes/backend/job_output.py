"""Artefato de saída (ZIP) ao finalizar jobs."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.jobs import Job, JobManager, JobStatus


def _zip_tree(dest: Path, folder: Path, arc_prefix: str) -> int:
    n = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(folder.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(folder)
            zf.write(f, arc_prefix + str(rel).replace("\\", "/"))
            n += 1
    return n


def build_download_zip(job: Job) -> Path | None:
    """Monta ZIP de saída em job.dir. Retorna path ou None."""
    if job.result.get("zip"):
        existing = Path(job.result["zip"])
        if existing.is_file():
            return existing

    candidates: list[Path] = []
    for key in ("pasta", "pasta_saida", "pasta_base"):
        raw = (job.result or {}).get(key) or (job.config or {}).get(key)
        if raw:
            p = Path(str(raw))
            if p.is_dir():
                candidates.append(p)
            elif p.is_file():
                candidates.append(p.parent)

    # Saída parcial dentro do job
    job_out = job.dir / "output"
    if job_out.is_dir() and any(job_out.iterdir()):
        candidates.append(job_out)

    seen: set[str] = set()
    for folder in candidates:
        key = str(folder.resolve())
        if key in seen:
            continue
        seen.add(key)
        files = [f for f in folder.rglob("*") if f.is_file()]
        if not files:
            continue
        dest = job.dir / "resultado.zip"
        prefix = folder.name + "/"
        count = _zip_tree(dest, folder, prefix)
        if count > 0:
            job.result["zip"] = str(dest)
            job.result["download_files"] = count
            return dest

    # Planilha única no result
    for key in ("planilha", "planilha_normas", "planilha_materias"):
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
            return dest

    return None


def finalize_job_output(manager: JobManager, job: Job) -> None:
    from backend.jobs import JobStatus

    if job.status != JobStatus.COMPLETED:
        return
    if job.result.get("zip"):
        return
    path = build_download_zip(job)
    if path:
        job.emit("info", "Pacote de download pronto ({0} arquivo(s)).".format(
            job.result.get("download_files", "?")
        ))
