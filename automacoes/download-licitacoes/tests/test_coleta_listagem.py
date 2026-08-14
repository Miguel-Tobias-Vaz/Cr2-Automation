"""Coleta de listagem — slug e fallback API (Carregar Mais)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "script.py"


def _load():
    spec = importlib.util.spec_from_file_location("licit_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["licit_script"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestSlugCategoria(unittest.TestCase):
    def setUp(self):
        self.mod = _load()

    def test_c_licitacoes(self):
        self.assertEqual(
            self.mod.slug_categoria_da_listagem(
                "https://cmmoju.pa.gov.br/c/licitacoes/"
            ),
            "licitacoes",
        )

    def test_com_page_no_fim(self):
        self.assertEqual(
            self.mod.slug_categoria_da_listagem(
                "https://exemplo.pa.gov.br/c/licitacoes/page/3/"
            ),
            "licitacoes",
        )


class TestComplementarApi(unittest.TestCase):
    def setUp(self):
        self.mod = _load()

    def test_mescla_posts_novos(self):
        mod = self.mod
        posts = {
            "https://cmmoju.pa.gov.br/pregao/": ("PREGÃO 1/2023", "2023"),
        }
        sess = MagicMock()
        with patch.object(mod, "descobrir_categoria_id", return_value=75), patch.object(
            mod,
            "coletar_posts_api",
            return_value=[
                {
                    "titulo": "INEXIGIBILIDADE Nº 001/2023 (teste)",
                    "link": "https://cmmoju.pa.gov.br/inex-001/",
                    "date": "2023-01-03T10:00:00",
                }
            ],
        ):
            out = mod._complementar_posts_via_api(
                sess,
                posts,
                "https://cmmoju.pa.gov.br/c/licitacoes/",
                anos_filtro=["2023"],
            )
        self.assertEqual(len(out), 2)
        self.assertIn("https://cmmoju.pa.gov.br/inex-001/", out)
