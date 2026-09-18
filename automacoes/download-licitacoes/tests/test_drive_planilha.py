# -*- coding: utf-8 -*-
"""Google Drive na planilha-fonte de licitações."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "script.py"


def _load():
    spec = importlib.util.spec_from_file_location("dl_lic", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_parse_drive_ids():
    mod = _load()
    pasta = "https://drive.google.com/drive/folders/1tuLh4LAViaT2US-8NWx5a08hTzAiCC9t?usp=drive_link"
    arq = "https://drive.google.com/file/d/1KMw2do-NZ_fcxO0Vz687foVoE0okvuj3/view"
    open_id = "https://drive.google.com/open?id=1KMw2do-NZ_fcxO0Vz687foVoE0okvuj3&usp=drive_copy"
    assert mod._id_pasta_drive(pasta) == "1tuLh4LAViaT2US-8NWx5a08hTzAiCC9t"
    assert mod._id_arquivo_drive(arq) == "1KMw2do-NZ_fcxO0Vz687foVoE0okvuj3"
    assert mod._id_arquivo_drive(open_id) is None
    assert mod._id_drive_ambiguo(open_id) == "1KMw2do-NZ_fcxO0Vz687foVoE0okvuj3"
    assert mod.eh_url_google_drive(pasta)


def test_link_documentos_em_qualquer_coluna():
    mod = _load()
    cells = [
        "1",
        "PREGÃO",
        "9/2023",
        "OBJETO",
        "Finalizado",
        "https://drive.google.com/drive/folders/abc123xyzABCDEFGHIJK",
        "",
        "",
        "",
        "",
    ]
    idx = {"modalidade": 1, "numero": 2, "objeto": 3, "publicacao": 4, "documentos": 9}
    link = mod._link_documentos_na_linha(cells, idx)
    assert "drive.google.com" in link
    assert "abc123" in link


def test_paralelismo_planilha_drive_reduz():
    mod = _load()
    dw, lw = mod.paralelismo_efetivo(
        planilha_fonte=True, download_workers=6, licitacao_workers=12,
    )
    assert dw == 1
    assert lw == 2


def test_paralelismo_portal_mantem_alto():
    mod = _load()
    dw, lw = mod.paralelismo_efetivo(
        planilha_fonte=False, download_workers=6, licitacao_workers=12,
    )
    assert dw == 6
    assert lw == 12


def test_paralelismo_planilha_respeita_pedido_menor():
    mod = _load()
    dw, lw = mod.paralelismo_efetivo(
        planilha_fonte=True, download_workers=1, licitacao_workers=1,
    )
    assert dw == 1
    assert lw == 1


def test_open_id_tenta_pasta_antes_de_arquivo():
    from unittest.mock import MagicMock, patch

    mod = _load()
    url = "https://drive.google.com/open?id=PASTA123xyzABCDEFGHIJ"
    filhos = [("ATA.pdf", "https://drive.google.com/uc?export=download&confirm=t&id=ARQ1")]
    sessao = MagicMock()
    with patch.object(mod, "_listar_pasta_drive_embedded", return_value=filhos):
        out = mod.anexos_google_drive(sessao, url)
    assert out == filhos


def test_open_id_vira_arquivo_se_pasta_vazia():
    from unittest.mock import MagicMock, patch

    mod = _load()
    url = "https://drive.google.com/open?id=FILE123xyzABCDEFGHIJK"
    sessao = MagicMock()
    resp = MagicMock()
    resp.ok = True
    resp.text = '<meta property="og:title" content="Edital.pdf">'
    sessao.get.return_value = resp
    with patch.object(mod, "_listar_pasta_drive_embedded", return_value=[]):
        with patch.object(mod, "_listar_pasta_drive_data_id", return_value=[]):
            out = mod.anexos_google_drive(sessao, url)
    assert len(out) == 1
    assert out[0][0] == "Edital.pdf"
    assert "FILE123xyzABCDEFGHIJK" in out[0][1]
