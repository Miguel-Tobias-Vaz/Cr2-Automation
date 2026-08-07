"""Ponto de entrada: executa um runner em processo isolado."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.job_paths import find_job_dir  # noqa: E402
from backend.jobs import JobCancelled  # noqa: E402
from backend.worker_job import WorkerJob  # noqa: E402


def _load_runner(service_id: str):
    from backend.runners import RUNNERS

    fn = RUNNERS.get(service_id)
    if not fn:
        raise ValueError("Serviço desconhecido: {0}".format(service_id))
    return fn


def main() -> int:
    if len(sys.argv) < 3:
        print("Uso: python -m backend.job_worker <job_id> <service_id>", file=sys.stderr)
        return 1

    job_id = sys.argv[1].strip()
    service_id = sys.argv[2].strip()
    work_dir = find_job_dir(job_id)
    if not work_dir:
        print("[ERRO] pasta do job não encontrada: {0}".format(job_id), file=sys.stderr)
        return 1
    runtime_path = work_dir / "runtime.json"

    if not runtime_path.is_file():
        print("[ERRO] runtime.json não encontrado para job {0}".format(job_id), file=sys.stderr)
        return 1

    with open(runtime_path, encoding="utf-8") as fh:
        config = json.load(fh)

    job = WorkerJob(job_id, service_id, config, work_dir)
    exit_code = 0
    try:
        runner = _load_runner(service_id)
        runner(job)
        if job.cancel_requested:
            exit_code = 2
    except JobCancelled:
        job.cancel_requested = True
        exit_code = 2
    except Exception as exc:
        if job.cancel_requested or type(exc).__name__ in ("Cancelado", "JobCancelled"):
            job.cancel_requested = True
            exit_code = 2
        else:
            job.error = str(exc)
            job.emit("error", str(exc))
            exit_code = 1
    finally:
        job.write_result()
        try:
            runtime_path.unlink(missing_ok=True)
        except OSError:
            pass

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
