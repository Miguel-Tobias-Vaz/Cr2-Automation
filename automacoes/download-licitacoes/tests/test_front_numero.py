# -*- coding: utf-8 -*-
"""Testes das regras Front / numeros longos (ex.: Altamira)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gestor_regras.config_front import SIGLAS  # noqa: E402
from gestor_regras.front import linha_front, modalidade_front, numero_front  # noqa: E402
from gestor_regras.upload import registro_de_linha_planilha  # noqa: E402
from ia_local.regras_titulo import numero_com_sigla  # noqa: E402


# Tabela oficial (sigla → modalidade)
TABELA_OFICIAL = {
    "AD": "Adesão a Ata de Registro de Preço",
    "CR": "Credenciamento",
    "CC": "Concorrência",
    "CON": "Concurso",
    "CA": "Carona",
    "CD": "Contratação Direta",
    "CV": "Convite",
    "CP": "Chamada Pública",
    "DC": "Diálogo Competitivo",
    "DL": "Dispensa de Licitação",
    "IN": "Inexigibilidade de Licitação",
    "LL": "Leilão",
    "PE": "Pregão Eletrônico",
    "PP": "Pregão Presencial",
    "RPCP": "Registro de Preços Originário de Chamamento Público",
    "RPPE": "Registro de Preços Originário de Pregão Eletrônico",
    "RPPP": "Registro de Preços Originário de Pregão Presencial",
    "TP": "Tomada de Preços",
}


class TestNumeroFront(unittest.TestCase):
    def test_numero_curto_padroniza(self):
        self.assertEqual(
            numero_front({"numero": "3/2025", "modalidade": "Pregão Eletrônico"}),
            "003/2025-PE",
        )

    def test_numero_longo_altamira_nao_corta(self):
        self.assertEqual(
            numero_front({"numero": "1123002/2023", "modalidade": "Convite"}),
            "1123002/2023-CV",
        )

    def test_numero_com_sigla_ia(self):
        self.assertEqual(numero_com_sigla("1123002/2023", "Convite"), "1123002/2023-CV")
        self.assertEqual(numero_com_sigla("1/2024", "Pregão Presencial"), "001/2024-PP")

    def test_linha_front_objeto_altamira(self):
        obj = (
            "Contratação de empresa para Prestação de Serviços de Comunicação "
            "e Publicidade Institucional do Legislativo "
            "(Transmissão, produção, edição, midias digitais e sociais)"
        )
        reg = registro_de_linha_planilha({
            "Modalidade": "Convite",
            "Número": "1123002/2023",
            "Ano": "2023",
            "Objeto": obj,
            "Data de Publicação": "30/11/2023",
            "Data de Abertura": "",
            "Valor Estimado": "",
            "Situação da Licitação": "Publicada",
            "Valor Homologado": "",
        })
        lf = linha_front(reg)
        self.assertEqual(lf["numero"], "1123002/2023-CV")
        self.assertEqual(lf["modalidade"], "Convite")
        self.assertIn("Publicidade Institucional", lf["objeto"])
        self.assertEqual(lf["ano"], "2023")


class TestModalidadesOficiais(unittest.TestCase):
    def test_siglas_iguais_a_tabela(self):
        self.assertEqual(SIGLAS, {v: k for k, v in TABELA_OFICIAL.items()})

    def test_numero_todas_siglas(self):
        for sigla, nome in TABELA_OFICIAL.items():
            self.assertEqual(
                numero_com_sigla("12/2024", nome),
                "012/2024-%s" % sigla,
            )

    def test_concorrencia_variantes_viram_cc(self):
        self.assertEqual(modalidade_front("Concorrência Eletrônica"), "Concorrência")
        self.assertEqual(modalidade_front("Concorrência Presencial"), "Concorrência")
        self.assertEqual(
            numero_front({"numero": "5/2024", "modalidade": "Concorrência"}),
            "005/2024-CC",
        )


if __name__ == "__main__":
    unittest.main()
