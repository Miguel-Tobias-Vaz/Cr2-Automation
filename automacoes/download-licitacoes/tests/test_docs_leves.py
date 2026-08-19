# -*- coding: utf-8 -*-
"""Filtro docs leves: qualquer contrato/aditivo, exige DFD, ordena por poucos anexos."""

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


def test_rejeita_qualquer_contrato():
    mod = _load()
    itens = [
        _lic(
            "CHAMADA PÚBLICA Nº 004/2023",
            [
                ("DFD.pdf", "http://a/dfd.pdf"),
                ("Termo de Referência.pdf", "http://a/tr.pdf"),
                ("Contrato - Valdair José-ass.pdf", "http://a/contrato.pdf"),
            ],
        ),
    ]
    sel, rej = mod.filtrar_licitacoes_docs_leves(itens)
    assert sel == []
    assert rej[0]["_filtro_motivo"] == "tem contrato/aditivo"


def test_rejeita_so_aditivo():
    mod = _load()
    itens = [
        _lic(
            "Pregão 02/2023",
            [("1º Termo Aditivo.pdf", "http://a/aditivo.pdf")],
        ),
    ]
    sel, rej = mod.filtrar_licitacoes_docs_leves(itens)
    assert sel == []
    assert rej[0]["_filtro_motivo"] == "tem contrato/aditivo"


def test_rejeita_sem_dfd():
    mod = _load()
    itens = [
        _lic(
            "Pregão 03/2023",
            [
                ("Termo de Referência.pdf", "http://a/tr.pdf"),
                ("Termo de Homologação.pdf", "http://a/hom.pdf"),
            ],
        ),
    ]
    sel, rej = mod.filtrar_licitacoes_docs_leves(itens)
    assert sel == []
    assert rej[0]["_filtro_motivo"] == "sem DFD"


def test_aceita_dfd_sem_contrato_e_ordena():
    mod = _load()
    poucos = _lic(
        "Pregão poucos",
        [
            ("DFD.pdf", "http://a/dfd1.pdf"),
            ("Termo de Referência.pdf", "http://a/tr1.pdf"),
            ("Termo de Homologação.pdf", "http://a/h1.pdf"),
        ],
        link="poucos",
    )
    muitos = _lic(
        "Pregão muitos",
        [
            ("Documento de Formalização da Demanda.pdf", "http://a/dfd2.pdf"),
            ("ETP.pdf", "http://a/etp.pdf"),
            ("Termo de Referência.pdf", "http://a/tr2.pdf"),
            ("Edital.pdf", "http://a/ed.pdf"),
            ("Aviso.pdf", "http://a/av.pdf"),
            ("Ata.pdf", "http://a/ata.pdf"),
            ("Parecer jurídico.pdf", "http://a/pj.pdf"),
        ],
        link="muitos",
    )
    sel, rej = mod.filtrar_licitacoes_docs_leves([muitos, poucos])
    assert rej == []
    assert sel[0]["link"] == "poucos"
    assert sel[1]["link"] == "muitos"


def test_classificar_contrato_valdair():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from ia_local.classificar_docs import classificar

    assert classificar("Contrato - Valdair José-ass.pdf")["tipo"] == "contrato"
