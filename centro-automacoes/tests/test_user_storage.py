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
    delete_workspace_path,
    detect_publicacao_folders,
    list_workspace_files,
    mkdir_workspace,
    output_publicacao_hints,
    resolve_user_path,
    save_upload,
    workspace_info,
)
from backend.user_storage import _match_publicacao_key


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


def test_apply_user_defaults_pasta_sessoes(users_root):
    cfg = apply_user_defaults(
        {"pasta_sessoes": r"C:\Users\x\sessoes"},
        "joao",
        service_id="sessao",
    )
    out = Path(cfg["pasta_sessoes"])
    assert out.is_dir()
    assert out.name == "sessao"
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


def test_save_upload_zip_publicacao_folders(users_root):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("RGF/2023/doc.pdf", b"%PDF")
        zf.writestr("RREO/2023/doc.pdf", b"%PDF")
        zf.writestr("Balancete/x.pdf", b"%PDF")
    meta = save_upload("ana", "pub.zip", buf.getvalue(), extract=True)
    pub = meta.get("suggested_publicacao") or {}
    assert "pasta_rgf" in pub
    assert "pasta_rreo" in pub
    assert "pasta_balancete" in pub
    assert Path(pub["pasta_rgf"]).is_dir()


def test_detect_publicacao_folders(users_root, tmp_path):
    base = tmp_path / "extracted"
    (base / "Relatório de Gestão Fiscal (RGF)" / "2023").mkdir(parents=True)
    (base / "Relatório RREO").mkdir(parents=True)
    found = detect_publicacao_folders(base)
    assert "pasta_rgf" in found
    assert "pasta_rreo" in found


def test_apply_user_defaults_publicacao_nao_preenche_tudo(users_root):
    cfg = apply_user_defaults(
        {"pasta_rgf": r"C:\Downloads", "pasta_rreo": ""},
        "joao",
        service_id="publicacao",
    )
    assert cfg["pasta_rgf"] == ""
    assert cfg["pasta_rreo"] == ""


def test_list_workspace_files(users_root):
    info = workspace_info("ana")
    uploads = Path(info["uploads_dir"])
    (uploads / "teste.pdf").write_bytes(b"x")
    data = list_workspace_files("ana", "uploads")
    names = [e["name"] for e in data["entries"]]
    assert "teste.pdf" in names


def test_resolve_user_path_bloqueia_traversal(users_root):
    root = resolve_user_path("ana", "")
    escaped = resolve_user_path("ana", "../../../windows/system32")
    assert str(escaped).startswith(str(root))
    assert ".." not in escaped.parts


def test_output_publicacao_hints(users_root):
    out = workspace_info("ana")["output_dir"]
    rgf = Path(out) / "documentos" / "Relatório RREO" / "2023"
    rgf.mkdir(parents=True)
    hints = output_publicacao_hints("ana")
    assert hints.get("pasta_rreo")


def test_mkdir_and_delete_workspace(users_root):
    mkdir_workspace("ana", "uploads/nova")
    data = list_workspace_files("ana", "uploads")
    assert any(e["name"] == "nova" for e in data["entries"])
    delete_workspace_path("ana", "uploads/nova")
    data2 = list_workspace_files("ana", "uploads")
    assert not any(e["name"] == "nova" for e in data2["entries"])


def test_match_publicacao_balancete_nao_vira_balanco(users_root):
    assert _match_publicacao_key("Balancete Financeiro") == "pasta_balancete"
    assert _match_publicacao_key("Balanço e Relatórios Anuais") == "pasta_balanco"


def test_delete_workspace_bloqueia_jobs(users_root):
    info = workspace_info("ana")
    jobs = Path(info["jobs_dir"])
    marker = jobs / "keep.txt"
    marker.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="jobs"):
        delete_workspace_path("ana", "jobs/keep.txt")


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
