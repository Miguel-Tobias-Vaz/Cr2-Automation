"""Progresso do job — não marcar 100% antes de concluir."""

from __future__ import annotations

from backend.jobs import Job, JobManager, JobStatus
from backend.runners.base import _atualizar_progresso_do_log


def test_progress_percent_caps_at_99_while_running():
    job = Job(id="x", service_id="licitacoes", config={})
    job.status = JobStatus.RUNNING
    job.set_progress(done=40, total=40)
    assert job.progress_percent == 99

    job.status = JobStatus.COMPLETED
    assert job.progress_percent == 100


def test_progress_ignores_smaller_total_after_queue_established():
    job = Job(id="y", service_id="publicacao", config={})
    job.set_progress(total=40)
    _atualizar_progresso_do_log(job, "    [2/2] Segunda publicacao (workaround)...")
    assert job.progress_total == 40
    assert job.progress_done == 0

    _atualizar_progresso_do_log(job, "[10/40 · 25%] Licitação exemplo")
    assert job.progress_done == 10
    assert job.progress_total == 40


def test_progress_ignores_collection_total_inside_sentence():
    """Extração Pro logava 'posts novos. Total: N' e a barra travava em 0/N."""
    job = Job(id="n", service_id="normas", config={})
    _atualizar_progresso_do_log(job, "  12 posts novos. Total: 45")
    assert job.progress_total == 0
    assert job.progress_done == 0

    _atualizar_progresso_do_log(job, "  Portarias na fila: 001/2025, 002/2025")
    assert job.progress_total == 0

    _atualizar_progresso_do_log(job, "[001/12] lei-ordinaria-n-1-2024")
    assert job.progress_done == 1
    assert job.progress_total == 12


def test_progress_reads_standalone_total_line():
    job = Job(id="p", service_id="publicacao", config={})
    _atualizar_progresso_do_log(job, "  Total: 40")
    assert job.progress_total == 40
    assert job.progress_done == 0


def test_progress_reads_normas_post_counter():
    job = Job(id="n2", service_id="normas", config={})
    _atualizar_progresso_do_log(job, "[001/187] algum-post")
    assert job.progress_done == 1
    assert job.progress_total == 187
    _atualizar_progresso_do_log(job, "[010/187] outro-post")
    assert job.progress_done == 10


def test_user_jobs_for_owner_lists_all_running():
    mgr = JobManager()
    mgr._persist_enabled = False

    j1 = mgr.create("documentos", {})
    j1.owner = "u1"
    j1.status = JobStatus.RUNNING
    mgr._jobs[j1.id] = j1

    j2 = mgr.create("licitacoes", {})
    j2.owner = "u1"
    j2.status = JobStatus.RUNNING
    mgr._jobs[j2.id] = j2

    assert len(mgr.user_jobs_for_owner("u1")) == 2
    assert mgr.user_job_for_owner("u1", "documentos").id == j1.id
