"""Logs de runners paralelos não devem se misturar."""

from __future__ import annotations

import sys
import threading
import time

from backend.runners.base import (
    _ensure_thread_dispatch_streams,
    _log_tls,
    _Tee,
    bind_job_log_tee,
    _job_tee_lock,
)


def test_parallel_stdout_per_thread():
    _ensure_thread_dispatch_streams()
    got_a: list[str] = []
    got_b: list[str] = []
    barrier = threading.Barrier(2)

    def worker(lines: list[str], label: str) -> None:
        tee = _Tee(sys.__stdout__, lines.append, echo=False)
        _log_tls.tee_out = tee
        barrier.wait()
        for i in range(30):
            print("{0}-{1}".format(label, i))
        tee.flush()
        _log_tls.tee_out = None

    ta = threading.Thread(target=worker, args=(got_a, "A"))
    tb = threading.Thread(target=worker, args=(got_b, "B"))
    ta.start()
    tb.start()
    ta.join(timeout=5)
    tb.join(timeout=5)

    assert ta.is_alive() is False and tb.is_alive() is False
    assert got_a and got_b
    assert all(line.startswith("A-") for line in got_a)
    assert all(line.startswith("B-") for line in got_b)
    assert not any(line.startswith("B-") for line in got_a)
    assert not any(line.startswith("A-") for line in got_b)


def test_worker_thread_inherits_job_tee():
    """ThreadPool sem inherit explícito ainda deve ecoar no Tee do job."""
    import backend.runners.base as base
    from backend.runners.base import _ThreadDispatchStream, inherit_job_log_tee

    got: list[str] = []
    tee = _Tee(sys.__stdout__, got.append, echo=False)
    prev_out = getattr(base, "_job_tee_out", None)
    prev_err = getattr(base, "_job_tee_err", None)
    prev_tls = getattr(_log_tls, "tee_out", None)
    try:
        bind_job_log_tee(tee, None)
        _log_tls.tee_out = None  # simula worker nova
        stream = _ThreadDispatchStream(stderr=False)

        def worker():
            stream.write("from-worker-ok\n")
            stream.flush()
            inherit_job_log_tee()  # no-op se o write já herdou

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5)
        assert t.is_alive() is False
        assert any("from-worker-ok" in line for line in got)
    finally:
        _log_tls.tee_out = prev_tls
        with _job_tee_lock:
            base._job_tee_out = prev_out
            base._job_tee_err = prev_err
