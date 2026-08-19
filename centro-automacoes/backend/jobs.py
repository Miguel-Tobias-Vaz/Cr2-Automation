"""Gerenciador de jobs com fila FIFO e logs em memória."""

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

from backend.config import JOB_TIMEOUT_S, MAX_CONCURRENT, MAX_QUEUE
from backend import queue_store
from backend.job_paths import ensure_job_dir, iter_all_job_dirs

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


class QueueFullError(Exception):
    """Fila cheia (pending + running >= MAX_QUEUE)."""


@dataclass
class Job:
    id: str
    service_id: str
    config: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    logs: list[dict[str, str]] = field(default_factory=list)
    cancel_requested: bool = False
    owner: str | None = None
    queue_rank: int = 0
    timed_out: bool = False
    progress_done: int = 0
    progress_total: int = 0
    progress_label: str = ""
    _subscribers: list[queue.Queue] = field(default_factory=list, repr=False)

    @property
    def dir(self) -> Path:
        return ensure_job_dir(self.id, self.owner)

    @property
    def progress_percent(self) -> int | None:
        if self.progress_total > 0:
            pct = int(round(100.0 * self.progress_done / self.progress_total))
            pct = max(0, min(100, pct))
            if self.status == JobStatus.RUNNING and pct >= 100:
                return 99
            return pct
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
        # Avisa o painel (SSE) sem poluir o histórico de log.
        entry = {
            "t": time.strftime("%H:%M:%S"),
            "level": "progress",
            "msg": "",
            "progress": {
                "done": self.progress_done,
                "total": self.progress_total,
                "percent": self.progress_percent,
                "label": self.progress_label,
            },
        }
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

    def to_dict(self, manager: JobManager | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "service_id": self.service_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "result": self.result,
            "has_download": self._has_download(),
            "zip_building": bool((self.result or {}).get("_zip_building")),
            "zip_error": (self.result or {}).get("_zip_error"),
            "cancel_requested": self.cancel_requested,
            "owner": self.owner,
            "queue_rank": self.queue_rank,
            "timed_out": self.timed_out,
            "progress": {
                "done": self.progress_done,
                "total": self.progress_total,
                "percent": self.progress_percent,
                "label": self.progress_label,
            },
        }
        if manager is not None:
            payload["queue"] = manager.queue_meta(self)
        return payload

    def _has_download(self) -> bool:
        from backend.job_output import job_has_download

        return job_has_download(self)


class JobManager:
    """Fila FIFO: até MAX_CONCURRENT jobs rodando; demais aguardam."""

    MAX_ATIVOS = MAX_CONCURRENT
    MAX_QUEUE = MAX_QUEUE

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._runner: Callable[[Job], None] | None = None
        self._persist_enabled = True
        self._timeout_stop = threading.Event()
        if JOB_TIMEOUT_S > 0:
            threading.Thread(target=self._timeout_loop, daemon=True).start()

    def _timeout_loop(self) -> None:
        while not self._timeout_stop.is_set():
            self._timeout_stop.wait(30)
            if JOB_TIMEOUT_S <= 0:
                continue
            now = time.time()
            for job in self.running_jobs():
                if not job.started_at or job.cancel_requested:
                    continue
                if now - job.started_at >= JOB_TIMEOUT_S:
                    self._apply_timeout(job)

    def _apply_timeout(self, job: Job) -> None:
        with self._lock:
            if job.status != JobStatus.RUNNING or job.cancel_requested:
                return
            job.timed_out = True
            job.cancel_requested = True
        job.emit(
            "warn",
            "Timeout automático ({0}s) — job cancelado.".format(JOB_TIMEOUT_S),
        )
        job.error = "Timeout após {0}s".format(JOB_TIMEOUT_S)
        self.cancel(job.id)

    def restore_from_disk(self) -> int:
        n = queue_store.restore(self)
        n += queue_store.restore_completed(self)
        return n

    def resume_queue(self, runner: Callable[[Job], None]) -> None:
        self._runner = runner
        self._dispatch()

    def _persist(self) -> None:
        if not self._persist_enabled:
            return
        try:
            queue_store.save(self)
            queue_store.save_completed(self)
        except OSError:
            pass

    def running_count(self) -> int:
        with self._lock:
            return self._running_count_locked()

    def pending_count(self) -> int:
        with self._lock:
            return self._pending_count_locked()

    def ativos(self) -> int:
        """Pending + running (compatibilidade com API antiga)."""
        with self._lock:
            return self._alive_count_locked()

    def _running_count_locked(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status == JobStatus.RUNNING)

    def _pending_count_locked(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status == JobStatus.PENDING)

    def _alive_count_locked(self) -> int:
        return sum(
            1
            for j in self._jobs.values()
            if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
        )

    def _pending_jobs_locked(self) -> list[Job]:
        return sorted(
            (j for j in self._jobs.values() if j.status == JobStatus.PENDING),
            key=lambda j: (j.queue_rank, j.created_at),
        )

    def _next_queue_rank_locked(self) -> int:
        pending = [j for j in self._jobs.values() if j.status == JobStatus.PENDING]
        if not pending:
            return 0
        return max(j.queue_rank for j in pending) + 1

    def queue_position(self, job_id: str) -> int | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != JobStatus.PENDING:
                return None
            pending = self._pending_jobs_locked()
            for i, j in enumerate(pending, start=1):
                if j.id == job_id:
                    return i
        return None

    def queue_meta(self, job: Job) -> dict[str, Any]:
        running = self.running_count()
        meta: dict[str, Any] = {
            "running_slots": running,
            "max_slots": self.MAX_ATIVOS,
            "pending_total": self.pending_count(),
        }
        if job.status == JobStatus.RUNNING:
            meta["position"] = 0
            meta["ahead"] = 0
        elif job.status == JobStatus.PENDING:
            pos = self.queue_position(job.id) or 0
            meta["position"] = pos
            meta["ahead"] = max(0, pos - 1)
        return meta

    def queue_snapshot(self) -> dict[str, Any]:
        with self._lock:
            running = [
                j.to_dict(None)
                for j in sorted(
                    (x for x in self._jobs.values() if x.status == JobStatus.RUNNING),
                    key=lambda x: x.started_at or x.created_at,
                )
            ]
            pending = [
                j.to_dict(None)
                for j in self._pending_jobs_locked()
            ]
        for i, item in enumerate(pending, start=1):
            item["queue"] = {
                "position": i,
                "ahead": i - 1,
                "running_slots": len(running),
                "max_slots": self.MAX_ATIVOS,
                "pending_total": len(pending),
            }
        return {
            "running": len(running),
            "pending": len(pending),
            "max_concurrent": self.MAX_ATIVOS,
            "max_queue": self.MAX_QUEUE,
            "running_jobs": running,
            "pending_jobs": pending,
        }

    def job_ativo(self) -> Job | None:
        """Job RUNNING mais recente (pill / compat)."""
        with self._lock:
            running = [j for j in self._jobs.values() if j.status == JobStatus.RUNNING]
        if not running:
            return None
        return max(running, key=lambda j: j.started_at or j.created_at)

    def _job_output_dir_conflict(self, run_path: str, *, exclude_id: str) -> Job | None:
        target = str(run_path or "").strip()
        if not target:
            return None
        with self._lock:
            for job in self._jobs.values():
                if job.id == exclude_id:
                    continue
                if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
                    continue
                other = str((job.config or {}).get("_job_run_dir") or "").strip()
                if other and other == target:
                    return job
        return None

    def running_jobs(self) -> list[Job]:
        with self._lock:
            items = [j for j in self._jobs.values() if j.status == JobStatus.RUNNING]
        return sorted(items, key=lambda j: j.started_at or j.created_at, reverse=True)

    def user_jobs_for_owner(self, owner: str) -> list[Job]:
        """Jobs RUNNING e PENDING do usuario (running primeiro)."""
        with self._lock:
            running = sorted(
                [
                    j
                    for j in self._jobs.values()
                    if j.status == JobStatus.RUNNING
                    and self._owners_match(j.owner, owner)
                ],
                key=lambda j: j.started_at or j.created_at,
            )
            pending = [
                j
                for j in self._pending_jobs_locked()
                if self._owners_match(j.owner, owner)
            ]
        return running + pending

    def user_job_for_owner(
        self, owner: str, service_id: str | None = None
    ) -> Job | None:
        """Job RUNNING ou PENDING do usuario (prioriza running; filtra por ferramenta)."""
        jobs_list = self.user_jobs_for_owner(owner)
        if service_id:
            for job in jobs_list:
                if job.service_id == service_id:
                    return job
            return None
        return jobs_list[0] if jobs_list else None

    def create(self, service_id: str, config: dict[str, Any]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], service_id=service_id, config=config)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def enqueue(
        self,
        service_id: str,
        config: dict[str, Any],
        runner: Callable[[Job], None],
        owner: str | None = None,
    ) -> Job:
        with self._lock:
            if self._alive_count_locked() >= self.MAX_QUEUE:
                raise QueueFullError(
                    "Fila cheia ({0} jobs). Aguarde algum terminar.".format(self.MAX_QUEUE)
                )
        job = self.create(service_id, config)
        job.owner = owner
        from backend.user_storage import assign_job_output_dir

        try:
            run_dir = assign_job_output_dir(job, owner=owner, service_id=service_id)
        except ValueError:
            with self._lock:
                self._jobs.pop(job.id, None)
            raise
        if run_dir:
            conflict = self._job_output_dir_conflict(run_dir, exclude_id=job.id)
            if conflict:
                with self._lock:
                    self._jobs.pop(job.id, None)
                nome = (job.config or {}).get("nome_pasta") or run_dir
                raise ValueError(
                    'Já existe um job na fila usando a pasta "{0}". '
                    "Aguarde terminar ou escolha outro nome.".format(nome)
                )
            label = (job.config or {}).get("nome_pasta")
            if label and label != job.id:
                job.emit("info", "Pasta deste job: {0}".format(label))
            else:
                job.emit("info", "Pasta deste job: {0}".format(run_dir))
        with self._lock:
            job.queue_rank = self._next_queue_rank_locked()
        self.save_config(job)
        queue_store.save_runtime_config(job)
        self._runner = runner
        self._persist()
        self._dispatch()
        if job.status == JobStatus.PENDING:
            pos = self.queue_position(job.id)
            job.emit(
                "info",
                "Na fila — posição {0} ({1} rodando, máx. {2})".format(
                    pos or "?",
                    self.running_count(),
                    self.MAX_ATIVOS,
                ),
            )
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    @staticmethod
    def _owners_match(owner: str | None, username: str | None) -> bool:
        if not owner or not username:
            return False
        return owner.strip().lower() == username.strip().lower()

    def _job_visible_to_user(
        self, job: Job, username: str, *, is_admin: bool
    ) -> bool:
        if is_admin:
            return True
        # Com autenticação, jobs sem dono não são públicos entre usuários.
        return self._owners_match(job.owner, username)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            items = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [j.to_dict(self) for j in items[:40]]

    def list_jobs_for_user(
        self, username: str, *, is_admin: bool, limit: int = 40
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        visible = [
            j for j in items if self._job_visible_to_user(j, username, is_admin=is_admin)
        ]
        return [j.to_dict(self) for j in visible[:limit]]

    def queue_snapshot_for_user(
        self, username: str, *, is_admin: bool
    ) -> dict[str, Any]:
        if is_admin:
            return self.queue_snapshot()
        with self._lock:
            running_jobs = sorted(
                (
                    j
                    for j in self._jobs.values()
                    if j.status == JobStatus.RUNNING
                    and self._job_visible_to_user(j, username, is_admin=False)
                ),
                key=lambda x: x.started_at or x.created_at,
            )
            pending_jobs = [
                j
                for j in self._pending_jobs_locked()
                if self._job_visible_to_user(j, username, is_admin=False)
            ]
        running = [j.to_dict(None) for j in running_jobs]
        pending = [j.to_dict(None) for j in pending_jobs]
        for i, item in enumerate(pending, start=1):
            item["queue"] = {
                "position": i,
                "ahead": i - 1,
                "running_slots": len(running),
                "max_slots": self.MAX_ATIVOS,
                "pending_total": len(pending),
            }
        return {
            "running": len(running),
            "pending": len(pending),
            "max_concurrent": self.MAX_ATIVOS,
            "max_queue": self.MAX_QUEUE,
            "running_jobs": running,
            "pending_jobs": pending,
        }

    def list_downloads_ready(
        self,
        owner: str | None = None,
        *,
        limit: int = 2,
        max_age_s: float = 2 * 60 * 60,
    ) -> list[dict[str, Any]]:
        """Jobs concluídos com ZIP — só do usuário, recentes (evita poluir o painel)."""
        now = time.time()
        with self._lock:
            items = list(self._jobs.values())
        ready: list[dict[str, Any]] = []
        for j in items:
            if j.status != JobStatus.COMPLETED:
                continue
            if not self._has_download_for(j):
                continue
            if owner:
                if not self._owners_match(j.owner, owner):
                    continue
            elif j.owner:
                # Sem auth: só jobs órfãos (modo local compartilhado).
                continue
            finished = float(j.finished_at or 0)
            if max_age_s and finished and (now - finished) > max_age_s:
                continue
            ready.append(
                {
                    "id": j.id,
                    "service_id": j.service_id,
                    "owner": j.owner,
                    "finished_at": j.finished_at,
                    "has_download": True,
                }
            )
        ready.sort(key=lambda x: float(x.get("finished_at") or 0), reverse=True)
        return ready[:limit]

    @staticmethod
    def _has_download_for(job: Job) -> bool:
        from backend.job_output import job_has_download

        return job_has_download(job)

    def admin_snapshot(self) -> dict[str, Any]:
        with self._lock:
            items = list(self._jobs.values())
        by_status: dict[str, int] = {}
        by_service: dict[str, int] = {}
        for j in items:
            by_status[j.status.value] = by_status.get(j.status.value, 0) + 1
            by_service[j.service_id] = by_service.get(j.service_id, 0) + 1
        recent = sorted(items, key=lambda j: j.created_at, reverse=True)[:30]
        return {
            "total": len(items),
            "by_status": by_status,
            "by_service": by_service,
            "recent": [j.to_dict(self) for j in recent],
        }

    def disk_usage_jobs(self) -> dict[str, Any]:
        total = 0
        dirs = 0
        for p in iter_all_job_dirs():
            dirs += 1
            for f in p.rglob("*"):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except OSError:
                        pass
        return {
            "job_dirs": dirs,
            "bytes": total,
            "mb": round(total / (1024 * 1024), 2),
            "path": str(DATA),
        }

    def cancel(self, job_id: str, *, force: bool = False) -> Job | None:
        job = self.get(job_id)
        if not job:
            return None
        if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return job
        job.cancel_requested = True
        # Sinal imediato para subprocessos (não depende do loop de logs acordar).
        try:
            flag = Path(job.dir) / "cancel.flag"
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("1", encoding="utf-8")
        except OSError:
            pass
        if job.status == JobStatus.PENDING:
            job.status = JobStatus.CANCELLED
            job.finished_at = time.time()
            msg = "Removido da fila antes de iniciar."
            if job.timed_out:
                msg = "Removido da fila (timeout enfileirado)."
            job.emit("warn", msg)
            job.emit("info", "— fim —")
            try:
                from backend.job_log import write_job_meta

                write_job_meta(job)
            except Exception:
                pass
            self._persist()
            queue_store.cleanup_runtime(job.id, job.owner)
            return job
        job.emit("warn", "Cancelamento solicitado — parando a fila deste processo...")
        return job

    def reorder_pending(self, ordered_ids: list[str]) -> list[str]:
        """Reordena jobs pending (admin). Retorna ids na ordem final."""
        with self._lock:
            pending = {j.id: j for j in self._jobs.values() if j.status == JobStatus.PENDING}
            valid = [jid for jid in ordered_ids if jid in pending]
            tail = [jid for jid in sorted(pending.keys(), key=lambda x: pending[x].queue_rank) if jid not in valid]
            final = valid + tail
            for rank, jid in enumerate(final):
                pending[jid].queue_rank = rank
        self._persist()
        return final

    def _dispatch(self) -> None:
        with self._lock:
            runner = self._runner
            if not runner:
                return
            to_start: list[Job] = []
            while self._running_count_locked() < self.MAX_ATIVOS:
                pending = self._pending_jobs_locked()
                if not pending:
                    break
                job = pending[0]
                if job.cancel_requested:
                    job.status = JobStatus.CANCELLED
                    job.finished_at = time.time()
                    continue
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
                to_start.append(job)
            self._persist()

        for job in to_start:
            threading.Thread(
                target=self._worker,
                args=(job, runner),
                daemon=True,
            ).start()

    def _worker(self, job: Job, runner: Callable[[Job], None]) -> None:
        if job.cancel_requested:
            job.status = JobStatus.CANCELLED
            job.finished_at = time.time()
            self._persist()
            queue_store.cleanup_runtime(job.id, job.owner)
            self._dispatch()
            return

        job.emit("info", "Processo iniciado — {0}".format(job.service_id))
        try:
            runner(job)
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.result.setdefault("mensagem", "Fila cancelada pelo usuario.")
                job.emit("warn", "CANCELADO — fila interrompida.")
                job.emit("info", "— fim —")
            elif job.status == JobStatus.RUNNING:
                if job.timed_out:
                    job.status = JobStatus.FAILED
                    job.result.setdefault("mensagem", "Job encerrado por timeout.")
                    job.emit("error", "TIMEOUT — job excedeu o limite configurado.")
                    job.emit("info", "— fim —")
                else:
                    job.status = JobStatus.COMPLETED
                    from backend.job_output import schedule_finalize_job_output

                    schedule_finalize_job_output(self, job)
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
            try:
                from backend.job_log import write_job_meta

                write_job_meta(job)
            except Exception:
                pass
            self._persist()
            queue_store.cleanup_runtime(job.id, job.owner)
            self._dispatch()

    def cancel_all_pending(self) -> int:
        n = 0
        with self._lock:
            pending = self._pending_jobs_locked()
        for job in pending:
            if self.cancel(job) and job.status == JobStatus.CANCELLED:
                n += 1
        self._persist()
        return n

    def start(self, job: Job, runner: Callable[[Job], None]) -> None:
        """Compat: inicia job já criado (preferir enqueue)."""
        self._runner = runner
        self._dispatch()

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
