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
