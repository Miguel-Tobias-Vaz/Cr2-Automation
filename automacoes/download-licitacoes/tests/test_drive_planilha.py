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
    arq = "https://drive.google.com/open?id=1KMw2do-NZ_fcxO0Vz687foVoE0okvuj3&usp=drive_copy"
    assert mod._id_pasta_drive(pasta) == "1tuLh4LAViaT2US-8NWx5a08hTzAiCC9t"
    assert mod._id_arquivo_drive(arq) == "1KMw2do-NZ_fcxO0Vz687foVoE0okvuj3"
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
