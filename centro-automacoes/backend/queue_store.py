"""Persistência da fila de jobs em disco."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.jobs import Job, JobManager, JobStatus

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "jobs"
QUEUE_FILE = DATA / "queue_state.json"
VERSION = 1


def _ensure_data() -> None:
    DATA.mkdir(parents=True, exist_ok=True)


def save(manager: JobManager) -> None:
    """Grava jobs pending/running para sobreviver a reinício."""
    from backend.jobs import JobStatus

    _ensure_data()
    with manager._lock:
        alive = [
            j
            for j in manager._jobs.values()
            if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
        ]
        items = sorted(alive, key=lambda x: x.created_at)
        payload = {
            "version": VERSION,
            "saved_at": time.time(),
            "jobs": [
                {
                    "id": j.id,
                    "service_id": j.service_id,
                    "status": j.status.value,
                    "created_at": j.created_at,
                    "started_at": j.started_at,
                    "cancel_requested": j.cancel_requested,
                    "owner": j.owner,
                    "queue_rank": j.queue_rank,
                }
                for j in items
            ],
        }
    tmp = QUEUE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    tmp.replace(QUEUE_FILE)


def save_runtime_config(job: Job) -> None:
    """Config completa (credenciais) para worker e restore."""
    _ensure_data()
    job.dir.mkdir(parents=True, exist_ok=True)
    path = job.dir / "runtime.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(job.config or {}, fh, ensure_ascii=False, indent=2)


def load_runtime_config(job_id: str, owner: str | None = None) -> dict[str, Any] | None:
    from backend.job_paths import find_job_dir

    found = find_job_dir(job_id, owner)
    if not found:
        return None
    path = found / "runtime.json"
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def restore(manager: JobManager) -> int:
    """Restaura fila do disco. Jobs 'running' viram pending."""
    from backend.jobs import Job, JobStatus

    if not QUEUE_FILE.is_file():
        return 0

    try:
        with open(QUEUE_FILE, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return 0

    entries = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return 0

    restored = 0
    with manager._lock:
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            job_id = str(raw.get("id") or "").strip()
            service_id = str(raw.get("service_id") or "").strip()
            if not job_id or not service_id:
                continue
            if job_id in manager._jobs:
                continue
            owner_raw = raw.get("owner")
            config = load_runtime_config(job_id, owner_raw)
            if config is None:
                continue

            status_raw = str(raw.get("status") or "pending")
            if status_raw == JobStatus.RUNNING.value:
                status = JobStatus.PENDING
                was_running = True
            elif status_raw == JobStatus.PENDING.value:
                status = JobStatus.PENDING
                was_running = False
            else:
                continue

            job = Job(
                id=job_id,
                service_id=service_id,
                config=config,
                status=status,
                created_at=float(raw.get("created_at") or time.time()),
                started_at=None,
                cancel_requested=bool(raw.get("cancel_requested")),
                owner=owner_raw,
                queue_rank=int(raw.get("queue_rank") or 0),
            )
            manager._jobs[job_id] = job
            restored += 1
            if was_running:
                job.emit(
                    "warn",
                    "Servidor reiniciado — job recolocado na fila (estava rodando).",
                )
            else:
                job.emit("info", "Job restaurado da fila após reinício do servidor.")

    return restored


def cleanup_runtime(job_id: str, owner: str | None = None) -> None:
    from backend.job_paths import find_job_dir

    found = find_job_dir(job_id, owner)
    if not found:
        return
    path = found / "runtime.json"
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
