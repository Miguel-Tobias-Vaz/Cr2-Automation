"""Gerenciador de jobs com logs em memória e SSE."""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "jobs"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    service_id: str
    config: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    logs: list[dict[str, str]] = field(default_factory=list)
    _subscribers: list[queue.Queue] = field(default_factory=list, repr=False)

    @property
    def dir(self) -> Path:
        p = DATA / self.id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def emit(self, level: str, msg: str) -> None:
        entry = {"t": time.strftime("%H:%M:%S"), "level": level, "msg": str(msg)}
        self.logs.append(entry)
        if len(self.logs) > 500:
            self.logs = self.logs[-500:]
        dead: list[queue.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(entry)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass
        log_file = self.dir / "job.log"
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write("{t} [{level}] {msg}\n".format(**entry))

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        self._subscribers.append(q)
        for entry in self.logs[-120:]:
            try:
                q.put_nowait(entry)
            except Exception:
                pass
        return q

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "service_id": self.service_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "result": self.result,
            "has_download": bool(self.result.get("zip")),
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, service_id: str, config: dict[str, Any]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], service_id=service_id, config=config)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            items = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in items[:40]]

    def start(self, job: Job, runner: Callable[[Job], None]) -> None:
        def _worker() -> None:
            job.status = JobStatus.RUNNING
            job.emit("info", "Job iniciado — {0}".format(job.service_id))
            try:
                runner(job)
                if job.status == JobStatus.RUNNING:
                    job.status = JobStatus.COMPLETED
                msg = (job.result or {}).get("mensagem") or "Automação concluída com sucesso."
                job.emit("ok", "✓ CONCLUÍDO — {0}".format(msg))
                job.emit("info", "— fim —")
            except Exception as exc:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                job.emit("error", str(exc))
                job.emit("info", "— fim —")
            finally:
                job.finished_at = time.time()

        threading.Thread(target=_worker, daemon=True).start()

    def zip_folder(self, job: Job, folder: Path, name: str = "saida.zip") -> Path | None:
        if not folder.is_dir():
            return None
        files = [p for p in folder.rglob("*") if p.is_file()]
        if not files:
            return None
        dest = job.dir / name
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, f.relative_to(folder.parent))
        job.result["zip"] = str(dest)
        return dest

    def zip_path(self, job: Job, path: Path) -> Path | None:
        if not path.is_dir():
            return None
        dest = job.dir / "download.zip"
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in path.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(path))
        job.result["zip"] = str(dest)
        return dest

    def save_config(self, job: Job) -> None:
        with open(job.dir / "config.json", "w", encoding="utf-8") as fh:
            json.dump(job.config, fh, ensure_ascii=False, indent=2)
