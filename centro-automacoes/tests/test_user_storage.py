"""Testes: pastas por usuário, upload e ZIP de saída."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from backend.job_output import build_download_zip
from backend.jobs import Job, JobStatus
from backend.user_storage import (
    apply_user_defaults,
    save_upload,
    workspace_info,
)


@pytest.fixture
def users_root(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.user_storage.USERS_ROOT", tmp_path / "users")
    return tmp_path / "users"


def test_workspace_cria_pastas(users_root):
    info = workspace_info("maria")
    assert info["username"] == "maria"
    assert Path(info["output_dir"]).is_dir()
    assert Path(info["uploads_dir"]).is_dir()


def test_apply_user_defaults_substitui_c_downloads(users_root):
    cfg = apply_user_defaults({"pasta_base": r"C:\Downloads"}, "joao")
    out = Path(cfg["pasta_base"])
    assert out.is_dir()
    assert "joao" in str(out)


def test_save_upload_xlsx(users_root):
    data = b"PK\x03\x04fake"
    meta = save_upload("ana", "planilha.xlsx", data)
    assert Path(meta["path"]).is_file()
    assert meta["filename"] == "planilha.xlsx"


def test_save_upload_zip_extract(users_root):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Repasses/dados.pdf", b"%PDF-1.4 test")
        zf.writestr("Repasses.xlsx", b"PK\x03\x04x")
    meta = save_upload("ana", "entrada.zip", buf.getvalue(), extract=True)
    assert meta.get("extracted_dir")
    assert Path(meta["suggested_pasta_base"]).is_dir()
    assert meta["extracted_files"] == 2


def test_build_download_zip_pasta(users_root, tmp_path):
    pasta = tmp_path / "saida"
    pasta.mkdir()
    (pasta / "a.txt").write_text("ok", encoding="utf-8")
    job = Job(id="abc123", service_id="documentos", config={})
    job.status = JobStatus.COMPLETED
    job.result["pasta"] = str(pasta)
    dest = build_download_zip(job)
    assert dest and dest.is_file()
    assert job.result.get("zip")
