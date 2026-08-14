"""Regras de organização de sessão (download-normas)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "automacoes" / "download-normas" / "organizar_sessao.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("organizar_sessao", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_link_indica_sessao_pautas_atas():
    mod = _load_mod()
    assert mod.link_indica_sessao(
        "https://camara.example/c/atividades-legislativas/pautas-e-atas-das-sessoes/"
    )
    assert mod.link_indica_sessao("https://example.org/arquivos/pauta-011-2023.pdf")
    assert mod.link_indica_sessao("https://example.org/download/ata-018.pdf")


def test_link_indica_sessao_portarias_nao():
    mod = _load_mod()
    assert not mod.link_indica_sessao(
        "https://inhangapi.pa.gov.br/c/publicacoes/portarias/"
    )
    assert not mod.link_indica_sessao(
        "https://example.org/c/publicacoes/portarias/portaria-n-010-2025.pdf"
    )


def test_organizar_destino_sessao_respeita_link():
    mod = _load_mod()
    titulo_ata = "ATA Nº 018 DA SESSÃO ORDINÁRIA, DE 16 DE NOVEMBRO DE 2023"
    url_portarias = "https://example.org/c/publicacoes/portarias/"
    org = mod.organizar_destino_sessao(
        pasta_base="/tmp/out",
        pasta_hint="Camara",
        ano_fallback=2023,
        textos=[titulo_ata, titulo_ata],
        url_fonte=url_portarias,
        url_pdf="https://example.org/files/doc.pdf",
    )
    assert org is None

    org_ok = mod.organizar_destino_sessao(
        pasta_base="/tmp/out",
        pasta_hint="Camara",
        ano_fallback=2023,
        textos=[titulo_ata, titulo_ata],
        url_fonte="https://example.org/pautas-e-atas-das-sessoes/",
        url_pdf="https://example.org/files/doc.pdf",
    )
    assert org_ok is not None
    assert org_ok["meta"]["doc_tipo"] == "ata"


def test_extrair_periodo_legislativo_qualquer_numero():
    mod = _load_mod()
    assert mod._extrair_periodo_legislativo("PAUTA 13ª SESSÃO - 4º PERÍODO") == "4º Período"
    assert mod._extrair_periodo_legislativo("quarto período legislativo") == "4º Período"
    assert mod._extrair_periodo_legislativo("IV período legislativo") == "4º Período"
    assert mod._extrair_periodo_legislativo("5º período") == "5º Período"


def test_nome_pasta_sessao_separa_periodos():
    mod = _load_mod()
    base = {
        "numero": 13,
        "tipo": "Ordinária",
        "evento": "",
        "data": "03-11-2023",
        "doc_tipo": "pauta",
        "doc_nome": "Pauta",
    }
    p1 = dict(base, periodo="1º Período")
    p2 = dict(base, periodo="2º Período")
    n1 = mod.nome_pasta_sessao(p1)
    n2 = mod.nome_pasta_sessao(p2)
    assert n1 != n2
    assert "1" in n1 and "2" in n2


def test_resolver_dir_sessao_mesmo_numero_datas_diferentes(tmp_path):
    """Jacareacanga: 1ª Ordinária de fev ≠ 1ª Ordinária de jun."""
    mod = _load_mod()
    ano = tmp_path / "2023"
    ano.mkdir()
    meta_fev = {
        "numero": 1,
        "tipo": "Ordinária",
        "evento": "",
        "data": "17-02-2023",
        "doc_tipo": "pauta",
        "doc_nome": "Pauta",
    }
    meta_jun = dict(meta_fev, data="02-06-2023", doc_tipo="ata", doc_nome="Ata")
    p_fev = mod.resolver_dir_sessao(ano, meta_fev)
    p_fev.mkdir(parents=True, exist_ok=True)
    (p_fev / "Pauta.pdf").write_bytes(b"x")
    p_jun = mod.resolver_dir_sessao(ano, meta_jun)
    assert p_fev != p_jun
    assert "17-02-2023" in p_fev.name
    assert "02-06-2023" in p_jun.name
    dest, arq = mod._destino_arquivo_sessao(p_jun, meta_jun, pasta_ano=ano)
    assert dest == p_jun
    assert arq == "Ata.pdf"
    assert "Verificar" not in str(dest)


def test_resolver_dir_sessao_nao_mistura_periodos(tmp_path):
    mod = _load_mod()
    ano = tmp_path / "2023"
    ano.mkdir()
    meta1 = {
        "numero": 13,
        "tipo": "Ordinária",
        "evento": "",
        "data": "03-11-2023",
        "periodo": "1º Período",
        "doc_tipo": "pauta",
        "doc_nome": "Pauta",
    }
    meta2 = dict(meta1, periodo="2º Período")
    meta4 = dict(meta1, periodo="4º Período")
    p1 = mod.resolver_dir_sessao(ano, meta1)
    p2 = mod.resolver_dir_sessao(ano, meta2)
    p4 = mod.resolver_dir_sessao(ano, meta4)
    assert p1 != p2 != p4
    assert mod._periodo_na_pasta(p1.name) == "1º Período"
    assert mod._periodo_na_pasta(p2.name) == "2º Período"
    assert mod._periodo_na_pasta(p4.name) == "4º Período"
