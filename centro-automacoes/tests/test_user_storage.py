"""Testes: pastas por usuário, upload e ZIP de saída."""

from __future__ import annotations

import io
import shutil
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
    list_workspace_owners,
    mkdir_workspace,
    output_publicacao_hints,
    prepare_workspace_download,
    resolve_user_path,
    save_upload,
    workspace_info,
    ensure_owner_workspace,
)
from backend.user_storage import _match_publicacao_key


@pytest.fixture
def users_root(tmp_path, monkeypatch):
    monkeypatch.delenv("OPTO_LOCAL", raising=False)
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


def test_job_dir_por_usuario(users_root, tmp_path, monkeypatch):
    from backend.job_paths import find_job_dir
    from backend.jobs import Job

    legacy = tmp_path / "legacy_jobs"
    legacy.mkdir()
    monkeypatch.delenv("OPTO_LOCAL", raising=False)
    monkeypatch.setattr("backend.user_storage.USERS_ROOT", users_root)
    monkeypatch.setattr("backend.job_paths.USERS_ROOT", users_root)
    monkeypatch.setattr("backend.job_paths.LEGACY_JOBS_ROOT", legacy)
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


def test_list_workspace_files_pasta_com_tamanho(users_root):
    info = workspace_info("ana")
    out = Path(info["output_dir"])
    pasta = out / "licitacoes" / "Licitacao_001"
    pasta.mkdir(parents=True)
    (pasta / "a.pdf").write_bytes(b"12345")
    (pasta / "b.pdf").write_bytes(b"67890")

    data = list_workspace_files("ana", "output", include_folder_sizes=True)
    lic = next(e for e in data["entries"] if e["name"] == "licitacoes")
    assert lic["kind"] == "dir"
    assert lic.get("size") == 5 + 5

    inner = list_workspace_files("ana", "output/licitacoes", include_folder_sizes=True)
    sub = next(e for e in inner["entries"] if e["name"] == "Licitacao_001")
    assert sub.get("size") == 5 + 5


def test_workspace_folder_size(users_root):
    from backend.user_storage import workspace_folder_size

    info = workspace_info("ana")
    out = Path(info["output_dir"])
    pasta = out / "normas" / "2024"
    pasta.mkdir(parents=True)
    (pasta / "doc.pdf").write_bytes(b"x" * 100)

    data = list_workspace_files("ana", "output")
    normas = next(e for e in data["entries"] if e["name"] == "normas")
    assert normas.get("size") is None

    sized = workspace_folder_size("ana", "output/normas")
    assert sized["size"] == 100


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


def test_folder_download_plan_lotes(users_root, monkeypatch):
    import backend.user_storage as us

    monkeypatch.setattr(us, "LOTE_MAX_BYTES", 80)
    info = workspace_info("ana")
    out = Path(info["output_dir"]) / "licitacoes"
    for name in ("Licitacao_A", "Licitacao_B", "Licitacao_C"):
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "doc.pdf").write_bytes(b"x" * 40)

    from backend.user_storage import folder_download_plan

    plan = folder_download_plan("ana", "output/licitacoes")
    assert plan["mode"] == "lots"
    assert plan["lot_count"] >= 2
    seen: list[str] = []
    for lot in plan["lots"]:
        for unit in lot["units"]:
            assert unit not in seen, f"{unit} apareceu em mais de um lote"
            seen.append(unit)
    assert set(seen) == {"Licitacao_A", "Licitacao_B", "Licitacao_C"}


def test_folder_download_plan_single(users_root):
    from backend.user_storage import folder_download_plan

    info = workspace_info("ana")
    folder = Path(info["output_dir"]) / "normas"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "a.pdf").write_bytes(b"123")

    plan = folder_download_plan("ana", "output/normas")
    assert plan["mode"] == "single"
    assert plan["lot_count"] == 1
    assert len(plan["lots"]) == 1


def test_prepare_workspace_download_arquivo(users_root):
    info = workspace_info("ana")
    f = Path(info["uploads_dir"]) / "doc.pdf"
    f.write_bytes(b"%PDF-1.4")
    path, name, tmp = prepare_workspace_download("ana", "uploads/doc.pdf")
    assert path.is_file()
    assert name == "doc.pdf"
    assert tmp is None


def test_prepare_workspace_download_pasta(users_root):
    info = workspace_info("ana")
    folder = Path(info["output_dir"]) / "documentos"
    folder.mkdir(parents=True)
    (folder / "a.txt").write_text("ok", encoding="utf-8")
    (folder / "sub").mkdir()
    (folder / "sub" / "b.txt").write_text("x", encoding="utf-8")
    path, name, tmp = prepare_workspace_download("ana", "output/documentos")
    assert path.is_file()
    assert name == "documentos.zip"
    assert tmp is None
    import zipfile

    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
    assert "a.txt" in names
    assert any("sub/b.txt" in n or "sub\\b.txt" in n for n in names)


def test_prepare_workspace_download_bloqueia_jobs(users_root):
    info = workspace_info("ana")
    jobs = Path(info["jobs_dir"])
    jobs.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="jobs"):
        prepare_workspace_download("ana", "jobs")


def test_list_workspace_owners(users_root):
    workspace_info("ana")
    workspace_info("joao")
    owners = list_workspace_owners()
    ids = {o["id"] for o in owners}
    assert "ana" in ids
    assert "joao" in ids


def test_ensure_owner_workspace(users_root):
    info = workspace_info("maria@test.com")
    owner_id = ensure_owner_workspace("maria@test.com")
    assert owner_id == info["username"]
    with pytest.raises(ValueError):
        ensure_owner_workspace("nao-existe")


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


def test_build_download_zip_licitacoes_muitas_pastas(users_root, tmp_path):
    """165+ pastas de licitação preservam estrutura no ZIP."""
    import zipfile

    saida = tmp_path / "licitacoes"
    for i in range(1, 170):
        pasta = saida / f"Licitacao_{i:03d}"
        pasta.mkdir(parents=True)
        (pasta / "edital.pdf").write_bytes(b"%PDF-1.4 test")
    (saida / "subirLicitacoes.xlsx").write_bytes(b"PK\x03\x04x")

    job = Job(id="lic1", service_id="licitacoes", config={})
    job.status = JobStatus.COMPLETED
    job.result["pasta"] = str(saida)
    job.result["planilha_licitacoes"] = str(saida / "subirLicitacoes.xlsx")

    dest = build_download_zip(job)
    assert dest and dest.is_file()
    assert job.result.get("download_files", 0) >= 170
    with zipfile.ZipFile(dest, "r") as zf:
        names = zf.namelist()
    assert any("Licitacao_001/edital.pdf" in n for n in names)
    assert any(n.endswith("subirLicitacoes.xlsx") for n in names)


def test_assign_job_output_dir_per_job(users_root):
    from backend.jobs import Job
    from backend.user_storage import assign_job_output_dir

    job = Job(id="abc123", service_id="licitacoes", config={"nome_pasta": "CMBelém"})
    path = assign_job_output_dir(job, owner="ana", service_id="licitacoes")
    assert path
    assert job.config["pasta_saida"] == path
    assert job.config["pasta_base"] == path
    assert path.endswith("CMBelém") or "CMBelém" in path
    assert Path(path).is_dir()


def test_assign_job_output_dir_fallback_job_id(users_root):
    from backend.jobs import Job
    from backend.user_storage import assign_job_output_dir

    job = Job(id="abc123", service_id="licitacoes", config={})
    with pytest.raises(ValueError, match="nome da pasta"):
        assign_job_output_dir(job, owner="ana", service_id="licitacoes")


def test_sanitize_output_folder_name():
    from backend.user_storage import sanitize_output_folder_name

    assert sanitize_output_folder_name("CM BelBranco") == "CM BelBranco"
    assert sanitize_output_folder_name("  CMBelém  ") == "CMBelém"
    with pytest.raises(ValueError):
        sanitize_output_folder_name("pasta/sub")
    assert sanitize_output_folder_name("") is None
    assert sanitize_output_folder_name("   ") is None


def test_assign_job_output_dir_skips_local(users_root, monkeypatch):
    from backend.jobs import Job
    from backend.user_storage import assign_job_output_dir

    monkeypatch.setenv("OPTO_LOCAL", "1")
    job = Job(id="x1", service_id="licitacoes", config={})
    assert assign_job_output_dir(job, owner="ana", service_id="licitacoes") is None


def test_build_download_zip_isolates_subfolders_in_shared_service(tmp_path):
    """Cada job ZIP só inclui result.pasta — não a pasta compartilhada do serviço."""
    import time
    import zipfile

    output_root = tmp_path / "output"
    svc = output_root / "licitacoes"
    run_a = svc / "PM A 2023"
    run_b = svc / "PM B 2023"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)
    (run_a / "a.txt").write_text("a", encoding="utf-8")
    (run_b / "b.txt").write_text("b", encoding="utf-8")

    job = Job(
        id="iso1",
        service_id="licitacoes",
        config={
            "pasta_saida": str(svc),
            "_workspace": {"output_dir": str(output_root)},
        },
    )
    job.status = JobStatus.COMPLETED
    job.started_at = time.time() - 60
    job.finished_at = time.time()
    job.result["pasta"] = str(run_a)

    dest = build_download_zip(job)
    assert dest and dest.is_file()
    with zipfile.ZipFile(dest, "r") as zf:
        names = zf.namelist()
    assert any("a.txt" in n for n in names)
    assert not any("b.txt" in n for n in names)


def test_build_download_zip_service_folder_uses_job_time_window(tmp_path):
    """Quando result.pasta é a pasta do serviço, filtra arquivos pela janela do job."""
    import os
    import time
    import zipfile

    output_root = tmp_path / "output"
    svc = output_root / "licitacoes"
    svc.mkdir(parents=True)

    old = svc / "Licitacao_antiga"
    old.mkdir()
    velho = old / "velho.pdf"
    velho.write_bytes(b"old")
    old_mtime = time.time() - 3600
    os.utime(velho, (old_mtime, old_mtime))

    job = Job(
        id="iso2",
        service_id="licitacoes",
        config={"_workspace": {"output_dir": str(output_root)}},
    )
    job.status = JobStatus.COMPLETED
    job.started_at = time.time()
    new = svc / "Licitacao_nova"
    new.mkdir()
    (new / "novo.pdf").write_bytes(b"new")
    job.finished_at = time.time() + 1
    job.result["pasta"] = str(svc)

    dest = build_download_zip(job)
    assert dest and dest.is_file()
    with zipfile.ZipFile(dest, "r") as zf:
        names = zf.namelist()
    assert any("novo.pdf" in n for n in names)
    assert not any("velho.pdf" in n for n in names)


def test_find_job_zip_resultado(tmp_path):
    from backend.job_output import find_job_zip_file

    job_dir = tmp_path / "jobx"
    job_dir.mkdir()
    (job_dir / "resultado.zip").write_bytes(b"PK")
    found = find_job_zip_file(job_dir)
    assert found is not None
    assert found.name == "resultado.zip"


def test_disk_job_payload_detects_resultado_zip(users_root, tmp_path, monkeypatch):
    from backend.job_log import disk_job_payload, write_job_meta
    from backend.jobs import Job, JobStatus

    job = Job(id="diskzip1", service_id="normas", config={}, owner="ana")
    job.status = JobStatus.COMPLETED
    job.result["pasta"] = str(tmp_path / "out")
    (job.dir / "resultado.zip").write_bytes(b"PK\x03\x04")
    write_job_meta(job)
    payload = disk_job_payload("diskzip1", "ana")
    assert payload is not None
    assert payload["has_download"] is True
