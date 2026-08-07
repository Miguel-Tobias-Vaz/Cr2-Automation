"""Testes de auth, reorder e timeout."""

from __future__ import annotations

import os
import time

import pytest

from backend import auth
from backend.jobs import JobManager, JobStatus


@pytest.fixture
def auth_users(monkeypatch):
    monkeypatch.delenv("OPTO_SUPABASE_URL", raising=False)
    monkeypatch.delenv("OPTO_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setenv("OPTO_USERS", "admin:secret:admin,maria:123:user")
    monkeypatch.setattr(auth, "USERS_FILE", auth.AUTH_DIR / "users.test.json")
    auth.reload_users()
    yield
    monkeypatch.delenv("OPTO_USERS", raising=False)
    auth.reload_users()


def test_auth_login(auth_users):
    assert auth.is_enabled()
    sess = auth.login("maria", "123")
    assert sess is not None
    assert sess.username == "maria"
    assert auth.session_from_token(sess.token) is not None
    assert auth.login("maria", "wrong") is None


def test_can_cancel_job(auth_users):
    auth.reload_users()
    sess = auth.login("maria", "123")
    admin = auth.login("admin", "secret")
    assert auth.can_cancel_job(sess, "maria")
    assert not auth.can_cancel_job(sess, "joao")
    assert auth.can_cancel_job(admin, "joao")


def test_reorder_pending():
    mgr = JobManager()
    mgr._persist_enabled = False

    def runner(job):
        time.sleep(0.05)

    hold = __import__("threading").Event()
    hold.clear()

    def slow(job):
        hold.wait(timeout=2)

    for _ in range(mgr.MAX_ATIVOS):
        mgr.enqueue("documentos", {}, slow, owner="a")
    j1 = mgr.enqueue("normas", {}, runner, owner="b")
    j2 = mgr.enqueue("licitacoes", {}, runner, owner="c")
    time.sleep(0.05)
    assert mgr.pending_count() == 2
    final = mgr.reorder_pending([j2.id, j1.id])
    assert final[0] == j2.id
    pending = mgr._pending_jobs_locked()
    assert pending[0].id == j2.id
    hold.set()
    time.sleep(0.3)


def test_user_job_for_owner():
    mgr = JobManager()
    mgr._persist_enabled = False

    j_run = mgr.create("documentos", {})
    j_run.owner = "maria"
    j_run.status = JobStatus.RUNNING
    mgr._jobs[j_run.id] = j_run

    j_pen = mgr.create("normas", {})
    j_pen.owner = "maria"
    j_pen.status = JobStatus.PENDING
    j_pen.queue_rank = 1
    mgr._jobs[j_pen.id] = j_pen

    assert mgr.user_job_for_owner("maria").id == j_run.id
    assert mgr.user_job_for_owner("joao") is None

    j_run.status = JobStatus.COMPLETED
    assert mgr.user_job_for_owner("maria").id == j_pen.id


def test_user_job_for_owner_by_service():
    mgr = JobManager()
    mgr._persist_enabled = False

    j_doc = mgr.create("documentos", {})
    j_doc.owner = "maria"
    j_doc.status = JobStatus.RUNNING
    mgr._jobs[j_doc.id] = j_doc

    j_lic = mgr.create("licitacoes", {})
    j_lic.owner = "maria"
    j_lic.status = JobStatus.RUNNING
    mgr._jobs[j_lic.id] = j_lic

    assert mgr.user_job_for_owner("maria", "documentos").id == j_doc.id
    assert mgr.user_job_for_owner("maria", "licitacoes").id == j_lic.id
    assert mgr.user_job_for_owner("maria", "normas") is None
    assert len(mgr.user_jobs_for_owner("maria")) == 2


def test_timeout_marks_job(monkeypatch):
    monkeypatch.setattr("backend.jobs.JOB_TIMEOUT_S", 1)
    mgr = JobManager()
    mgr._persist_enabled = False
    mgr._timeout_stop.set()

    def slow(job):
        time.sleep(3)

    job = mgr.create("documentos", {})
    job.status = JobStatus.RUNNING
    job.started_at = time.time() - 5
    mgr._jobs[job.id] = job
    mgr._apply_timeout(job)
    assert job.timed_out
    assert job.cancel_requested
