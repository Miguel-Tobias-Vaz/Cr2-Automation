"""Testes de subprocesso isolado (Playwright)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.config import BROWSER_SERVICES, USE_SUBPROCESS
from backend.runners.isolated import _handle_worker_line, uses_subprocess
from backend.worker_job import WorkerJob


def test_browser_services_defined():
    assert "publicacao" in BROWSER_SERVICES
    assert "sessao" in BROWSER_SERVICES
    assert "pub_repasses" in BROWSER_SERVICES
    assert "contratos" in BROWSER_SERVICES
    assert "dic_est_ter" in BROWSER_SERVICES
    assert "licitacoes" not in BROWSER_SERVICES


def test_uses_subprocess():
    assert uses_subprocess("publicacao") is USE_SUBPROCESS
    assert uses_subprocess("normas") is False


def test_worker_job_emit_ndjson(capsys):
    job = WorkerJob("abc", "publicacao", {}, Path("."))
    job.emit("info", "teste")
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["op"] == "log"
    assert data["msg"] == "teste"


def test_worker_job_has_owner(tmp_path):
    job = WorkerJob("abc", "publicacao", {}, tmp_path, owner="user@example.com")
    assert job.owner == "user@example.com"
    job2 = WorkerJob("abc", "publicacao", {}, tmp_path)
    assert job2.owner is None


def test_handle_worker_line_parses_progress():
    class FakeJob:
        def __init__(self):
            self.progress = {}

        def emit(self, level, msg):
            pass

        def set_progress(self, done=None, total=None, label=None):
            self.progress = {"done": done, "total": total, "label": label}

    job = FakeJob()
    line = json.dumps(
        {"op": "progress", "done": 2, "total": 10, "percent": 20, "label": "ok"}
    )
    _handle_worker_line(job, line, set())
    assert job.progress["done"] == 2
    assert job.progress["total"] == 10


def test_isolated_root_is_centro_automacoes():
    from backend.runners.isolated import ROOT

    assert (ROOT / "backend" / "job_worker.py").is_file()
    assert ROOT.name == "centro-automacoes"


def test_job_worker_module_importable():
    from backend.runners.isolated import ROOT

    r = subprocess.run(
        [sys.executable, "-m", "backend.job_worker"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    assert "Uso:" in r.stderr or "Uso:" in r.stdout
    assert "No module named" not in (r.stderr or "")
    assert "No module named" not in (r.stdout or "")
