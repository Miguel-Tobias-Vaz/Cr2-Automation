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
    def test_numero_curto_so_acrescenta_sigla(self):
        self.assertEqual(
            numero_front({"numero": "3/2025", "modalidade": "Pregão Eletrônico"}),
            "3/2025-PE",
        )

    def test_numero_longo_altamira_nao_corta(self):
        self.assertEqual(
            numero_front({"numero": "1123002/2023", "modalidade": "Convite"}),
            "1123002/2023-CV",
        )

    def test_numero_com_sigla_ia(self):
        self.assertEqual(numero_com_sigla("1123002/2023", "Convite"), "1123002/2023-CV")
        self.assertEqual(numero_com_sigla("1/2024", "Pregão Presencial"), "1/2024-PP")

    def test_so_troca_categoria_preserva_numeros(self):
        """Números/códigos ficam iguais; só a categoria final muda."""
        casos = [
            ("9/2023-007-CMVX-SRP", "Registro de Preços Originário de Pregão Presencial",
             "9/2023-007-CMVX-RPPP"),
            ("9/2023-004-CMVX-SRP", "Registro de Preços Originário de Pregão Presencial",
             "9/2023-004-CMVX-RPPP"),
            ("9/2023-006-CMVX", "Registro de Preços Originário de Pregão Presencial",
             "9/2023-006-CMVX-RPPP"),
            ("2/2023-001", "Tomada de Preços", "2/2023-001-TP"),
            ("0/2023-007-CMXV", "Dispensa de Licitação", "0/2023-007-CMXV-DL"),
            ("1/2023-004-CMVX", "Convite", "1/2023-004-CMVX-CV"),
            ("6/2023-004-CMVX", "Inexigibilidade de Licitação", "6/2023-004-CMVX-IN"),
            ("6/2023-003", "Inexigibilidade de Licitação", "6/2023-003-IN"),
            ("1/2023-001", "Convite", "1/2023-001-CV"),
            ("0/2023-001-CMVX", "Dispensa de Licitação", "0/2023-001-CMVX-DL"),
            ("009/2023-RPPP", "Registro de Preços Originário de Pregão Presencial",
             "009/2023-RPPP"),
            ("009/2023-PE", "Registro de Preços Originário de Pregão Presencial",
             "009/2023-RPPP"),
        ]
        for bruto, modalidade, esperado in casos:
            self.assertEqual(
                numero_com_sigla(bruto, modalidade),
                esperado,
                msg="falhou para %r" % bruto,
            )
            self.assertEqual(
                numero_front({"numero": bruto, "modalidade": modalidade}),
                esperado,
                msg="numero_front falhou para %r" % bruto,
            )

    def test_ia_nao_encurta_codigos_portal(self):
        from ia_local.regras_titulo import numero_pos_confirmacao

        self.assertEqual(
            numero_pos_confirmacao(
                "009/2023",
                "9/2023-007-CMVX-RPPP",
                "Registro de Preços Originário de Pregão Presencial",
            ),
            "9/2023-007-CMVX-RPPP",
        )
        self.assertEqual(
            numero_pos_confirmacao(
                "9/2023",
                "9/2023-007-CMVX-SRP",
                "Registro de Preços Originário de Pregão Presencial",
            ),
            "9/2023-007-CMVX-RPPP",
        )

    def test_mesmo_numero_em_todas_as_planilhas(self):
        """preenchida e subir* devem ficar com o mesmo Número (só troca categoria)."""
        from script import padronizar_linha_para_todas_planilhas
        from gestor_regras.upload import (
            _garantir_numero_igual_nas_planilhas,
            registro_de_linha_planilha,
        )

        linha = {
            "Modalidade": "Pregão Presencial",
            "Número": "9/2023-007-CMVX-SRP",
            "Ano": "2023",
            "Objeto": "registro de preços de materiais de limpeza",
            "Data de Publicação": "01/04/2023",
            "Data de Abertura": "10/04/2023",
            "Valor Estimado": "1000.00",
            "Situação da Licitação": "Publicada",
            "Valor Homologado": "",
        }
        padronizar_linha_para_todas_planilhas(linha)
        self.assertEqual(linha["Número"], "9/2023-007-CMVX-RPPP")
        self.assertEqual(
            linha["Modalidade"],
            "Registro de Preços Originário de Pregão Presencial",
        )

        reg = registro_de_linha_planilha(linha)
        lf = linha_front(reg)
        lf = _garantir_numero_igual_nas_planilhas(lf, linha)
        self.assertEqual(lf["numero"], linha["Número"])
        self.assertEqual(lf["modalidade"], linha["Modalidade"])

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
                "12/2024-%s" % sigla,
            )

    def test_concorrencia_variantes_viram_cc(self):
        self.assertEqual(modalidade_front("Concorrência Eletrônica"), "Concorrência")
        self.assertEqual(modalidade_front("Concorrência Presencial"), "Concorrência")
        self.assertEqual(
            numero_front({"numero": "5/2024", "modalidade": "Concorrência"}),
            "5/2024-CC",
        )


if __name__ == "__main__":
    unittest.main()
