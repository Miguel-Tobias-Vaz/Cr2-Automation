"""Testes de limpeza admin."""

from __future__ import annotations

import time

from backend import cleanup
from backend.jobs import Job, JobManager, JobStatus


def test_preview_and_cleanup_jobs(tmp_path, monkeypatch):
    jobs_dir = tmp_path / "data" / "jobs"
    jobs_dir.mkdir(parents=True)
    old = jobs_dir / "job_old"
    old.mkdir()
    (old / "job.log").write_text("log", encoding="utf-8")
    (old / "shot.png").write_bytes(b"x" * 100)

    active = jobs_dir / "job_live"
    active.mkdir()
    (active / "runtime.json").write_text("{}", encoding="utf-8")

    shots = tmp_path / "automacoes" / "publicacao-sessao" / "screenshots_pub"
    shots.mkdir(parents=True)
    (shots / "sessao_erro_1.png").write_bytes(b"y" * 50)

    monkeypatch.setattr(cleanup, "DATA_JOBS", jobs_dir)
    monkeypatch.setattr(cleanup, "AUTOMACOES", tmp_path / "automacoes")
    monkeypatch.setattr(cleanup, "USERS_ROOT", tmp_path / "data" / "users")
    monkeypatch.setattr(cleanup, "SCREENSHOT_GLOBS", ("publicacao-sessao/screenshots_pub",))

    mgr = JobManager()
    mgr._persist_enabled = False
    mgr._jobs["job_live"] = Job(
        id="job_live",
        service_id="documentos",
        config={},
        status=JobStatus.RUNNING,
        created_at=time.time(),
    )
    mgr._jobs["job_old_mem"] = Job(
        id="job_old",
        service_id="documentos",
        config={},
        status=JobStatus.COMPLETED,
        created_at=time.time() - 99999,
        finished_at=time.time() - 99999,
    )

    prev = cleanup.preview(mgr)
    assert prev["total_files"] >= 2
    keys = {b["key"] for b in prev["buckets"]}
    assert "job_dirs" in keys
    assert "screenshots" in keys

    out = cleanup.run_cleanup(mgr, job_dirs=True, screenshots=True)
    assert out["deleted_files"] >= 2
    assert not old.exists()
    assert active.exists()
    assert not (shots / "sessao_erro_1.png").exists()
