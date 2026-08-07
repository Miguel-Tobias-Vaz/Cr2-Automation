"""Testes de persistência da fila."""

from __future__ import annotations

import json
import time

import pytest

from backend.jobs import JobManager, JobStatus
from backend import queue_store


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    data = tmp_path / "jobs"
    monkeypatch.setattr("backend.jobs.DATA", data)
    monkeypatch.setattr(queue_store, "DATA", data)
    monkeypatch.setattr(queue_store, "QUEUE_FILE", data / "queue_state.json")
    m = JobManager()
    m._persist_enabled = True
    return m


def test_save_and_restore_pending(mgr):
    def runner(job):
        time.sleep(0.2)

    hold = __import__("threading").Event()
    hold.clear()

    def slow(job):
        hold.wait(timeout=2)

    for _ in range(mgr.MAX_ATIVOS):
        mgr.enqueue("documentos", {"a": 1}, slow)
    j = mgr.enqueue("normas", {"b": 2}, runner)
    assert j.status == JobStatus.PENDING
    queue_store.save(mgr)

    mgr2 = JobManager()
    mgr2._persist_enabled = True
    n = queue_store.restore(mgr2)
    assert n == mgr.MAX_ATIVOS + 1
    assert mgr2.get(j.id) is not None
    assert mgr2.get(j.id).status == JobStatus.PENDING
    assert mgr2.get(j.id).config.get("b") == 2

    hold.set()
    time.sleep(0.3)


def test_running_becomes_pending_on_restore(mgr):
    job = mgr.create("licitacoes", {"x": 1})
    queue_store.save_runtime_config(job)
    job.status = JobStatus.RUNNING
    job.started_at = time.time()
    mgr._jobs[job.id] = job
    queue_store.save(mgr)

    mgr2 = JobManager()
    mgr2._persist_enabled = True
    n = queue_store.restore(mgr2)
    assert n == 1
    restored = mgr2.get(job.id)
    assert restored.status == JobStatus.PENDING
    assert restored.started_at is None


def test_runtime_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(queue_store, "DATA", tmp_path / "jobs")
    jid = "abc123"
    (tmp_path / "jobs" / jid).mkdir(parents=True)
    cfg = {"usuario": "u", "senha": "secret"}
    path = tmp_path / "jobs" / jid / "runtime.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    loaded = queue_store.load_runtime_config(jid)
    assert loaded == cfg
