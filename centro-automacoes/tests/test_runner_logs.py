"""Logs de runners paralelos não devem se misturar."""

from __future__ import annotations

import sys
import threading
import time

from backend.runners.base import _ensure_thread_dispatch_streams, _log_tls, _Tee


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
