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
    CANCELLED = "cancelled"


class JobCancelled(Exception):
    """Fila cancelada pelo usuario."""


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
    cancel_requested: bool = False
    # Progresso da fila: done/total → percent (0–100)
    progress_done: int = 0
    progress_total: int = 0
    progress_label: str = ""
    _subscribers: list[queue.Queue] = field(default_factory=list, repr=False)

    @property
    def dir(self) -> Path:
        p = DATA / self.id
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def progress_percent(self) -> int | None:
        if self.progress_total > 0:
            pct = int(round(100.0 * self.progress_done / self.progress_total))
            return max(0, min(100, pct))
        return None

    def set_progress(
        self,
        done: int | None = None,
        total: int | None = None,
        label: str | None = None,
    ) -> None:
        if total is not None and total >= 0:
            self.progress_total = int(total)
        if done is not None and done >= 0:
            self.progress_done = int(done)
        if label is not None:
            self.progress_label = str(label).strip()[:80]

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
            "cancel_requested": self.cancel_requested,
            "progress": {
                "done": self.progress_done,
                "total": self.progress_total,
                "percent": self.progress_percent,
                "label": self.progress_label,
            },
        }


class JobManager:
    """Fila local: no máximo MAX_ATIVOS processos em execução ao mesmo tempo."""

    MAX_ATIVOS = 1

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def ativos(self) -> int:
        with self._lock:
            return sum(
                1
                for j in self._jobs.values()
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
            )

    def job_ativo(self) -> Job | None:
        """Processo pending/running mais recente (para o pill do painel)."""
        with self._lock:
            vivos = [
                j
                for j in self._jobs.values()
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
            ]
        if not vivos:
            return None
        return max(vivos, key=lambda j: j.created_at)

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

    def cancel(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if not job:
            return None
        if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return job
        job.cancel_requested = True
        job.emit("warn", "Cancelamento solicitado — parando a fila deste processo...")
        return job

    def start(self, job: Job, runner: Callable[[Job], None]) -> None:
        def _worker() -> None:
            job.status = JobStatus.RUNNING
            job.emit("info", "Processo iniciado — {0}".format(job.service_id))
            try:
                runner(job)
                if job.cancel_requested:
                    job.status = JobStatus.CANCELLED
                    job.result.setdefault("mensagem", "Fila cancelada pelo usuario.")
                    job.emit("warn", "CANCELADO — fila interrompida.")
                    job.emit("info", "— fim —")
                elif job.status == JobStatus.RUNNING:
                    job.status = JobStatus.COMPLETED
                    msg = (job.result or {}).get("mensagem") or "Automação concluída com sucesso."
                    job.emit("ok", "CONCLUIDO — {0}".format(msg))
                    job.emit("info", "— fim —")
            except JobCancelled:
                job.cancel_requested = True
                job.status = JobStatus.CANCELLED
                job.result.setdefault("mensagem", "Fila cancelada pelo usuario.")
                job.emit("warn", "CANCELADO — fila interrompida.")
                job.emit("info", "— fim —")
            except Exception as exc:
                if job.cancel_requested or type(exc).__name__ == "Cancelado":
                    job.cancel_requested = True
                    job.status = JobStatus.CANCELLED
                    job.result.setdefault("mensagem", "Fila cancelada pelo usuario.")
                    job.emit("warn", "CANCELADO — fila interrompida.")
                    job.emit("info", "— fim —")
                else:
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
        sensiveis = ("senha", "password", "app_password", "token", "api_key", "secret")
        limpo: dict[str, Any] = {}
        for k, v in (job.config or {}).items():
            kl = str(k).lower()
            if any(s in kl for s in sensiveis):
                limpo[k] = "***" if v else ""
            else:
                limpo[k] = v
        with open(job.dir / "config.json", "w", encoding="utf-8") as fh:
            json.dump(limpo, fh, ensure_ascii=False, indent=2)
