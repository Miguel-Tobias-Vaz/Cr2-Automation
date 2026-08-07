# -*- coding: utf-8 -*-
import unittest
from datetime import datetime

from script import (
    ano_de_data_pub,
    ano_do_titulo,
    decidir_anos_vs_filtro,
    extrai_ano,
)


class TestExtraiAno(unittest.TestCase):
    def test_ano_apos_barra_vence_sufixo_data(self):
        # Bug Juruti: lia 2004 em '-200402' e parava o filtro 2023 cedo
        self.assertEqual(extrai_ano("9/2023-200402"), "2023")
        self.assertEqual(
            ano_do_titulo(
                "PREGÃO ELETRÔNICO SRP Nº 9/2023-200402 "
                "(CONTRATAÇÃO DE SERVIÇOS DE ÁUDIO)"
            ),
            "2023",
        )

    def test_barra_com_ano_final(self):
        self.assertEqual(extrai_ano("202301/2024-CPL"), "2024")

    def test_sem_barra_usa_ano_solto(self):
        self.assertEqual(extrai_ano("edital 2022 CMJ"), "2022")

    def test_nao_pega_ano_colado_em_mais_digitos(self):
        self.assertEqual(extrai_ano("200402"), "")


class TestFiltroAnoComPublicacao(unittest.TestCase):
    def setUp(self):
        self.anos = {"2023"}
        self.ano_min = 2023

    def test_casa_pelo_titulo(self):
        self.assertEqual(
            decidir_anos_vs_filtro("2023", "2024", self.anos, self.ano_min),
            "pegar",
        )

    def test_casa_pela_data_publicacao(self):
        # Número de outro ano, mas publicado em 2023
        self.assertEqual(
            decidir_anos_vs_filtro("2022", "2023", self.anos, self.ano_min),
            "pegar",
        )
        self.assertEqual(ano_de_data_pub("15/03/2023"), "2023")
        self.assertEqual(ano_de_data_pub(datetime(2023, 5, 1)), "2023")

    def test_pular_quando_ambos_mais_novos(self):
        self.assertEqual(
            decidir_anos_vs_filtro("2024", "2024", self.anos, self.ano_min),
            "pular",
        )

    def test_parar_quando_pub_mais_antiga(self):
        self.assertEqual(
            decidir_anos_vs_filtro("2022", "2022", self.anos, self.ano_min),
            "parar",
        )


if __name__ == "__main__":
    unittest.main()
