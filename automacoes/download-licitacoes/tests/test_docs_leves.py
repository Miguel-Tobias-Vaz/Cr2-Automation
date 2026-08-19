# -*- coding: utf-8 -*-
"""Filtro docs leves: só-contrato puro, docs úteis, ordena por poucos anexos."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "script.py"


def _load():
    spec = importlib.util.spec_from_file_location("download_licitacoes_script", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(mod)
    return mod


def _lic(titulo, anexos, link="http://ex/1"):
    return {"titulo": titulo, "link": link, "anexos": anexos, "data_pub": "01/03/2023"}


def test_rejeita_so_contrato_puro():
    mod = _load()
    sel, rej = mod.filtrar_licitacoes_docs_leves([
        _lic("X", [("Contrato Nº 20230091.pdf", "http://a/c.pdf")]),
    ])
    assert sel == []
    assert rej[0]["_filtro_motivo"] == "só contrato/aditivo"


def test_aceita_pacote_com_minuta_e_contrato_firmado():
    """CR2 típico: Edital + TR + Minuta + Contrato firmado — deve entrar."""
    mod = _load()
    sel, rej = mod.filtrar_licitacoes_docs_leves([
        _lic(
            "Pregão 007/2023",
            [
                ("Edital.pdf", "http://a/e.pdf"),
                ("Termo de Referência.pdf", "http://a/tr.pdf"),
                ("Minuta de Contrato.pdf", "http://a/m.pdf"),
                ("Contrato Nº 20230091.pdf", "http://a/c.pdf"),
                ("Contrato Social.pdf", "http://a/cs.pdf"),
                ("Termo de Homologação.pdf", "http://a/h.pdf"),
            ],
            link="ok",
        ),
    ])
    assert rej == []
    assert len(sel) == 1
    assert sel[0]["link"] == "ok"


def test_aceita_sem_dfd_com_tr_edital():
    mod = _load()
    sel, rej = mod.filtrar_licitacoes_docs_leves([
        _lic(
            "Pregão",
            [
                ("Edital.pdf", "http://a/e.pdf"),
                ("Termo de Referência.pdf", "http://a/tr.pdf"),
            ],
        ),
    ])
    assert rej == []
    assert len(sel) == 1


def test_rejeita_sem_doc_util():
    mod = _load()
    sel, rej = mod.filtrar_licitacoes_docs_leves([
        _lic("X", [("Foto.jpg", "http://a/f.jpg"), ("Scan.pdf", "http://a/s.pdf")]),
    ])
    assert sel == []
    assert "sem doc útil" in rej[0]["_filtro_motivo"]


def test_ordena_por_menos_anexos():
    mod = _load()
    poucos = _lic(
        "poucos",
        [("Edital.pdf", "u1"), ("TR.pdf", "u2")],
        link="poucos",
    )
    muitos = _lic(
        "muitos",
        [
            ("Edital.pdf", "a"),
            ("Termo de Referência.pdf", "b"),
            ("Homologação.pdf", "c"),
            ("Ata.pdf", "d"),
            ("Parecer.pdf", "e"),
            ("Aviso.pdf", "f"),
        ],
        link="muitos",
    )
    sel, _ = mod.filtrar_licitacoes_docs_leves([muitos, poucos])
    assert sel[0]["link"] == "poucos"


def test_classificar_minuta_vs_contrato():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from ia_local.classificar_docs import classificar

    assert classificar("Minuta de Contrato.pdf")["tipo"] == "minuta_contrato"
    assert classificar("Contrato Social.pdf")["tipo"] == "contrato_social"
    assert classificar("Contrato Nº 20230091.pdf")["tipo"] == "contrato"
    assert classificar("Contrato - Valdair José-ass.pdf")["tipo"] == "contrato"
