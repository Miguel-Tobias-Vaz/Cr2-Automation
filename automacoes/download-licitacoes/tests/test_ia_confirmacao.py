# -*- coding: utf-8 -*-
"""Testes da confirmação IA (número/objeto/situação/datas/valores)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ia_local.ia_refinar import (  # noqa: E402
    _normalizar_data_ia,
    _normalizar_valor_ia,
    _validar_e_fundir,
    montar_prompt,
)


class TestConfirmacaoIA(unittest.TestCase):
    def test_normalizar_data(self):
        self.assertEqual(_normalizar_data_ia("5/3/2023"), "05/03/2023")
        self.assertEqual(_normalizar_data_ia("Não informado"), "")
        self.assertEqual(_normalizar_data_ia("2023-03-05"), "")

    def test_normalizar_valor(self):
        self.assertEqual(_normalizar_valor_ia("1.720.000,50"), "1720000.50")
        self.assertEqual(_normalizar_valor_ia("1720000.00"), "1720000.00")

    def test_validar_fundir_confirma_campos(self):
        fonte = (
            "PREGAO 009/2023 aquisição de materiais. "
            "Valor estimado R$ 10.000,00. "
            "Abertura em 10/04/2023. Publicação 01/04/2023. "
            "Homologado o valor de 9.500,00."
        )
        local = {
            "numero": "009/2023",
            "ano": "2023",
            "objeto": "aquisição de materiais",
            "situacao": "Finalizado",
            "data_publicacao": "01/04/2023",
            "data_abertura": "",
            "valor_estimado": "10000.00",
            "valor_homologado": "",
        }
        dados = {
            "numero": "009/2023",
            "ano": "2023",
            "objeto": "aquisição de materiais",
            "situacao": "Finalizado",
            "data_publicacao": "01/04/2023",
            "data_abertura": "10/04/2023",
            "valor_estimado": "10000.00",
            "valor_homologado": "9500.00",
            "confianca": "alta",
            "trecho_numero": "PREGAO 009/2023",
            "trecho_objeto": "aquisição de materiais",
            "motivo_situacao": "Homologado",
            "trecho_data_publicacao": "Publicação 01/04/2023",
            "trecho_data_abertura": "Abertura em 10/04/2023",
            "trecho_valor_estimado": "Valor estimado R$ 10.000,00",
            "trecho_valor_homologado": "Homologado o valor de 9.500,00",
            "observacao": "",
        }
        out = _validar_e_fundir(dados, local, fonte.lower())
        self.assertEqual(out["numero"], "009/2023")
        self.assertEqual(out["data_abertura"], "10/04/2023")
        self.assertEqual(out["valor_homologado"], "9500.00")
        self.assertTrue(
            any("data_abertura" in m or "valor_homologado" in m for m in out["mudancas"])
        )

    def test_montar_prompt_inclui_confirmacao(self):
        prompt = montar_prompt(
            "PREGAO 1/2023 (teste)",
            {"numero": "001/2023", "objeto": "teste", "situacao": "Aberto"},
            [{"nome": "Edital.pdf", "tipo": "edital", "rotulo": "Edital",
              "texto": "Edital do pregão 001/2023 objeto teste abertura 01/02/2023"}],
        )
        self.assertIn("CONFIRME", prompt)
        self.assertIn("data_abertura", prompt)
        self.assertIn("valor_estimado", prompt)


if __name__ == "__main__":
    unittest.main()
