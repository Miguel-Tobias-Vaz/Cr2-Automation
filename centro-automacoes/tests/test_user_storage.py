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


def test_apply_user_defaults_subpasta_por_servico(users_root):
    cfg = apply_user_defaults({"pasta_base": r"C:\Downloads"}, "joao", service_id="normas")
    out = Path(cfg["pasta_base"])
    assert out.is_dir()
    assert out.name == "normas"
    assert "joao" in str(out)


def test_apply_user_defaults_bloqueia_pasta_de_outro_usuario(users_root):
    other = users_root / "maria" / "output" / "normas"
    other.mkdir(parents=True)
    cfg = apply_user_defaults(
        {"pasta_base": str(other)},
        "joao",
        service_id="licitacoes",
    )
    out = Path(cfg["pasta_base"])
    assert "joao" in str(out)
    assert "licitacoes" in str(out)
    assert "maria" not in str(out)


def test_apply_user_defaults_reescreve_output_raiz(users_root):
    joao_out = users_root / "joao" / "output"
    joao_out.mkdir(parents=True)
    cfg = apply_user_defaults(
        {"pasta_base": str(joao_out)},
        "joao",
        service_id="normas",
    )
    out = Path(cfg["pasta_base"])
    assert out.name == "normas"


def test_job_dir_por_usuario(users_root, monkeypatch):
    from backend.job_paths import find_job_dir
    from backend.jobs import Job

    monkeypatch.setattr("backend.user_storage.USERS_ROOT", users_root)
    job = Job(id="abc999", service_id="normas", config={}, owner="maria@test.com")
    d = job.dir
    assert d.is_dir()
    assert "maria" in str(d) or "maria_test.com" in str(d)
    assert find_job_dir("abc999", "maria@test.com") == d


def test_build_download_zip_nao_mistura_pasta_compartilhada(users_root, tmp_path):
    """ZIP na pasta output compartilhada inclui só arquivos deste job (mtime)."""
    import os
    import time

    shared = tmp_path / "users" / "ana" / "output"
    shared.mkdir(parents=True)
    old = shared / "Licitacoes" / "antigo.pdf"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    old_time = time.time() - 3600
    os.utime(old, (old_time, old_time))

    new = shared / "Normas" / "novo.pdf"
    new.parent.mkdir(parents=True)
    new.write_bytes(b"new")

    job = Job(id="job1", service_id="normas", config={"_workspace": {"output_dir": str(shared)}})
    job.status = JobStatus.COMPLETED
    job.started_at = time.time() - 60
    job.result["pasta"] = str(shared)
    job.result["planilha_normas"] = str(shared / "Normas.xlsx")
    (shared / "Normas.xlsx").write_text("x", encoding="utf-8")

    dest = build_download_zip(job)
    assert dest and dest.is_file()
    with zipfile.ZipFile(dest, "r") as zf:
        names = zf.namelist()
    assert any("novo.pdf" in n for n in names)
    assert not any("antigo.pdf" in n for n in names)


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
