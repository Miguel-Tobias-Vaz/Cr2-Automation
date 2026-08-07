"""Testes da fila de jobs."""

from __future__ import annotations

import threading
import time

import pytest

from backend.config import MAX_CONCURRENT, MAX_QUEUE
from backend.jobs import JobManager, JobStatus, QueueFullError


@pytest.fixture
def mgr():
    return JobManager()


def test_max_concurrent_default():
    assert MAX_CONCURRENT >= 4
    assert MAX_QUEUE >= MAX_CONCURRENT


def test_enqueue_starts_up_to_max(mgr):
    hold = threading.Event()

    def runner(job):
        hold.wait(timeout=3)
        time.sleep(0.02)

    for _ in range(MAX_CONCURRENT + 2):
        mgr.enqueue("documentos", {}, runner)

    time.sleep(0.08)
    assert mgr.running_count() == MAX_CONCURRENT
    assert mgr.pending_count() == 2

    hold.set()
    time.sleep(0.5)
    assert mgr.pending_count() == 0
    assert mgr.ativos() == 0


def test_cancel_pending(mgr):
    hold = threading.Event()

    def runner(job):
        hold.wait(timeout=3)
        time.sleep(0.02)

    for _ in range(MAX_CONCURRENT):
        mgr.enqueue("documentos", {}, runner)
    pending_job = mgr.enqueue("documentos", {}, runner)
    time.sleep(0.08)
    assert pending_job.status == JobStatus.PENDING
    mgr.cancel(pending_job.id)
    assert mgr.get(pending_job.id).status == JobStatus.CANCELLED
    hold.set()
    time.sleep(0.4)


def test_queue_position(mgr):
    hold = threading.Event()

    def runner(job):
        hold.wait(timeout=3)
        time.sleep(0.02)

    for _ in range(MAX_CONCURRENT + 1):
        mgr.enqueue("normas", {}, runner)

    time.sleep(0.08)
    assert mgr.pending_count() == 1
    pending = [j for j in mgr._jobs.values() if j.status == JobStatus.PENDING]
    pos = mgr.queue_position(pending[0].id)
    assert pos == 1
    hold.set()
    time.sleep(0.4)


def test_queue_full_raises():
    mgr = JobManager()
    mgr.MAX_QUEUE = 2

    def runner(job):
        time.sleep(0.3)

    mgr.enqueue("documentos", {}, runner)
    mgr.enqueue("documentos", {}, runner)
    with pytest.raises(QueueFullError):
        mgr.enqueue("documentos", {}, runner)

    time.sleep(0.35)


def test_dispatch_after_complete(mgr):
    done: list[str] = []

    def runner(job):
        done.append(job.id)
        time.sleep(0.04)

    for _ in range(3):
        mgr.enqueue("categorias", {}, runner)

    time.sleep(0.35)
    assert len(done) == 3
