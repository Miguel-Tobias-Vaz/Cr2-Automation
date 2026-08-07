# -*- coding: utf-8 -*-
"""Constantes do Front para planilhas de upload (portado do Gestor V1)."""

NAO_INFORMADO = "Não informado"

CAMPOS_FRONT = [
    ("modalidade", "Modalidade"),
    ("numero", "Número"),
    ("ano", "Ano"),
    ("objeto", "Objeto"),
    ("data_publicacao", "Data de Publicação"),
    ("data_abertura", "Data de Abertura"),
    ("valor_estimado", "Valor Estimado"),
    ("situacao", "Situação da Licitação"),
    ("valor_homologado", "Valor Homologado"),
]

ROTULOS = {c[0]: c[1] for c in CAMPOS_FRONT}

CAMPOS_OBRIGATORIOS_FRONT = (
    "modalidade", "numero", "ano", "objeto", "situacao",
)

# Lista oficial (sigla → nome). Ordem = tabela Front.
MODALIDADES = [
    "Adesão a Ata de Registro de Preço",       # AD
    "Credenciamento",                          # CR
    "Concorrência",                            # CC
    "Concurso",                                # CON
    "Carona",                                  # CA
    "Contratação Direta",                      # CD
    "Convite",                                 # CV
    "Chamada Pública",                         # CP
    "Diálogo Competitivo",                     # DC
    "Dispensa de Licitação",                   # DL
    "Inexigibilidade de Licitação",            # IN
    "Leilão",                                  # LL
    "Pregão Eletrônico",                       # PE
    "Pregão Presencial",                       # PP
    "Registro de Preços Originário de Chamamento Público",  # RPCP
    "Registro de Preços Originário de Pregão Eletrônico",   # RPPE
    "Registro de Preços Originário de Pregão Presencial",   # RPPP
    "Tomada de Preços",                        # TP
    "Não houve Processos Licitatórios",
    NAO_INFORMADO,
]

SITUACOES = [
    "Aberto",
    "Anulado",
    "Cancelado",
    "Deserto",
    "Em andamento",
    "Finalizado",
    "Fracassado",
    "Publicada",
    "Revogado",
    "Suspenso",
    NAO_INFORMADO,
]

SIGLAS = {
    "Adesão a Ata de Registro de Preço": "AD",
    "Credenciamento": "CR",
    "Concorrência": "CC",
    "Concurso": "CON",
    "Carona": "CA",
    "Contratação Direta": "CD",
    "Convite": "CV",
    "Chamada Pública": "CP",
    "Diálogo Competitivo": "DC",
    "Dispensa de Licitação": "DL",
    "Inexigibilidade de Licitação": "IN",
    "Leilão": "LL",
    "Pregão Eletrônico": "PE",
    "Pregão Presencial": "PP",
    "Registro de Preços Originário de Chamamento Público": "RPCP",
    "Registro de Preços Originário de Pregão Eletrônico": "RPPE",
    "Registro de Preços Originário de Pregão Presencial": "RPPP",
    "Tomada de Preços": "TP",
}

MODALIDADE_REGISTRO_PRECOS = {
    "Pregão Eletrônico": "Registro de Preços Originário de Pregão Eletrônico",
    "Pregão Presencial": "Registro de Preços Originário de Pregão Presencial",
    "Chamada Pública": "Registro de Preços Originário de Chamamento Público",
}

# Situações usadas pelo script CR2 -> Front
MAPA_SITUACAO = {
    "homologada": "Finalizado",
    "homologado": "Finalizado",
    "adjudicada": "Finalizado",
    "adjudicado": "Finalizado",
    "ratificada": "Finalizado",
    "ratificado": "Finalizado",
    "deserta": "Deserto",
    "deserto": "Deserto",
    "fracassada": "Fracassado",
    "fracassado": "Fracassado",
    "revogada": "Revogado",
    "revogado": "Revogado",
    "anulada": "Anulado",
    "anulado": "Anulado",
    "cancelada": "Cancelado",
    "cancelado": "Cancelado",
    "suspensa": "Suspenso",
    "suspenso": "Suspenso",
    "publicada": "Publicada",
    "aberto": "Aberto",
    "aberta": "Aberto",
    "em andamento": "Em andamento",
    "finalizado": "Finalizado",
    "finalizada": "Finalizado",
}

ARQ_MODELO_LICITACOES = "subirLicitacoes.xlsx"
ARQ_MODELO_DOCUMENTOS = "subirDocumentosLicitacoes.xlsx"
ABA_LICITACOES = "Modelo_Licitacoes - Planilha"
ABA_DOCUMENTOS = "UploadLicitacao - Página1"

