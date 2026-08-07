"""Executa runners com Playwright em subprocesso isolado."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from backend.config import BROWSER_SERVICES, USE_SUBPROCESS
from backend.jobs import JobCancelled
from backend.runners.base import PROJECT_ROOT, _limpar_linha_log

# centro-automacoes/ (contém o pacote backend/) — NÃO usar parent.parent:
# este arquivo está em backend/runners/, então parent.parent seria só backend/.
ROOT = Path(__file__).resolve().parents[2]
CANCEL_WAIT_S = 12.0


def uses_subprocess(service_id: str) -> bool:
    return USE_SUBPROCESS and service_id in BROWSER_SERVICES


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    paths = [str(ROOT), str(PROJECT_ROOT)]
    existing = env.get("PYTHONPATH", "")
    if existing:
        paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    env.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _write_runtime_config(job) -> None:
    path = job.dir / "runtime.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(job.config or {}, fh, ensure_ascii=False, indent=2)


def _cleanup_worker_files(job) -> None:
    for name in ("runtime.json", "cancel.flag"):
        try:
            (job.dir / name).unlink(missing_ok=True)
        except OSError:
            pass


def _apply_progress(job, payload: dict) -> None:
    if not hasattr(job, "set_progress"):
        return
    job.set_progress(
        done=payload.get("done"),
        total=payload.get("total"),
        label=payload.get("label"),
    )


def _handle_worker_line(job, line: str, visto: set[str]) -> None:
    raw = (line or "").strip()
    if not raw:
        return
    if raw.startswith("{") and '"op"' in raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and payload.get("op") == "log":
            job.emit(str(payload.get("level") or "info"), str(payload.get("msg") or ""))
            return
        if isinstance(payload, dict) and payload.get("op") == "progress":
            _apply_progress(job, payload)
            return
    limpa = _limpar_linha_log(raw, visto=visto)
    if limpa:
        job.emit("info", limpa)


def _load_worker_result(job) -> None:
    path = job.dir / "result.json"
    if not path.is_file():
        return
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data.get("result"), dict):
            job.result.update(data["result"])
        if data.get("error") and not job.error:
            job.error = str(data["error"])
        if data.get("cancel_requested"):
            job.cancel_requested = True
    except (OSError, json.JSONDecodeError):
        pass
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _terminate_process(proc: subprocess.Popen, job) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)
    except OSError:
        pass
    job.emit("warn", "Subprocesso encerrado após cancelamento.")


def run_isolated(job) -> None:
    """Roda o runner em subprocesso; logs e progresso voltam via stdout (NDJSON)."""
    _write_runtime_config(job)
    cancel_flag = job.dir / "cancel.flag"
    try:
        cancel_flag.unlink(missing_ok=True)
    except OSError:
        pass

    cmd = [sys.executable, "-m", "backend.job_worker", job.id, job.service_id]
    job.emit("info", "Subprocesso isolado (Playwright) — PID em execução…")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        env=_worker_env(),
        bufsize=1,
    )

    visto: set[str] = set()
    cancel_since: float | None = None

    try:
        assert proc.stdout is not None
        while True:
            if job.cancel_requested and cancel_since is None:
                cancel_since = time.time()
                try:
                    cancel_flag.write_text("1", encoding="utf-8")
                except OSError:
                    pass

            line = proc.stdout.readline()
            if line:
                _handle_worker_line(job, line, visto)
            elif proc.poll() is not None:
                break

            if cancel_since is not None and proc.poll() is None:
                if time.time() - cancel_since > CANCEL_WAIT_S:
                    _terminate_process(proc, job)
                    job.cancel_requested = True
                    break

        if proc.stdout:
            for line in proc.stdout:
                _handle_worker_line(job, line, visto)

        code = proc.wait()
    finally:
        _load_worker_result(job)
        _cleanup_worker_files(job)

    if code == 2 or job.cancel_requested:
        job.cancel_requested = True
        raise JobCancelled()
    if code != 0:
        msg = job.error or "Subprocesso terminou com código {0}".format(code)
        raise RuntimeError(msg)
