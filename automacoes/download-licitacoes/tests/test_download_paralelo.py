# -*- coding: utf-8 -*-
"""Download paralelo de anexos na mesma licitação."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "script.py"


def _load():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("download_licitacoes_script", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_baixar_anexos_paralelo_chama_todos(tmp_path):
    mod = _load()
    mod.DOWNLOAD_WORKERS = 4
    pasta = tmp_path / "lic"
    pasta.mkdir()
    anexos = [
        ("DFD.pdf", "http://ex/dfd.pdf"),
        ("TR.pdf", "http://ex/tr.pdf"),
        ("Homologacao.pdf", "http://ex/h.pdf"),
    ]

    def fake_baixar(sessao, url, destino):
        Path(destino).write_bytes(b"%PDF-1.4 fake")
        return True

    with patch.object(mod, "baixar_arquivo", side_effect=fake_baixar):
        sessao = MagicMock()
        sessao.headers = {"User-Agent": "t"}
        sessao.verify = True
        paths = mod.baixar_anexos_da_licitacao(sessao, anexos, str(pasta))

    assert len(paths) == 3
    assert all(Path(p).is_file() for p in paths)


def test_baixar_anexos_pula_ja_existente(tmp_path):
    mod = _load()
    mod.DOWNLOAD_WORKERS = 2
    pasta = tmp_path / "lic"
    pasta.mkdir()
    existente = pasta / "Dfd.pdf"
    # nome_arquivo capitaliza — grava com o nome que a função geraria
    from unittest.mock import patch as p2

    anexos = [("DFD.pdf", "http://ex/dfd.pdf"), ("Novo.pdf", "http://ex/novo.pdf")]

    # Cria arquivo com o nome final que nome_arquivo produz
    nome_dfd = mod.nome_arquivo("DFD.pdf", "http://ex/dfd.pdf")
    (pasta / nome_dfd).write_bytes(b"old")

    chamadas = []

    def fake_baixar(sessao, url, destino):
        chamadas.append(url)
        Path(destino).write_bytes(b"new")
        return True

    with patch.object(mod, "baixar_arquivo", side_effect=fake_baixar):
        sessao = MagicMock()
        sessao.headers = {}
        sessao.verify = True
        paths = mod.baixar_anexos_da_licitacao(sessao, anexos, str(pasta))

    assert len(paths) == 2
    assert chamadas == ["http://ex/novo.pdf"]
