"""Resolução de pastas de jobs (legado + por usuário)."""

from __future__ import annotations

from pathlib import Path

from backend.user_storage import USERS_ROOT, is_local_mode, user_jobs_dir

ROOT = Path(__file__).resolve().parent.parent
LEGACY_JOBS_ROOT = ROOT / "data" / "jobs"


def find_job_dir(job_id: str, owner: str | None = None) -> Path | None:
    """Localiza pasta do job (nova estrutura ou legado data/jobs/)."""
    job_id = (job_id or "").strip()
    if not job_id:
        return None
    candidates: list[Path] = []
    if owner:
        candidates.append(user_jobs_dir(owner) / job_id)
    candidates.append(LEGACY_JOBS_ROOT / job_id)
    if not owner and USERS_ROOT.is_dir():
        candidates[:0] = sorted(USERS_ROOT.glob(f"*/jobs/{job_id}"))
    for p in candidates:
        if p.is_dir():
            return p
    return None


def ensure_job_dir(job_id: str, owner: str | None = None) -> Path:
    """Garante pasta do job — usuários autenticados usam data/users/{user}/jobs/."""
    existing = find_job_dir(job_id, owner)
    if existing:
        return existing
    if owner and not is_local_mode():
        p = user_jobs_dir(owner) / job_id
    else:
        p = LEGACY_JOBS_ROOT / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def iter_all_job_dirs() -> list[Path]:
    """Todas as pastas de job (legado + por usuário)."""
    seen: set[str] = set()
    out: list[Path] = []
    for root in (LEGACY_JOBS_ROOT,):
        if not root.is_dir():
            continue
        for p in root.iterdir():
            if p.is_dir():
                key = str(p.resolve())
                if key not in seen:
                    seen.add(key)
                    out.append(p)
    if USERS_ROOT.is_dir():
        for p in USERS_ROOT.glob("*/jobs/*"):
            if p.is_dir():
                key = str(p.resolve())
                if key not in seen:
                    seen.add(key)
                    out.append(p)
    return out
