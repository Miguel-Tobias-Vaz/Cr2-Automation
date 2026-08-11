"""Testes de auth, reorder e timeout."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.jobs import Job, JobManager, JobStatus
from backend.main import app
from backend.state import jobs


@pytest.fixture
def auth_users(monkeypatch):
    monkeypatch.delenv("OPTO_SUPABASE_URL", raising=False)
    monkeypatch.delenv("OPTO_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("OPTO_LOCAL", raising=False)
    monkeypatch.setenv("OPTO_REQUIRE_AUTH", "1")
    monkeypatch.setenv("OPTO_USERS", "admin:secret:admin,maria:123:user")
    monkeypatch.setattr(auth, "USERS_FILE", auth.AUTH_DIR / "users.test.json")
    auth.reload_users()
    yield
    monkeypatch.delenv("OPTO_USERS", raising=False)
    monkeypatch.delenv("OPTO_REQUIRE_AUTH", raising=False)
    auth.reload_users()


@pytest.fixture
def api_client(auth_users):
    jobs._jobs.clear()
    jobs._persist_enabled = False
    with TestClient(app) as client:
        yield client
    jobs._jobs.clear()
    jobs._persist_enabled = True


def _auth_header(username: str, password: str) -> dict[str, str]:
    sess = auth.login(username, password)
    assert sess is not None
    return {"Authorization": f"Bearer {sess.token}"}


def test_api_jobs_requires_auth(api_client):
    r = api_client.get("/api/jobs")
    assert r.status_code == 401


def test_api_queue_requires_auth(api_client):
    r = api_client.get("/api/queue")
    assert r.status_code == 401


def test_api_jobs_isolation(api_client):
    j_maria = Job(id="m1", service_id="documentos", config={}, owner="maria")
    j_joao = Job(id="j1", service_id="normas", config={}, owner="joao")
    jobs._jobs[j_maria.id] = j_maria
    jobs._jobs[j_joao.id] = j_joao

    r = api_client.get("/api/jobs", headers=_auth_header("maria", "123"))
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()}
    assert ids == {"m1"}


def test_api_queue_admin_sees_all(api_client, monkeypatch):
    monkeypatch.setenv("OPTO_PRINCIPAL_ADMIN", "admin")
    j_maria = Job(id="m1", service_id="documentos", config={}, owner="maria")
    j_maria.status = JobStatus.RUNNING
    j_joao = Job(id="j1", service_id="normas", config={}, owner="joao")
    j_joao.status = JobStatus.PENDING
    j_joao.queue_rank = 1
    jobs._jobs[j_maria.id] = j_maria
    jobs._jobs[j_joao.id] = j_joao

    r = api_client.get("/api/queue", headers=_auth_header("admin", "secret"))
    assert r.status_code == 200
    data = r.json()
    assert data["running"] == 1
    assert data["pending"] == 1


def test_api_health_anonymous_minimal(api_client):
    j = Job(id="x1", service_id="documentos", config={}, owner="maria")
    j.status = JobStatus.RUNNING
    jobs._jobs[j.id] = j

    r = api_client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["auth_required"] is True
    assert "queue" not in data


def test_logs_stream_requires_auth(api_client):
    j = Job(id="s1", service_id="documentos", config={}, owner="maria")
    jobs._jobs[j.id] = j
    r = api_client.get("/api/jobs/s1/logs/stream")
    assert r.status_code == 401


def test_logs_stream_token_query(api_client):
    j = Job(id="s1", service_id="documentos", config={}, owner="maria")
    j.status = JobStatus.COMPLETED
    jobs._jobs[j.id] = j
    sess = auth.login("maria", "123")
    assert sess is not None
    with api_client.stream(
        "GET",
        f"/api/jobs/s1/logs/stream?access_token={sess.token}",
    ) as r:
        assert r.status_code == 200


def test_logs_stream_forbidden_other_user(api_client):
    j = Job(id="s1", service_id="documentos", config={}, owner="joao")
    jobs._jobs[j.id] = j
    r = api_client.get("/api/jobs/s1/logs/stream", headers=_auth_header("maria", "123"))
    assert r.status_code == 403


def test_milagre_status_requires_auth(api_client):
    r = api_client.get("/api/status")
    assert r.status_code == 401


def test_fail_closed_without_auth(monkeypatch):
    monkeypatch.delenv("OPTO_SUPABASE_URL", raising=False)
    monkeypatch.delenv("OPTO_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("OPTO_USERS", raising=False)
    monkeypatch.delenv("OPTO_LOCAL", raising=False)
    monkeypatch.setenv("OPTO_REQUIRE_AUTH", "1")
    monkeypatch.setattr(auth, "USERS_FILE", auth.AUTH_DIR / "users.test-empty.json")
    auth.reload_users()
    jobs._persist_enabled = False
    with TestClient(app) as client:
        r = client.get("/api/jobs")
        assert r.status_code == 503
    jobs._persist_enabled = True
    auth.reload_users()


def test_queue_snapshot_for_user():
    mgr = JobManager()
    mgr._persist_enabled = False

    j_m = Job(id="m1", service_id="documentos", config={}, owner="maria")
    j_m.status = JobStatus.RUNNING
    j_j = Job(id="j1", service_id="normas", config={}, owner="joao")
    j_j.status = JobStatus.PENDING
    j_j.queue_rank = 1
    mgr._jobs[j_m.id] = j_m
    mgr._jobs[j_j.id] = j_j

    snap = mgr.queue_snapshot_for_user("maria", is_admin=False)
    assert snap["running"] == 1
    assert snap["pending"] == 0
    assert {x["id"] for x in snap["running_jobs"]} == {"m1"}


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


def test_list_downloads_ready_somente_dono():
    mgr = JobManager()
    mgr._persist_enabled = False

    j_a = Job(id="a1", service_id="categorias", config={}, owner="maria@test.com")
    j_a.status = JobStatus.COMPLETED
    j_a.result["zip"] = "/tmp/a.zip"

    j_b = Job(id="b1", service_id="normas", config={}, owner="joao@test.com")
    j_b.status = JobStatus.COMPLETED
    j_b.result["zip"] = "/tmp/b.zip"

    j_orfa = Job(id="c1", service_id="documentos", config={}, owner=None)
    j_orfa.status = JobStatus.COMPLETED
    j_orfa.result["zip"] = "/tmp/c.zip"

    mgr._jobs = {j.id: j for j in (j_a, j_b, j_orfa)}

    maria = mgr.list_downloads_ready("maria@test.com")
    assert [x["id"] for x in maria] == ["a1"]

    joao = mgr.list_downloads_ready("joao@test.com")
    assert [x["id"] for x in joao] == ["b1"]

    local = mgr.list_downloads_ready(None)
    assert [x["id"] for x in local] == ["c1"]


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
