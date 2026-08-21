# -*- coding: utf-8 -*-
import unittest

from gestor_regras.campos_contrato import (
    ano_contrato,
    cnpj_orgao,
    contratada,
    falta_para_o_portal,
    fiscal_contrato,
    linha_contrato,
    numero_contrato,
    objeto_contrato,
    tipo_contrato,
    valor_contrato,
    vigencia,
)

CONTRATO = """
PREFEITURA MUNICIPAL DE EXEMPLO
CNPJ nº 05.105.135/0001-30

CONTRATO ADMINISTRATIVO Nº 003/2025
PROCESSO ADMINISTRATIVO Nº 45/2025 - PREGÃO ELETRÔNICO Nº 009/2025

CONTRATANTE: PREFEITURA MUNICIPAL DE EXEMPLO, inscrita no CNPJ 05.105.135/0001-30.
CONTRATADA: COMERCIAL ALFA DISTRIBUIDORA LTDA, pessoa jurídica de direito privado,
inscrita no CNPJ nº 12.345.678/0001-99, com sede na Rua das Flores, 100.

CLÁUSULA PRIMEIRA - DO OBJETO
Contratação de empresa especializada no fornecimento de material de limpeza e
higienização para atender as necessidades das secretarias municipais.

CLÁUSULA SEGUNDA - DO VALOR
O valor global do presente contrato é de R$ 254.300,50 (duzentos e cinquenta e
quatro mil trezentos reais e cinquenta centavos).

CLÁUSULA TERCEIRA - DA VIGÊNCIA
O prazo de vigência do presente contrato será de 02/01/2025 a 31/12/2025.

CLÁUSULA QUARTA - DA FISCALIZAÇÃO
Fica designado o servidor JOAO CARLOS PEREIRA, matrícula 1234, para fiscal do
contrato.
"""

ADITIVO = """
2º TERMO ADITIVO AO CONTRATO Nº 003/2025

CONTRATADA: COMERCIAL ALFA DISTRIBUIDORA LTDA, inscrita no CNPJ 12.345.678/0001-99.

CLÁUSULA PRIMEIRA - DO OBJETO
Prorrogação do prazo de vigência do Contrato nº 003/2025 por mais 12 (doze)
meses, mantidas as demais condições.

CLÁUSULA SEGUNDA - DO VALOR
O valor acrescido é de R$ 50.000,00.

CLÁUSULA TERCEIRA - DA VIGÊNCIA
A vigência fica prorrogada de 01/01/2026 a 31/12/2026.
"""

PORTARIA = """
PORTARIA Nº 45/2025

O PREFEITO MUNICIPAL DE EXEMPLO, no uso de suas atribuições, RESOLVE:
Art. 1º DESIGNAR a servidora MARIA APARECIDA SOUZA, matrícula 987, para exercer
a função de fiscal do Contrato nº 010/2025.
"""


class TestTipoContrato(unittest.TestCase):
    def test_contrato_simples(self):
        self.assertEqual(tipo_contrato("Contrato 003-2025.pdf", CONTRATO), "Contrato")

    def test_aditivo_com_numero_no_nome(self):
        self.assertEqual(tipo_contrato("2º Termo Aditivo 003-2025.pdf"), "Aditivo 02")

    def test_aditivo_ordinal_escrito(self):
        self.assertEqual(
            tipo_contrato("Primeiro Termo Aditivo ao contrato.pdf"), "Aditivo 01"
        )

    def test_aditivo_numero_depois(self):
        self.assertEqual(tipo_contrato("Termo Aditivo nº 03.pdf"), "Aditivo 03")

    def test_aditivo_sem_ordem_vira_01(self):
        self.assertEqual(tipo_contrato("termo aditivo.pdf"), "Aditivo 01")

    def test_apostilamento_e_aditivo(self):
        self.assertTrue(tipo_contrato("Apostilamento.pdf").startswith("Aditivo"))

    def test_nome_generico_decide_pelo_texto(self):
        self.assertEqual(tipo_contrato("doc01.pdf", ADITIVO), "Aditivo 02")


class TestNumeroEAno(unittest.TestCase):
    def test_numero_do_texto_normalizado(self):
        self.assertEqual(numero_contrato("doc.pdf", CONTRATO), "003/2025")

    def test_numero_do_nome_do_arquivo(self):
        # nome de arquivo usa hífen/underscore — barra é inválida no Windows
        self.assertEqual(numero_contrato("Contrato 12-2024.pdf", ""), "012/2024")
        self.assertEqual(numero_contrato("contrato_003_2025.pdf", ""), "003/2025")
        self.assertEqual(numero_contrato("Contrato 003-2025-PE.pdf", ""), "003/2025")

    def test_texto_tem_prioridade_sobre_o_nome(self):
        self.assertEqual(numero_contrato("anexo-99-1999.pdf", CONTRATO), "003/2025")

    def test_aditivo_herda_numero_do_contrato(self):
        self.assertEqual(numero_contrato("2 Termo Aditivo.pdf", ADITIVO), "003/2025")

    def test_ano_vem_do_numero(self):
        self.assertEqual(ano_contrato("003/2025"), "2025")

    def test_ano_cai_para_data_quando_sem_numero(self):
        self.assertEqual(ano_contrato("", "02/01/2025"), "2025")


class TestObjeto(unittest.TestCase):
    def test_pega_clausula_do_objeto(self):
        obj = objeto_contrato(CONTRATO)
        self.assertIn("material de limpeza", obj)
        self.assertNotIn("CLÁUSULA SEGUNDA", obj)

    def test_pega_objeto_com_rotulo_em_linha(self):
        txt = """
        CONTRATO Nº 003/2025
        OBJETO DA CONTRATAÇÃO: Aquisição de material de limpeza e higienização para atender as necessidades da secretaria.
        CLÁUSULA SEGUNDA - DO VALOR
        O valor global do presente contrato é de R$ 10.000,00.
        """
        obj = objeto_contrato(txt)
        self.assertIn("material de limpeza", obj)
        self.assertNotIn("CLÁUSULA SEGUNDA", obj)

    def test_pega_objeto_com_rotulo_simples(self):
        txt = """
        CONTRATO Nº 010/2025
        OBJETO: contratação de empresa para prestação de serviços de limpeza urbana.
        CLÁUSULA SEGUNDA - DO VALOR
        """
        obj = objeto_contrato(txt)
        self.assertIn("serviços de limpeza urbana", obj)

    def test_sem_objeto_devolve_vazio(self):
        self.assertEqual(objeto_contrato("texto qualquer sem clausulas"), "")


class TestContratada(unittest.TestCase):
    def test_nome_e_cnpj_da_contratada(self):
        nome, doc = contratada(CONTRATO, "05.105.135/0001-30")
        self.assertEqual(nome, "COMERCIAL ALFA DISTRIBUIDORA LTDA")
        self.assertEqual(doc, "12.345.678/0001-99")

    def test_contratada_com_rotulo_simples(self):
        txt = """
        CONTRATADA: EMPRESA ABC SERVICOS LTDA, inscrita no CNPJ nº 12.345.678/0001-99.
        """
        nome, doc = contratada(txt, "05.105.135/0001-30")
        self.assertEqual(nome, "EMPRESA ABC SERVICOS LTDA")
        self.assertEqual(doc, "12.345.678/0001-99")

    def test_nao_confunde_com_cnpj_do_orgao(self):
        _nome, doc = contratada(CONTRATO, "05.105.135/0001-30")
        self.assertNotEqual(doc, "05.105.135/0001-30")


class TestVigencia(unittest.TestCase):
    def test_intervalo_de_a(self):
        self.assertEqual(vigencia(CONTRATO), ("02/01/2025", "31/12/2025"))

    def test_intervalo_no_aditivo(self):
        self.assertEqual(vigencia(ADITIVO), ("01/01/2026", "31/12/2026"))

    def test_intervalo_com_rotulo_simples(self):
        txt = "Prazo de vigência: 01/01/2025 até 31/12/2025."
        self.assertEqual(vigencia(txt), ("01/01/2025", "31/12/2025"))

    def test_periodo_em_meses_a_contar_de_data(self):
        txt = "O prazo de vigência será de 12 (doze) meses a contar de 15/03/2025."
        self.assertEqual(vigencia(txt), ("15/03/2025", "15/03/2026"))

    def test_sem_vigencia(self):
        self.assertEqual(vigencia("nada aqui"), ("", ""))


class TestValor(unittest.TestCase):
    def test_valor_global(self):
        self.assertEqual(valor_contrato(CONTRATO), "254300.50")

    def test_valor_acrescido_do_aditivo(self):
        self.assertEqual(valor_contrato(ADITIVO), "50000.00")

    def test_sem_valor(self):
        self.assertEqual(valor_contrato("sem dinheiro nenhum"), "")

    def test_rs_sem_rotulo_nao_vira_valor(self):
        # preço de item de tabela não é o valor do contrato — melhor vazio
        # (foi o que fez sair 902.50 em vez de 226.907,60 no PDF de Cumaru)
        self.assertEqual(
            valor_contrato("Item 1 Cadeira escolar unidade 50 R$ 902,50"), ""
        )

    def test_valor_global_depois_de_muito_texto(self):
        txt = "Item %d cadeira R$ 902,50\n" % 1 * 200
        txt += "CLAUSULA: O valor global do contrato e de R$ 226.907,60."
        self.assertEqual(valor_contrato(txt), "226907.60")


class TestFiscal(unittest.TestCase):
    def test_fiscal_designado_no_contrato(self):
        self.assertEqual(fiscal_contrato(CONTRATO), "JOAO CARLOS PEREIRA")

    def test_fiscal_da_portaria(self):
        self.assertEqual(fiscal_contrato(PORTARIA), "MARIA APARECIDA SOUZA")

    def test_nao_devolve_ruido(self):
        self.assertEqual(fiscal_contrato("fiscal do contrato: a Prefeitura"), "")


class TestLinhaCompleta(unittest.TestCase):
    def test_linha_contrato_completa(self):
        linha = linha_contrato(
            "Contrato 003-2025.pdf",
            CONTRATO,
            licitacao_origem="009/2025-PE",
            documento="C:/saida/Contratos/003-2025-PE/Contrato 003-2025.pdf",
        )
        self.assertEqual(linha["licitacao_origem"], "009/2025-PE")
        self.assertEqual(linha["ano"], "2025")
        self.assertEqual(linha["tipo_contrato"], "Contrato")
        self.assertEqual(linha["numero"], "003/2025")
        self.assertEqual(linha["nome_razao_social"], "COMERCIAL ALFA DISTRIBUIDORA LTDA")
        self.assertEqual(linha["cpf_cnpj"], "12.345.678/0001-99")
        self.assertEqual(linha["data_vigencia_in"], "02/01/2025")
        self.assertEqual(linha["data_vigencia_fim"], "31/12/2025")
        self.assertEqual(linha["valor"], "254300.50")
        self.assertEqual(linha["fiscal_contrato"], "JOAO CARLOS PEREIRA")
        self.assertEqual(falta_para_o_portal(linha), [])

    def test_fiscal_vem_da_portaria_quando_falta_no_contrato(self):
        sem_fiscal = CONTRATO.split("CLÁUSULA QUARTA")[0]
        linha = linha_contrato(
            "Contrato 003-2025.pdf", sem_fiscal, texto_portaria=PORTARIA
        )
        self.assertEqual(linha["fiscal_contrato"], "MARIA APARECIDA SOUZA")

    def test_documento_cai_para_nome_do_arquivo(self):
        linha = linha_contrato("Contrato 003-2025.pdf", CONTRATO)
        self.assertEqual(linha["documento"], "Contrato 003-2025.pdf")

    def test_faltas_apontam_campos_do_portal(self):
        linha = linha_contrato("qualquer.pdf", "texto sem nada util")
        faltas = falta_para_o_portal(linha)
        self.assertIn("numero", faltas)
        self.assertIn("objeto", faltas)
        self.assertIn("nomeRazaoSocial", faltas)


# Trechos REAIS de pmcn.pa.gov.br (Cumaru do Norte). O pdfplumber devolve os
# acentos corrompidos: "ê" virou "e "+espaço e "ç/ã" viraram U+FFFD.
CONTRATO_CUMARU = (
    "ESTADO DO PAR�\n"
    "CONTRATO N� 236/2023\n"
    "Pelo presente instrumento e na melhor forma de Direito, de um lado a "
    "PREFEITURA MUNICIPAL DE\nCUMARU DO NORTE, Pessoa Jur� dica de Direito "
    "Pu blico Interno, com sede a Avenida dos Estados, n�.\n"
    "73 - Centro, inscrito no CNPJ sob n�. 34.670.976/0001-93, atrave s do "
    "FUNDO MUNICIPAL PARA\nGESTAO DA MOVIMENTACAO DO RECURSOS DO FUNDEB, "
    "localizada na Avenida das Na�o es,\ns/n, Centro, inscrito no CNPJ/MF sob "
    "o n� 30.676.085/0001-93, neste ato representado pela\n"
    "Secreta ria Municipal de Educa�a o e Cultura Senhora AUGUSTA ELIAS P. DE "
    "S. MARTINS, brasileira,\ncasada, inscrita no CPF n� 715.838.586-87, "
    "residente e domiciliada na Rua\nMinas Geais, s/n, Centro, neste Munic� pio, "
    "doravante denominado CONTRATANTE: APFORM\n"
    "INDUSTRIA E COMERCIO DE MOVEIS LTDA, inscrita no Cadastro Nacional de Pessoa "
    "Jur�d ica - CNPJ\nn� 06.198.597/0001-07, sediada na Rua Projetada, "
    "s/n, Lote: 04, Cep 59.280-000, Bairro Distrito\nIndustrial I, Maca� ba "
    "� RN, neste ato representada pelo seu DAMIA O BASTITA DO NASCIMENTO,\n"
    "brasileiro, casado, Portador da Carteira de Identidade n� 30100668 "
    "expedida pela SSP/RN, CPF n�\n090.318.314-50, residente e domiciliado na "
    "Rua Anto nio Lacerda leite, 461, Bairro Vilar,\nMaca� ba/RN. doravante "
    "denominada simplesmente de CONTRATADA, feita na sessa o da referida\n"
    "LICITA�A O, o qual passa a ser parte integrante deste:\n"
    "CL�USULA PRIMEIRA: DO OBJETO\n"
    "1.0 Adesa o ata de Registro de Pre�os n� 007/2023, OBJETO: "
    "Aquisi�a o de mobilia rio para salas de aula.\n"
    "CL�USULA SEGUNDA: DO VALOR\n"
    "O valor global do contrato e de R$ 226.907,60 (duzentos e vinte e seis mil).\n"
)

TERMO_FISCAL_CUMARU = (
    "ESTADO DO PAR�\nPREFEITURA MUNICIPAL DE CUMARU DO NORTE\n"
    "TERMO DE DESIGNA��O\n"
    "Ficam designado os servidores MARCELO MARQUES CARDOSO DE LIMA, Inscrito no "
    "CPF n�.\n036.885.092-77 e RG n� 6869388 SSP/PA, com o cargo de\n"
    "ASSESSOR T�CNICO DE SUPORTE PEDAG�GICO atrav�s da Matricula "
    "n� 4266 como FISCAL TITULAR,\ne JACIARA SANTOS SILVA, Inscrito no CPF "
    "n�. 010.901.452-92 e RG n� 5133621 PC/PA, com o cargo de\n"
    "DIRETORA DE ENSINO DE SUPORTE PEDAG�GICO atrav�s da Matricula "
    "n� 4304 como FISCAL\nSUBSTITUTO para gerenciar o CONTRATO n� "
    "236/2023 celebrado entre FUNDO MUNICIPAL.\n"
)


class TestPdfReal(unittest.TestCase):
    """Regressões do portal de Cumaru do Norte (acentos corrompidos)."""

    def test_contratada_vem_depois_de_denominado_contratante(self):
        # o documento rotula a empresa como "CONTRATANTE:" e só no fim diz
        # "doravante denominada … CONTRATADA" — vale o segundo
        nome, doc = contratada(CONTRATO_CUMARU, cnpj_orgao(CONTRATO_CUMARU))
        self.assertEqual(nome, "APFORM INDUSTRIA E COMERCIO DE MOVEIS LTDA")
        self.assertEqual(doc, "06.198.597/0001-07")

    def test_nao_pega_cnpj_da_prefeitura_nem_do_fundo(self):
        _n, doc = contratada(CONTRATO_CUMARU, cnpj_orgao(CONTRATO_CUMARU))
        self.assertNotIn(doc, ("34.670.976/0001-93", "30.676.085/0001-93"))

    def test_nome_atravessa_quebra_de_linha(self):
        # "APFORM\nINDUSTRIA E COMERCIO…" tem \n no meio da razão social
        nome, _doc = contratada(CONTRATO_CUMARU, cnpj_orgao(CONTRATO_CUMARU))
        self.assertTrue(nome.startswith("APFORM "))

    def test_cpf_do_representante_nao_vira_cpf_cnpj(self):
        _n, doc = contratada(CONTRATO_CUMARU, cnpj_orgao(CONTRATO_CUMARU))
        self.assertNotEqual(doc, "090.318.314-50")

    def test_valor_com_acento_corrompido_no_rotulo(self):
        self.assertEqual(valor_contrato(CONTRATO_CUMARU), "226907.60")

    def test_numero_e_ano(self):
        self.assertEqual(numero_contrato("Contrato N 236-2023.pdf", CONTRATO_CUMARU),
                         "236/2023")
        self.assertEqual(ano_contrato("236/2023"), "2023")

    def test_sem_clausula_de_vigencia_fica_vazio(self):
        # este contrato realmente não tem cláusula de vigência
        self.assertEqual(vigencia(CONTRATO_CUMARU), ("", ""))

    def test_vigencia_com_acento_corrompido(self):
        # "vige ncia" (ê virou "e"+espaço) e "vig?ncia" (virou U+FFFD)
        self.assertEqual(
            vigencia("A vige ncia sera de 02/01/2025 a 31/12/2025."),
            ("02/01/2025", "31/12/2025"),
        )
        self.assertEqual(
            vigencia("A vig�ncia sera de 05/02/2024 a 04/02/2025."),
            ("05/02/2024", "04/02/2025"),
        )

    def test_fiscal_titular_vence_o_substituto(self):
        self.assertEqual(
            fiscal_contrato(TERMO_FISCAL_CUMARU), "MARCELO MARQUES CARDOSO DE LIMA"
        )

    def test_fiscal_nao_arrasta_ficam_designado_os_servidores(self):
        nome = fiscal_contrato(TERMO_FISCAL_CUMARU)
        self.assertNotIn("servidor", nome.lower())
        self.assertNotIn("designad", nome.lower())

    def test_linha_completa_do_pdf_real(self):
        linha = linha_contrato(
            "Contrato N 236-2023.pdf",
            CONTRATO_CUMARU,
            licitacao_origem="001/2023-RPPP",
            texto_portaria=TERMO_FISCAL_CUMARU,
        )
        self.assertEqual(linha["numero"], "236/2023")
        self.assertEqual(linha["ano"], "2023")
        self.assertEqual(linha["nome_razao_social"],
                         "APFORM INDUSTRIA E COMERCIO DE MOVEIS LTDA")
        self.assertEqual(linha["cpf_cnpj"], "06.198.597/0001-07")
        self.assertEqual(linha["valor"], "226907.60")
        self.assertEqual(linha["fiscal_contrato"], "MARCELO MARQUES CARDOSO DE LIMA")
        self.assertEqual(falta_para_o_portal(linha), [])


class TestArquivoFiscal(unittest.TestCase):
    def test_termo_fiscal_e_reconhecido_como_portaria(self):
        from gestor_regras.contratos import (
            eh_arquivo_contrato,
            eh_arquivo_portaria_fiscal,
        )

        self.assertTrue(eh_arquivo_portaria_fiscal("Termo Fiscal 236-2023.pdf"))
        self.assertTrue(eh_arquivo_portaria_fiscal("Termo de Designação.pdf"))
        self.assertTrue(eh_arquivo_portaria_fiscal("Portaria Fiscal 45-2025.pdf"))
        # e o contrato continua sendo contrato
        self.assertTrue(eh_arquivo_contrato("Contrato Nº 236-2023.pdf"))
        self.assertFalse(eh_arquivo_portaria_fiscal("Contrato Nº 236-2023.pdf"))


if __name__ == "__main__":
    unittest.main()
