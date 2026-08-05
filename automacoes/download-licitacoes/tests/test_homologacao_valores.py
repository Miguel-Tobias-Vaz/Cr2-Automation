# -*- coding: utf-8 -*-
"""Testes: valor homologado = total final ou soma de itens."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ia_local.regras_valores import (  # noqa: E402
    _valor_do_termo_homologacao,
    extrair_valores_dos_docs,
)


class TestHomologacaoTotalOuSoma(unittest.TestCase):
    def test_usa_total_final(self):
        texto = """
        TERMO DE HOMOLOGAÇÃO
        Item 1 - Canetas R$ 1.000,00
        Item 2 - Papel R$ 2.000,00
        Item 3 - Toner R$ 3.000,00

        VALOR TOTAL HOMOLOGADO: R$ 6.000,00
        """
        r = _valor_do_termo_homologacao(texto, "Termo de Homologacao.pdf", "homologacao")
        self.assertIsNotNone(r)
        self.assertEqual(r["valor"], 6000.0)

    def test_soma_itens_sem_total(self):
        texto = """
        TERMO DE HOMOLOGAÇÃO
        Item 1 materiais de limpeza valor total do item R$ 1.500,00
        Item 2 generos alimenticios valor total do item R$ 2.500,00
        Item 3 expediente valor total do item R$ 1.000,00
        Homologo os itens acima.
        """
        r = _valor_do_termo_homologacao(texto, "Termo de Homologacao.pdf", "homologacao")
        self.assertIsNotNone(r)
        self.assertEqual(r["valor"], 5000.0)
        self.assertIn("soma", r["rotulo"])

    def test_extrair_docs_prioriza_total(self):
        docs = [{
            "nome": "Termo de Homologacao.pdf",
            "tipo": "homologacao",
            "texto": (
                "Item 1 R$ 10.000,00\nItem 2 R$ 5.000,00\n"
                "TOTAL GERAL: R$ 15.000,00"
            ),
        }]
        out = extrair_valores_dos_docs(docs)
        self.assertEqual(out["valor_homologado"], "15000.00")


if __name__ == "__main__":
    unittest.main()
