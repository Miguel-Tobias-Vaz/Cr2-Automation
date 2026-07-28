#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
 BAIXADOR + EXTRATOR DE LICITAÇÕES — Portais CR2 (padrão: Prefeitura de Gurupá)
 v2 — revisado
==============================================================================

SCRIPT ÚNICO. Faz tudo:
  1) Coleta as licitações (API REST do WordPress; fallback: raspagem HTML com
     varredura sequencial de páginas /page/N/)
  2) Baixa os anexos, organizados em pastas por licitação
  3) Lê o texto de cada documento (OCR automático quando o PDF é digitalizado;
     resultado do OCR é cacheado em .ocr.txt e reaproveitado nas próximas rodadas)
  4) Extrai VALOR ESTIMADO e VALOR HOMOLOGADO (+ data de abertura e situação)
  5) Preenche a planilha-modelo (Front.xlsx) — 1 linha por licitação
  6) Gera uma aba de AUDITORIA com a origem de cada valor (documento + trecho)

Genérico: a entidade é derivada da URL de --listagem. O padrão é Gurupá,
mas funciona em qualquer portal CR2 trocando --listagem.

A planilha-modelo deve ter os cabeçalhos na linha 1:
  Modalidade | Número | Ano | Objeto | Data de Publicação |
  Data de Abertura | Valor Estimado | Situação da Licitação | Valor Homologado

------------------------------------------------------------------------------
 REQUISITOS
------------------------------------------------------------------------------
  pip install requests beautifulsoup4 openpyxl pdfplumber

  OCR (opcional, para PDFs digitalizados):
    pip install ocrmypdf            (+ Tesseract-OCR "por" + Ghostscript)
      Windows: Tesseract  -> https://github.com/UB-Mannheim/tesseract/wiki
               Ghostscript -> https://ghostscript.com/releases/gsdnld.html
    OU, backend alternativo:
    pip install pytesseract pdf2image   (+ Tesseract + Poppler)

  EasyOCR (opcional — motor de reserva p/ scans ruins; lento sem GPU):
    pip install easyocr pdf2image numpy
    (baixa ~64MB de modelos na 1ª execução; usado no modo MOTOR_OCR="auto"
     quando o resultado do Tesseract vem fraco, ou com --motor-ocr easyocr)

------------------------------------------------------------------------------
 USO
------------------------------------------------------------------------------
  python baixar_licitacoes.py --planilha-modelo Front.xlsx
  python baixar_licitacoes.py --planilha-modelo Front.xlsx --ocr
  python baixar_licitacoes.py --so-planilha        (não rebaixa; só extrai/preenche)
  python baixar_licitacoes.py --listagem https://OUTRA.pa.gov.br/c/licitacoes/ --ocr
  python baixar_licitacoes.py --ignorar-ssl        (portais com certificado quebrado)
==============================================================================
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

# Console Windows legado pode não aceitar UTF-8; evita crash em prints
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


class Cancelado(Exception):
    """Fila interrompida pelo usuario (centro-automacoes)."""


def pedido_cancelado():
    return False


def _abortar_se_cancelado():
    if pedido_cancelado():
        print("  [AVISO] Fila cancelada pelo usuario.")
        raise Cancelado()


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
LISTAGEM_PADRAO = "https://cmbrasilnovo.pa.gov.br/c/licitacoes"
SAIDA_PADRAO    = r"C:\Downloads\Licitacoes_CM Brasil Novo"
PLANILHA_SAIDA  = "Licitacoes_preenchida.xlsx"
SUBCATEGORIAS   = ["licitacoes-fracassadas", "licitacoes-desertas"]
MAX_PAGINAS     = 300     # trava de segurança na varredura de /page/N/

# ----------------------------------------------------------------------------
# FILTRO DE ANOS — edite aqui (ou use --anos 2023,2024 na linha de comando).
# Lista vazia = baixa TODOS os anos.
#   Exemplos:  ANOS_FILTRO = ["2023"]
#              ANOS_FILTRO = ["2022", "2023", "2024"]
# ----------------------------------------------------------------------------
ANOS_FILTRO = ["2023"]

# ----------------------------------------------------------------------------
# RENOMEAÇÃO PELO TÍTULO INTERNO — quando o nome do anexo é genérico
# ("Download", "documento", "anexo1"...), o script lê o título dentro do
# PDF (via texto nativo ou OCR) e renomeia o arquivo por ele.
#   True  = renomeia automaticamente
#   False = mantém os nomes originais dos links
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# MOTOR DE OCR — edite aqui (ou use --motor-ocr na linha de comando).
#   "auto"      = Tesseract primeiro (rápido); se o resultado vier ruim
#                 (curto/ilegível) e o EasyOCR estiver instalado, refaz com
#                 EasyOCR e usa o melhor dos dois.  <- RECOMENDADO
#   "tesseract" = só Tesseract (ocrmypdf/pytesseract)
#   "easyocr"   = só EasyOCR (deep learning; melhor em scans ruins, bem mais
#                 lento sem GPU). Instalação: pip install easyocr
#                 (baixa ~64MB de modelos na primeira execução)
# ----------------------------------------------------------------------------
MOTOR_OCR = "auto"

RENOMEAR_POR_TITULO = True

EXT_DOCS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".txt", ".csv", ".odt", ".ods", ".p7s", ".xml",
}
EXT_TEXTAVEIS = {".pdf"}

HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0 Safari/537.36")}
PAUSA, TENTATIVAS, TIMEOUT = 0.5, 3, 90

MODALIDADES_RE = re.compile(
    r"(preg[aã]o|inexigibilidade|dispensa|convite|tomada\s+de\s+pre[çc]os?|"
    r"concorr[eê]ncia|chamamento|credenciamento|leil[aã]o|concurso|"
    r"ades[aã]o|registro\s+de\s+pre[çc]os|rdc|"
    r"n[aã]o\s+houve\s+ades|comunicado\s+da\s+comiss[aã]o)", re.IGNORECASE)

COLUNAS = ["Modalidade", "Número", "Ano", "Objeto", "Data de Publicação",
           "Data de Abertura", "Valor Estimado", "Situação da Licitação",
           "Valor Homologado"]


# ============================================================================
# PARTE 1 — EXTRATOR DE CAMPOS  (valores, datas, situação)
# ============================================================================
def sem_acento(txt):
    """Remove acentos preservando o comprimento (1 char -> 1 char)."""
    return "".join(c for c in unicodedata.normalize("NFKD", txt)
                   if not unicodedata.combining(c))


def normaliza(txt):
    """minúsculo, sem acento, espaços colapsados — só para TESTES DE PERTENCIMENTO
    (nunca use as posições deste texto para fatiar o original)."""
    return re.sub(r"\s+", " ", sem_acento(txt).lower())


def normaliza_com_mapa(txt):
    """Normaliza colapsando espaços, MAS devolve também um mapa de posições:
    mapa[i] = índice, no texto ORIGINAL, do caractere norm[i].
    Isso permite achar um rótulo no texto normalizado e fatiar o original
    na posição correta — corrige o desalinhamento causado pelo colapso."""
    base = sem_acento(txt).lower()          # preserva comprimento
    norm_chars, mapa = [], []
    prev_space = False
    for i, ch in enumerate(base):
        if ch.isspace():
            if prev_space:
                continue
            norm_chars.append(" ")
            mapa.append(i)
            prev_space = True
        else:
            norm_chars.append(ch)
            mapa.append(i)
            prev_space = False
    return "".join(norm_chars), mapa


# --- Moeda brasileira: 1.234.567,89 ---
RE_MOEDA = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?![\d])")
# Com prefixo R$ aceitamos também valores SEM centavos ("R$ 1.500.000"),
# forma comum em avisos e ratificações. O prefixo evita capturar números
# soltos (datas, nº de processo). Aceita "RS" — OCR frequentemente lê o
# cifrão como a letra S.
RE_MOEDA_RS = re.compile(
    r"r\s*[\$s]\s*(\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+,\d{2})", re.IGNORECASE)


def primeiro_valor(trecho):
    """Primeiro valor monetário do trecho, tentando o padrão completo e o
    padrão prefixado por R$. Retorna float ou None."""
    m1 = RE_MOEDA.search(trecho)
    m2 = RE_MOEDA_RS.search(trecho)
    cands = []
    if m1:
        cands.append((m1.start(), m1.group(1)))
    if m2:
        cands.append((m2.start(), m2.group(1)))
    if not cands:
        return None
    cands.sort()                     # o que aparece primeiro após o rótulo
    txt = cands[0][1]
    if "," not in txt:               # sem centavos: só aceito se veio de R$
        txt += ",00"
    return para_float(txt)


def para_float(txt_moeda):
    if not txt_moeda:
        return None
    try:
        return round(float(txt_moeda.strip().replace(".", "").replace(",", ".")), 2)
    except ValueError:
        return None


ROTULOS_ESTIMADO = [
    "valor total estimado", "valor global estimado", "valor estimado",
    "valor total de referencia", "valor de referencia", "valor referencia",
    "valor maximo", "valor total maximo", "preco maximo", "preco estimado",
    "valor total previsto", "importancia estimada", "valor orcado",
    # ampliação (vocabulário real dos documentos):
    "total estimado", "estimado em", "estimada em", "orcado em",
    "custo estimado", "valor previsto", "preco de referencia",
    "valor medio estimado", "media dos precos", "valor da estimativa",
    "estimativa de preco", "estimativa de custo", "valor de mercado",
    "totalizando a estimativa", "cujo valor estimado",
    "despesa estimada", "valor da despesa estimada", "estimado no valor",
    "valor global maximo", "valor teto", "limite maximo",
]
ROTULOS_HOMOLOGADO = [
    "valor homologado", "valor adjudicado", "valor total homologado",
    "valor global", "valor total do contrato", "valor do contrato",
    "valor contratado", "valor da contratacao", "valor total adjudicado",
    "homologo o", "adjudico o", "no valor global de", "no valor total de",
    # ampliação (vocabulário real dos documentos):
    "perfazendo o valor", "perfazendo um total", "perfazendo a importancia",
    "importancia de", "pela importancia de", "no valor de",
    "pelo valor de", "pelo valor global", "com o valor de",
    "vencedora com o valor", "melhor proposta no valor",
    "proposta no valor", "proposta vencedora no valor",
    "valor final", "valor arrematado", "totalizando",
    "valor total de", "valor total", "montante de", "no montante de",
    "valor global do contrato", "valor anual", "valor mensal estimado do contrato",
    "contratado por", "adjudicado por", "homologado no valor",
    "adjudicado no valor", "valor da proposta", "valor negociado",
    "apos negociacao", "lance final", "melhor lance", "lance vencedor",
    "quantia de", "pela quantia de", "importe de", "no importe de",
    "soma de", "pela soma de", "vencedora do certame com",
]
REFORCO_TOTAL = ["total", "global", "geral"]

DOCS_ESTIMADO = [
    "termo de referencia", "termo referencia", "pesquisa de mercado",
    "pesquisa de preco", "analise de preco", "mapa de preco",
    "aviso de licitacao", "aviso", "edital",
]
DOCS_HOMOLOGADO = [
    "homologacao", "adjudicacao", "termo de adjudicacao",
    "ata sessao", "ata de sessao", "ata de julgamento", "ata julgamento",
    "resultado", "contrato administrativo", "contrato",
]


def _janela_valor(texto_orig, rotulos, janela=200):
    """Procura cada rótulo (em texto normalizado) e captura o 1º valor
    monetário logo após ele NO TEXTO ORIGINAL, usando o mapa de posições.
    Retorna lista de tuplas (valor_float, rotulo, tem_reforco_total, trecho)."""
    tnorm, mapa = normaliza_com_mapa(texto_orig)
    achados = []
    for rot in rotulos:
        inicio = 0
        while True:
            pos = tnorm.find(rot, inicio)
            if pos == -1:
                break
            inicio = pos + len(rot)
            # posição do FIM do rótulo, mapeada de volta ao texto original
            fim_norm = pos + len(rot)
            orig_fim = mapa[fim_norm] if fim_norm < len(mapa) else len(texto_orig)
            orig_ini = mapa[pos]
            trecho = texto_orig[orig_fim: orig_fim + janela]
            val = primeiro_valor(trecho)
            if val and val > 0:
                contexto = texto_orig[orig_ini: orig_fim + janela]
                reforco = any(r in normaliza(contexto) for r in REFORCO_TOTAL)
                achados.append((val, rot, reforco,
                                re.sub(r"\s+", " ", contexto).strip()[:120]))
    return achados


def extrair_valor(texto, tipo):
    rotulos = ROTULOS_ESTIMADO if tipo == "estimado" else ROTULOS_HOMOLOGADO
    achados = _janela_valor(texto, rotulos)
    if not achados:
        return None
    achados.sort(key=lambda x: (x[2], x[0]), reverse=True)
    melhor = achados[0]
    vistos, candidatos = set(), []
    for v, rot, ref, tr in achados:
        if v not in vistos:
            vistos.add(v)
            candidatos.append({"valor": v, "rotulo": rot, "trecho": tr})
    return {"valor": melhor[0], "rotulo": melhor[1], "reforco": melhor[2],
            "trecho": melhor[3], "candidatos": candidatos}


MESES = {"janeiro":1,"fevereiro":2,"marco":3,"abril":4,"maio":5,"junho":6,
         "julho":7,"agosto":8,"setembro":9,"outubro":10,"novembro":11,"dezembro":12}
RE_DATA_NUM  = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b")
RE_DATA_NUM2 = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2})\b(?![\d/.\-])")
RE_DATA_EXT  = re.compile(r"\b(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})\b")
ROTULOS_ABERTURA = [
    "data de abertura", "abertura da sessao", "abertura das propostas",
    "sessao publica", "data da sessao", "recebimento das propostas",
    "abertura", "realizar-se-a", "sera realizada", "data e horario",
    # ampliação (vocabulário real dos avisos/editais):
    "ocorrera no dia", "ocorrera em", "marcada para", "prevista para",
    "designada para", "agendada para", "no dia", "do dia",
    "as propostas serao recebidas", "inicio da sessao", "data da abertura",
    "data limite", "credenciamento", "disputa de lances",
    "sessao de disputa", "abertura dos envelopes", "entrega dos envelopes",
    "recebimento dos envelopes", "protocolo dos envelopes",
    "data do certame", "data da licitacao", "realizacao do certame",
]

RE_HORA_ADIANTE = re.compile(r"^.{0,20}?\b\d{1,2}\s*[:h]\s*\d{0,2}\b")


def _tem_hora_apos(trecho_norm_apos):
    """True se logo após a data há um horário ('as 09:00', '09h', '9 h 30') —
    assinatura típica da data de SESSÃO, e não de outras datas do documento."""
    return bool(RE_HORA_ADIANTE.search(trecho_norm_apos))


def data_valida(d, mth, y):
    """Valida calendário real (evita 31/02 vindo de OCR ruim)."""
    try:
        datetime(y, mth, d)
        return True
    except ValueError:
        return False


def _datas_no_trecho(trecho_norm):
    """Todas as datas válidas num trecho normalizado, na ordem, como
    (data, tem_hora) — tem_hora=True quando um horário segue a data."""
    achadas = []
    def _add(m, d, mth, y):
        if data_valida(d, mth, y):
            hora = _tem_hora_apos(trecho_norm[m.end(): m.end() + 25])
            achadas.append((m.start(), (d, mth, y), hora))
    for m in RE_DATA_NUM.finditer(trecho_norm):
        _add(m, int(m[1]), int(m[2]), int(m[3]))
    for m in RE_DATA_EXT.finditer(trecho_norm):
        if m[2] in MESES:
            _add(m, int(m[1]), MESES[m[2]], int(m[3]))
    for m in RE_DATA_NUM2.finditer(trecho_norm):
        y2 = int(m[3])
        _add(m, int(m[1]), int(m[2]), 2000 + y2 if y2 <= 79 else 1900 + y2)
    achadas.sort(key=lambda x: x[0])
    return [(d, h) for _, d, h in achadas]


def extrair_data_abertura(texto):
    """Busca de datas: feita inteiramente no texto normalizado (datas
    numéricas sobrevivem à normalização), sem fatiar o original.
    1) tenta cada rótulo e pega a 1ª data válida na janela após ele;
    2) sem rótulo, retorna None (o chamador pode usar o fallback)."""
    tnorm, _ = normaliza_com_mapa(texto)
    for rot in ROTULOS_ABERTURA:
        pos = tnorm.find(rot)
        if pos == -1:
            continue
        datas = _datas_no_trecho(tnorm[pos: pos + 220])
        if datas:
            return datas[0][0]
    return None


def datas_do_documento(texto):
    """Todas as datas válidas do documento, na ordem em que aparecem, como
    (data, tem_hora). Usada como fallback quando nenhum rótulo casa."""
    tnorm, _ = normaliza_com_mapa(texto)
    return _datas_no_trecho(tnorm)


def eh_contratacao_direta(modalidade):
    """Dispensa, Inexigibilidade, Contratação Direta, Adesão e Carona não
    têm sessão pública de abertura de propostas (Lei 8.666 arts. 24/25;
    Lei 14.133 arts. 74/75): o rito de conclusão é a RATIFICAÇÃO."""
    m = normaliza(modalidade or "")
    return ("dispensa" in m or "inexigibilidade" in m
            or "contratacao direta" in m or "adesao" in m or "carona" in m)


# ============================================================================
# BIBLIOTECA DE MODALIDADES — nomes padronizados na planilha
# ============================================================================
MODALIDADES_PADRAO = [
    "Adesão a Ata de Registro de Preço",
    "Carona",
    "Credenciamento",
    "Concorrência",
    "Concurso",
    "Convite",
    "Chamada Pública",
    "Diálogo Competitivo",
    "Dispensa de Licitação",
    "Inexigibilidade de Licitação",
    "Intenção de Registro de Preços",
    "Leilão",
    "Pregão Eletrônico",
    "Pregão Presencial",
    "Registro de Preços Originário de Chamamento Público",
    "Registro de Preços Originário de Pregão Eletrônico",
    "Registro de Preços Originário de Pregão Presencial",
    "Tomada de Preços",
    "Contratação Direta",
]

# Regras de reconhecimento, avaliadas EM ORDEM (da mais específica para a
# mais genérica). Cada regra: (termos que DEVEM aparecer, nome padrão).
# Os termos são testados no título normalizado (minúsculo, sem acento).
_REGRAS_MODALIDADE = [
    # --- compostas de Registro de Preços (SRP) primeiro ---
    (["pregao", "eletronico", "srp"],       "Registro de Preços Originário de Pregão Eletrônico"),
    (["pregao", "eletronico", "registro de precos"],
                                            "Registro de Preços Originário de Pregão Eletrônico"),
    (["pregao", "presencial", "srp"],       "Registro de Preços Originário de Pregão Presencial"),
    (["pregao", "presencial", "registro de precos"],
                                            "Registro de Preços Originário de Pregão Presencial"),
    (["chamamento", "registro de precos"],  "Registro de Preços Originário de Chamamento Público"),
    (["chamada publica", "registro de precos"],
                                            "Registro de Preços Originário de Chamamento Público"),
    (["intencao de registro"],              "Intenção de Registro de Preços"),
    # --- adesão / carona ---
    (["adesao"],                            "Adesão a Ata de Registro de Preço"),
    (["carona"],                            "Carona"),
    # --- contratação direta e afins ---
    (["dispensa"],                          "Dispensa de Licitação"),
    (["inexigibilidade"],                   "Inexigibilidade de Licitação"),
    (["contratacao direta"],                "Contratação Direta"),
    # --- demais modalidades ---
    (["dialogo competitivo"],               "Diálogo Competitivo"),
    (["credenciamento"],                    "Credenciamento"),
    (["chamada publica"],                   "Chamada Pública"),
    (["chamamento publico"],                "Chamada Pública"),
    (["chamamento"],                        "Chamada Pública"),
    (["concorrencia"],                      "Concorrência"),
    (["concurso"],                          "Concurso"),
    (["carta convite"],                     "Convite"),
    (["convite"],                           "Convite"),
    (["leilao"],                            "Leilão"),
    (["tomada de preco"],                   "Tomada de Preços"),
    (["pregao", "eletronico"],              "Pregão Eletrônico"),
    (["pregao", "presencial"],              "Pregão Presencial"),
]


def modalidade_padrao(titulo):
    """Converte o texto de modalidade do título para o nome PADRÃO da
    biblioteca. Regras específicas primeiro (SRP antes de pregão simples).
    Pregão sem qualificação: decide pelo prefixo do número (PE/PP) e, na
    ausência, assume Pregão Presencial se o padrão 'PP' aparecer, senão
    Pregão Eletrônico (forma predominante desde 2020).
    Sem correspondência: devolve o texto original (para não perder dado)."""
    t = normaliza(titulo)
    for termos, padrao in _REGRAS_MODALIDADE:
        if all(term in t for term in termos):
            return padrao
    if "pregao" in t:
        # decide pelo prefixo do número: PPRP/PP -> presencial; PERP/PE -> eletrônico
        if re.search(r"\bpp(rp)?\b", t):
            return "Pregão Presencial"
        if re.search(r"\bpe(rp)?\b", t):
            return "Pregão Eletrônico"
        return "Pregão Eletrônico"
    mod, _ = split_modalidade_numero(titulo)
    return mod.strip().title() if mod else titulo.strip().title()


# ============================================================================
# TÍTULO INTERNO DO DOCUMENTO — para renomear anexos com nome genérico
# ============================================================================
# Padrões de título que os documentos oficiais trazem no cabeçalho.
# Avaliados em ordem; o primeiro que casar nas linhas iniciais vence.
_TITULOS_DOC = [
    "termo de homologacao", "termo de adjudicacao", "termo de ratificacao",
    "termo de referencia", "termo de dispensa", "termo de inexigibilidade",
    "ata de registro de precos", "ata de julgamento", "ata da sessao",
    "ata de sessao", "ata de abertura", "ata de recebimento",
    "aviso de licitacao", "aviso de resultado", "aviso de homologacao",
    "extrato de contrato", "extrato de dispensa", "extrato de inexigibilidade",
    "extrato de ata", "extrato de termo aditivo", "extrato",
    "contrato administrativo", "termo de contrato", "contrato",
    "termo aditivo", "apostilamento",
    "edital de licitacao", "edital de pregao", "edital de chamamento",
    "edital de credenciamento", "edital",
    "parecer juridico", "parecer tecnico", "parecer",
    "projeto basico", "planilha orcamentaria", "cronograma fisico",
    "memorial descritivo", "mapa de precos", "mapa comparativo",
    "pesquisa de precos", "pesquisa de mercado", "cotacao de precos",
    "ordem de servico", "ordem de compra", "portaria",
    "justificativa", "autorizacao", "solicitacao de despesa",
    "resultado de julgamento", "resultado do julgamento", "resultado",
    "recurso administrativo", "contrarrazoes", "impugnacao",
    "certidao", "declaracao", "despacho", "homologacao", "adjudicacao",
    "ratificacao",
]

# Nomes de link considerados genéricos (não descrevem o documento).
_NOMES_GENERICOS = re.compile(
    r"^(download|documento|anexo|arquivo|clique( aqui)?|abrir|visualizar|"
    r"pdf|doc(umento)? ?\d*|anexo ?\d*|arquivo ?\d*|sem_nome|untitled|"
    r"scan(ned)?[\w\- ]*|img[\w\- ]*|image[\w\- ]*|digitalizad[oa][\w\- ]*|"
    r"\d+|[\d\-_ .]+)$",
    re.IGNORECASE)


def nome_eh_generico(nome_sem_ext):
    """True se o nome do arquivo não descreve o conteúdo."""
    n = nome_sem_ext.strip()
    return bool(_NOMES_GENERICOS.match(n)) or len(n) <= 3


def titulo_interno(texto, max_linhas=40):
    """Encontra o título real do documento nas primeiras linhas do texto
    (nativo ou OCR). Prefere a linha que contém um padrão conhecido de
    documento oficial; retorna o texto da linha limpo, ou ''. """
    if not texto:
        return ""
    linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()][:max_linhas]
    melhor, melhor_rank = "", -1
    for ln in linhas:
        if len(ln) > 90:            # títulos são curtos
            continue
        n = normaliza(ln)
        for idx, padrao in enumerate(_TITULOS_DOC):
            if padrao in n:
                # padrões no INÍCIO da lista são mais específicos:
                # rank maior = mais específico
                rank = len(_TITULOS_DOC) - idx
                if rank > melhor_rank:
                    melhor, melhor_rank = ln, rank
                break               # primeiro padrão (mais específico) da linha
    if not melhor:
        return ""
    # limpeza: colapsa espaços, remove pontuação de borda
    t = re.sub(r"\s+", " ", melhor).strip(" .:-–—_|")
    return t[:100]


def inferir_situacao(titulo, nomes_docs, modalidade=""):
    """Deduz a situação APENAS do título e dos NOMES dos documentos.
    (Não usa o texto interno: editais normais contêm frases-padrão como
    'caso a licitação seja considerada deserta...', que geravam falso
    positivo.) Aplica o rito correto por modalidade: contratação direta
    conclui por ratificação; certames concorrenciais, por homologação."""
    t = normaliza(titulo)
    docs = normaliza(" ".join(nomes_docs))
    if "deserta" in t or "deserta" in docs:
        return "Deserta"
    if "fracassada" in t or "fracassada" in docs:
        return "Fracassada"
    if "revogacao" in docs or "revogada" in docs or "revogado" in docs:
        return "Revogada"
    if "anulacao" in docs or "anulada" in docs or "anulado" in docs:
        return "Anulada"
    if eh_contratacao_direta(modalidade):
        # Rito da contratação direta: ratificação (e o contrato/extrato
        # publicado é evidência de conclusão do processo).
        if ("ratificacao" in docs or "ratificado" in docs or "ratificada" in docs
                or "extrato" in docs or "contrato" in docs):
            return "Ratificada"
        return ""
    if "homologacao" in docs or "homologado" in docs or "homologada" in docs:
        return "Homologada"
    if "adjudicacao" in docs or "adjudicado" in docs or "adjudicada" in docs:
        return "Adjudicada"
    return ""


# ============================================================================
# PARTE 2 — NOMES DE ARQUIVO / PASTA / TÍTULO
# ============================================================================
ILEGAL     = re.compile(r'[:\*\?"<>|\r\n\t]')
MARCADOR_N = re.compile(r"\bN\s*[ºoO°\.]+\s*", re.IGNORECASE)
RE_ANO     = re.compile(r"(?:19|20)\d{2}")


def limpa_nome(texto, maxlen=180):
    if not texto:
        return "sem_nome"
    texto = texto.strip().replace("/", "-").replace("\\", "-")
    texto = ILEGAL.sub("", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" .")
    return texto[:maxlen].strip(" .") or "sem_nome"


def split_modalidade_numero(titulo):
    base = titulo.split("(")[0].strip()
    m = MARCADOR_N.search(base)
    if not m:
        return base.strip(), ""
    return base[:m.start()].strip(" -–—"), base[m.end():].strip(" -–—")


def extrai_ano(numero):
    """Ano da licitação. Usa a ÚLTIMA ocorrência de 19xx/20xx, que é o ano
    (a primeira pode ser parte do número, ex.: '202301/2024-CPL')."""
    achados = RE_ANO.findall(numero or "")
    return achados[-1] if achados else ""


def extrai_objeto(titulo):
    m = re.search(r"\((.*)\)\s*$", titulo.strip(), re.DOTALL)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def nome_pasta(titulo):
    mod, num = split_modalidade_numero(titulo)
    return limpa_nome(f"{mod} {num}") if num else limpa_nome(mod or titulo)


def nome_arquivo_bruto(texto_link, url):
    """Nome como nas versões anteriores (sem capitalização) — usado para
    reconhecer e migrar arquivos baixados por rodadas antigas."""
    ext = os.path.splitext(urlparse(url).path)[1].lower() or ".pdf"
    base = limpa_nome(texto_link) or limpa_nome(
        unquote(os.path.basename(urlparse(url).path)))
    return base if base.lower().endswith(ext) else f"{base}{ext}"


def nome_arquivo(texto_link, url):
    return capitaliza_nome_arquivo(nome_arquivo_bruto(texto_link, url))


def variante_numerada(arquivo, i):
    raiz, ext = os.path.splitext(arquivo)
    return f"{raiz} ({i}){ext}"


# ----------------------------------------------------------------------------
# Capitalização de nomes de arquivo (padrão de título em português)
# ----------------------------------------------------------------------------
# Conectivos ficam minúsculos (exceto como primeira palavra).
_CONECTIVOS = {
    "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas",
    "a", "o", "as", "os", "ao", "aos", "para", "por", "com", "sem",
    "sob", "sobre", "que",
}
# Siglas comuns em documentos de licitação: preservadas em MAIÚSCULO.
_SIGLAS = {
    "srp", "arp", "rp", "cpl", "cmp", "pmg", "pe", "pp", "pprp", "perp",
    "tp", "cc", "rdc", "cnpj", "cpf", "me", "epp", "ltda", "eireli",
    "fme", "fms", "fmas", "fundeb", "semed", "semus", "sead", "pgm",
}


def capitaliza_nome_arquivo(nome):
    """'TERMO DE HOMOLOGAÇÃO.PDF' -> 'Termo de Homologação.pdf'.
    Regras: 1ª letra de cada palavra maiúscula; conectivos minúsculos
    (exceto no início); siglas conhecidas em maiúsculo; palavras com
    dígitos/ordinais (059.2023, Nº, 1º) ficam como estão; extensão
    minúscula."""
    raiz, ext = os.path.splitext(nome)
    saida = []
    for i, p in enumerate(raiz.split(" ")):
        if not p:
            continue
        if any(ch.isdigit() for ch in p) or "º" in p or "°" in p:
            saida.append(p)                    # números, ordinais, códigos
            continue
        pl = p.lower()
        if pl in _SIGLAS:
            saida.append(pl.upper())
        elif i > 0 and pl in _CONECTIVOS:
            saida.append(pl)
        else:
            saida.append(pl[:1].upper() + pl[1:])
    return " ".join(saida) + ext.lower()


def caminho_unico_arquivo(pasta, novo_nome, arquivo_atual):
    """Caminho livre para renomear `arquivo_atual` como `novo_nome` dentro
    de `pasta`. Se já existir OUTRO arquivo com esse nome, numera; se o
    destino for o próprio arquivo, devolve-o inalterado."""
    destino = os.path.join(pasta, novo_nome)
    if os.path.abspath(destino) == os.path.abspath(arquivo_atual):
        return arquivo_atual
    if not os.path.exists(destino):
        return destino
    i = 2
    while True:
        cand = os.path.join(pasta, variante_numerada(novo_nome, i))
        if os.path.abspath(cand) == os.path.abspath(arquivo_atual):
            return arquivo_atual
        if not os.path.exists(cand):
            return cand
        i += 1


def eh_anexo(url):
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext not in EXT_DOCS:
        return False
    return "/wp-content/themes/" not in url and "/wp-content/plugins/" not in url


def eh_artefato_ocr(nome):
    """True para subprodutos do OCR (.ocr.pdf / .ocr.txt) e temporários."""
    n = nome.lower()
    return n.endswith(".ocr.pdf") or n.endswith(".ocr.txt") or n.endswith(".part")


# ============================================================================
# PARTE 3 — COLETA (API REST + fallback HTML com varredura de páginas)
# ============================================================================
def extrair_anexos(html, url_base):
    soup = BeautifulSoup(html, "html.parser")
    # Preferimos o contêiner do post; se não houver, o documento inteiro
    # (eh_anexo já filtra imagens de tema/plugin). NÃO usamos seletores de
    # page-builder (Elementor tem dezenas de containers e select_one pegava
    # o errado, zerando os anexos).
    conteudo = soup.select_one(
        ".entry-content, .post-content, .single-content, article, main")
    if conteudo is not None:
        achados = _links_anexo(conteudo, url_base)
        if achados:
            return achados
    return _links_anexo(soup, url_base)


def _links_anexo(no, url_base):
    vistos, anexos = set(), []
    for a in no.find_all("a", href=True):
        href = urljoin(url_base, a["href"].strip())
        if eh_anexo(href) and href not in vistos:
            vistos.add(href)
            anexos.append((a.get_text(strip=True) or "", href))
    return anexos


def descobrir_categoria_id(sessao, base, slug):
    r = sessao.get(f"{base}/wp-json/wp/v2/categories",
                   params={"slug": slug}, timeout=TIMEOUT)
    r.raise_for_status()
    dados = r.json()
    return dados[0]["id"] if isinstance(dados, list) and dados else None


def coletar_posts_api(sessao, base, cat_id):
    posts, pagina = [], 1
    while pagina <= MAX_PAGINAS:
        r = sessao.get(f"{base}/wp-json/wp/v2/posts", timeout=TIMEOUT, params={
            "categories": cat_id, "per_page": 100, "page": pagina,
            "_fields": "title,link,content,date"})
        if r.status_code == 400:      # passou da última página
            break
        r.raise_for_status()
        lote = r.json()
        if not lote:
            break
        for p in lote:
            posts.append({
                "titulo": BeautifulSoup(p["title"]["rendered"], "html.parser").get_text(strip=True),
                "link": p["link"], "content": p["content"]["rendered"],
                "date": p.get("date", "")})
        # Se o servidor informa o total de páginas, respeita; se o cabeçalho
        # foi removido (plugins de segurança fazem isso), segue até 400/vazio.
        total_hdr = r.headers.get("X-WP-TotalPages")
        if total_hdr:
            try:
                if pagina >= int(total_hdr):
                    break
            except ValueError:
                pass
        pagina += 1
        time.sleep(PAUSA)
    return posts


def coletar_via_api(sessao, base, slugs):
    try:
        res = []
        for slug in slugs:
            cid = descobrir_categoria_id(sessao, base, slug)
            if not cid:
                print(f"  · categoria '{slug}' não encontrada na API.")
                continue
            posts = coletar_posts_api(sessao, base, cid)
            print(f"  · '{slug}': {len(posts)} post(s) via API.")
            for p in posts:
                data_pub = ""
                if p["date"]:
                    try:
                        data_pub = datetime.fromisoformat(p["date"]).strftime("%d/%m/%Y")
                    except Exception:
                        pass
                res.append({"titulo": p["titulo"], "link": p["link"],
                            "data_pub": data_pub,
                            "anexos": extrair_anexos(p["content"], p["link"])})
        return res or None
    except Exception as e:
        print(f"  ! API REST indisponível ({e}). Fallback HTML.")
        return None


def raiz_categoria(url_listagem):
    """Canonicaliza a URL de listagem removendo /page/N/ do fim.
    Assim, se o usuário passar .../licitacoes/page/3/, varremos DESDE a
    página 1 — senão as páginas não linkadas a partir da 3 ficariam de fora."""
    u = re.sub(r"/page/\d+/?$", "/", url_listagem.rstrip("/") + "/")
    return u if u.endswith("/") else u + "/"


def filtra_posts_da_pagina(soup, url, dominio):
    posts = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"].split("#")[0].strip())
        titulo = a.get_text(strip=True)
        pp = urlparse(href)
        if pp.netloc != dominio:
            continue
        seg = [s for s in pp.path.split("/") if s]
        if len(seg) != 1 or seg[0] in (
            "c","author","tag","category","wp-content","wp-json",
            "admin","webmail","mapa-do-site","o-municipio","o-governo",
            "lgpd","covid-19"):
            continue
        if titulo and MODALIDADES_RE.search(titulo):
            posts[href] = titulo
    return posts


def coletar_posts_html(sessao, url_listagem):
    """Varre a listagem página a página SEQUENCIALMENTE (/, /page/2/, /page/3/,
    ...) até receber 404 ou uma página sem novos posts. Não depende dos links
    de paginação visíveis (que nem sempre mostram todas as páginas)."""
    raiz = raiz_categoria(url_listagem)
    dominio = urlparse(raiz).netloc
    posts = {}
    n = 1
    while n <= MAX_PAGINAS:
        url = raiz if n == 1 else f"{raiz}page/{n}/"
        try:
            r = sessao.get(url, timeout=TIMEOUT)
            if r.status_code == 404:
                break
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"  ! Erro ao listar {url}: {e}")
            break
        novos = filtra_posts_da_pagina(soup, url, dominio)
        inedito = {k: v for k, v in novos.items() if k not in posts}
        if n > 1 and not inedito:
            break            # página repetida/vazia => acabou
        posts.update(inedito)
        n += 1
        time.sleep(PAUSA)
    return list(posts.items())


RE_META_PUB = re.compile(
    r'property=["\']article:published_time["\']\s+content=["\'](\d{4})-(\d{2})-(\d{2})',
    re.IGNORECASE)
RE_TIME_TAG = re.compile(
    r'<time[^>]+datetime=["\'](\d{4})-(\d{2})-(\d{2})', re.IGNORECASE)


def data_pub_do_html(html):
    """Data de publicação do post extraída das metatags do WordPress
    (article:published_time) ou da tag <time>. Formato dd/mm/aaaa ou ''. """
    for rx in (RE_META_PUB, RE_TIME_TAG):
        m = rx.search(html)
        if m:
            y, mth, d = int(m[1]), int(m[2]), int(m[3])
            if data_valida(d, mth, y):
                return f"{d:02d}/{mth:02d}/{y}"
    return ""


def coletar_via_html(sessao, listagens):
    res = []
    for url_listagem in listagens:
        print(f"  · raspando {raiz_categoria(url_listagem)} (varre /page/N/)")
        posts = coletar_posts_html(sessao, url_listagem)
        print(f"    {len(posts)} licitação(ões).")
        for url_post, titulo in posts:
            time.sleep(PAUSA)
            try:
                r = sessao.get(url_post, timeout=TIMEOUT)
                r.raise_for_status()
                r.encoding = r.apparent_encoding or "utf-8"
                anexos = extrair_anexos(r.text, url_post)
                data_pub = data_pub_do_html(r.text)
            except Exception as e:
                print(f"    ! Erro em {url_post}: {e}")
                anexos, data_pub = [], ""
            res.append({"titulo": titulo, "link": url_post,
                        "data_pub": data_pub, "anexos": anexos})
    return res


# ============================================================================
# PARTE 4 — OCR + LEITURA DE TEXTO
# ============================================================================
_OCR_BACKEND = None


def detectar_backend_ocr():
    global _OCR_BACKEND
    if _OCR_BACKEND is not None:
        return _OCR_BACKEND
    if shutil.which("ocrmypdf"):
        _OCR_BACKEND = "ocrmypdf"
    else:
        try:
            import pytesseract, pdf2image  # noqa
            _OCR_BACKEND = "pytesseract"
        except Exception:
            _OCR_BACKEND = "nenhum"
    return _OCR_BACKEND


def ler_texto_pdf(caminho):
    try:
        import pdfplumber
        with pdfplumber.open(caminho) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        return ""


def caminho_sidecar(caminho_pdf):
    return caminho_pdf[:-4] + ".ocr.txt"


def ocr_para_texto(caminho, idioma="por", motor="auto"):
    """Roda OCR e devolve o texto. O texto fica cacheado no .ocr.txt, então
    execuções seguintes (ex.: --so-planilha) não refazem o OCR.

    motor:
      "tesseract" -> só Tesseract (ocrmypdf/pytesseract)
      "easyocr"   -> só EasyOCR (se instalado; senão cai no Tesseract)
      "auto"      -> Tesseract primeiro; se o resultado vier ruim e o
                     EasyOCR estiver instalado, refaz e usa o MELHOR."""
    txt_path = caminho_sidecar(caminho)

    if motor == "easyocr":
        if easyocr_disponivel():
            texto = _ocr_easy(caminho, idioma)
            _grava_sidecar(txt_path, texto)
            return texto
        print("        (EasyOCR não instalado — usando Tesseract)")
        motor = "tesseract"

    texto = _ocr_tesseract(caminho, idioma)

    if motor == "auto" and texto_ocr_ruim(texto) and easyocr_disponivel():
        print(f"        (Tesseract fraco — tentando EasyOCR) "
              f"{os.path.basename(caminho)}")
        texto_easy = _ocr_easy(caminho, idioma)
        if qualidade_texto(texto_easy) > qualidade_texto(texto):
            texto = texto_easy

    _grava_sidecar(txt_path, texto)
    return texto


def _grava_sidecar(txt_path, texto):
    if not texto:
        return
    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(texto)
    except Exception:
        pass


def _ocr_tesseract(caminho, idioma="por"):
    """OCR via Tesseract (ocrmypdf preferido; pytesseract como alternativa)."""
    backend = detectar_backend_ocr()
    if backend == "ocrmypdf":
        try:
            saida = caminho[:-4] + ".ocr.pdf"
            txt_path_s = caminho_sidecar(caminho)
            # --deskew endireita páginas escaneadas tortas; --rotate-pages
            # corrige páginas giradas/cabeça pra baixo; --oversample 300
            # reamostra digitalizações de baixa resolução para 300 DPI —
            # os três juntos melhoram bastante a leitura de scans municipais.
            subprocess.run(
                ["ocrmypdf", "-l", idioma, "--force-ocr",
                 "--deskew", "--rotate-pages", "--oversample", "300",
                 "--optimize", "1", "--sidecar", txt_path_s, caminho, saida],
                capture_output=True, text=True, timeout=900)
            if os.path.exists(txt_path_s):
                with open(txt_path_s, encoding="utf-8", errors="ignore") as f:
                    return f.read()
        except Exception as ee:
            print(f"        (ocrmypdf falhou: {ee})")
        return ""
    if backend == "pytesseract":
        try:
            import pytesseract
            from pdf2image import convert_from_path
            # dpi=300 e motor LSTM (--oem 1): melhor precisão em scans
            return "\n".join(
                pytesseract.image_to_string(img, lang=idioma, config="--oem 1")
                for img in convert_from_path(caminho, dpi=300))
        except Exception as ee:
            print(f"        (pytesseract falhou: {ee})")
        return ""
    return ""


# ----------------------------------------------------------------------------
# EasyOCR (opcional) — deep learning; melhor em scans ruins, lento sem GPU
# ----------------------------------------------------------------------------
_EASYOCR_READER = None      # o Reader é caro de criar; inicializa uma vez
_EASYOCR_OK = None

IDIOMA_EASYOCR = {"por": "pt", "eng": "en", "spa": "es"}


def easyocr_disponivel():
    """True se easyocr + dependências estão instalados (checagem preguiçosa)."""
    global _EASYOCR_OK
    if _EASYOCR_OK is not None:
        return _EASYOCR_OK
    try:
        import easyocr, numpy, pdf2image  # noqa
        _EASYOCR_OK = True
    except Exception:
        _EASYOCR_OK = False
    return _EASYOCR_OK


def _easy_reader(idioma="por"):
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        import easyocr
        lang = IDIOMA_EASYOCR.get(idioma, "pt")
        # gpu=True usa CUDA se existir; sem GPU o easyocr cai em CPU sozinho
        _EASYOCR_READER = easyocr.Reader([lang], gpu=True, verbose=False)
    return _EASYOCR_READER


def _ocr_easy(caminho, idioma="por"):
    """OCR via EasyOCR, página a página."""
    try:
        import numpy as np
        from pdf2image import convert_from_path
        reader = _easy_reader(idioma)
        partes = []
        for img in convert_from_path(caminho, dpi=300):
            linhas = reader.readtext(np.array(img), detail=0, paragraph=True)
            partes.append("\n".join(linhas))
        return "\n".join(partes)
    except Exception as ee:
        print(f"        (easyocr falhou: {ee})")
        return ""


# ----------------------------------------------------------------------------
# Heurística de qualidade do texto reconhecido
# ----------------------------------------------------------------------------
RE_CHAR_BOM = re.compile(r"[a-zA-Z0-9áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ ,.;:()\-/\n]")


def qualidade_texto(texto):
    """Pontuação simples de legibilidade: comprimento útil x proporção de
    caracteres reconhecíveis. Serve para comparar saídas de dois motores."""
    if not texto:
        return 0.0
    t = texto.strip()
    if not t:
        return 0.0
    bons = len(RE_CHAR_BOM.findall(t))
    proporcao = bons / len(t)
    return len(t) * (proporcao ** 2)


def texto_ocr_ruim(texto, min_chars=200, min_proporcao=0.75):
    """True quando o resultado do OCR parece fraco: muito curto ou com
    proporção alta de caracteres ilegíveis (lixo de reconhecimento)."""
    if not texto or len(texto.strip()) < min_chars:
        return True
    t = texto.strip()
    return (len(RE_CHAR_BOM.findall(t)) / len(t)) < min_proporcao


def ocr_instalado():
    """True se ALGUM motor de OCR está disponível (Tesseract ou EasyOCR)."""
    return detectar_backend_ocr() != "nenhum" or easyocr_disponivel()


def obter_texto(caminho, usar_ocr, idioma="por", min_chars=40, motor="auto"):
    """Retorna (texto, origem in {'nativo','ocr','ocr-cache','vazio'})."""
    if os.path.splitext(caminho)[1].lower() not in EXT_TEXTAVEIS:
        return "", "vazio"
    texto = ler_texto_pdf(caminho)
    if len(texto.strip()) >= min_chars:
        return texto, "nativo"
    # cache de OCR de rodadas anteriores
    txt_path = caminho_sidecar(caminho)
    if os.path.exists(txt_path):
        try:
            with open(txt_path, encoding="utf-8", errors="ignore") as f:
                cache = f.read()
            if len(cache.strip()) >= min_chars:
                return cache, "ocr-cache"
        except Exception:
            pass
    if usar_ocr and ocr_instalado():
        texto_ocr = ocr_para_texto(caminho, idioma, motor)
        if len(texto_ocr.strip()) >= min_chars:
            return texto_ocr, "ocr"
    return texto, ("nativo" if texto.strip() else "vazio")


# ============================================================================
# PARTE 5 — DOWNLOAD
# ============================================================================
def baixar_arquivo(sessao, url, destino):
    for t in range(1, TENTATIVAS + 1):
        try:
            with sessao.get(url, stream=True, timeout=TIMEOUT) as r:
                r.raise_for_status()
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                tmp = destino + ".part"
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(65536):
                        if chunk:
                            f.write(chunk)
                os.replace(tmp, destino)
            return True
        except Exception as e:
            print(f"        tentativa {t}/{TENTATIVAS}: {e}")
            time.sleep(1.5 * t)
    return False


# ============================================================================
# PARTE 6 — EXTRAÇÃO DE VALORES POR LICITAÇÃO
# ============================================================================
def doc_serve_para(nome_arq, tipo):
    n = normaliza(nome_arq)
    alvos = DOCS_ESTIMADO if tipo == "estimado" else DOCS_HOMOLOGADO
    return any(a in n for a in alvos)


# Valor mínimo plausível para o TOTAL de uma contratação pública (valores
# menores encontrados perto de rótulos costumam ser multas, taxas ou itens).
VALOR_MINIMO_PLAUSIVEL = 100.00

# Tolerância da regra "homologado <= estimado": nos certames concorrenciais
# a disputa reduz o preço; homologado muito acima do estimado indica erro de
# extração (Lei 10.520 e Lei 14.133 desclassificam proposta acima do teto).
TOLERANCIA_HOMOLOGADO = 1.10


def _candidatos_do_tipo(arquivos_texto, tipo):
    """Todos os candidatos de valor do tipo, com metadados de confiança."""
    candidatos = []
    for nome, texto in arquivos_texto:
        if not texto:
            continue
        prioridade = 1 if doc_serve_para(nome, tipo) else 0
        achado = extrair_valor(texto, tipo)
        if not achado:
            continue
        for c in achado["candidatos"]:
            if c["valor"] < VALOR_MINIMO_PLAUSIVEL:
                continue
            candidatos.append({
                "valor": c["valor"], "rotulo": c["rotulo"], "doc": nome,
                "trecho": c.get("trecho", ""),
                "prioridade": prioridade,
                "reforco": any(r in c["rotulo"] for r in REFORCO_TOTAL)
                           or achado["reforco"] and c is achado["candidatos"][0],
                # Confirmação por extenso: "R$ X (… reais)" logo após o valor
                # é a redação padrão dos atos oficiais — evidência forte de
                # que o número capturado é mesmo um valor da contratação.
                "extenso": "reais" in normaliza(c.get("trecho", "")),
            })
    return candidatos


def _confianca(cand, contagem_docs):
    """Pontuação de confiança de um candidato de valor:
      +2 se o MESMO valor aparece em 2+ documentos distintos (validação cruzada)
      +1 se veio do documento correto para o tipo
      +1 se o rótulo indica total/global
      +1 se o valor vem seguido do extenso '(… reais)' — redação oficial
    A pontuação ORDENA os candidatos (o melhor é preenchido); não é veto."""
    pts = 0
    if contagem_docs.get(cand["valor"], 0) >= 2:
        pts += 2
    if cand["prioridade"] == 1:
        pts += 1
    if cand["reforco"]:
        pts += 1
    if cand.get("extenso"):
        pts += 1
    return pts


def _pontuar(candidatos):
    """Retorna lista [(pts, cand)] ordenada do melhor para o pior."""
    if not candidatos:
        return []
    docs_por_valor = {}
    for c in candidatos:
        docs_por_valor.setdefault(c["valor"], set()).add(c["doc"])
    contagem = {v: len(d) for v, d in docs_por_valor.items()}
    pontuados = [(_confianca(c, contagem), c) for c in candidatos]
    pontuados.sort(key=lambda x: (x[0], x[1]["prioridade"], x[1]["reforco"],
                                  x[1]["valor"]), reverse=True)
    return pontuados


def _melhor(candidatos):
    """Melhor candidato disponível (sempre preenche se houver algum)."""
    pontuados = _pontuar(candidatos)
    return pontuados[0][1] if pontuados else None


def _pts_de(cand, candidatos):
    for pts, c in _pontuar(candidatos):
        if c is cand:
            return pts
    return 0


def _resumo_candidatos(candidatos, limite=6):
    """String compacta 'doc: R$ valor (pts)' dos melhores candidatos."""
    partes = []
    for pts, c in _pontuar(candidatos)[:limite]:
        partes.append(f"{c['doc']}: {c['valor']:,.2f} ({pts}pt)".replace(
            ",", "@").replace(".", ",").replace("@", "."))
    return " | ".join(partes)


def _item_auditoria(campo, escolhido, candidatos, motivo=""):
    """Monta um registro de auditoria para um campo de valor."""
    if escolhido is None:
        return {"campo": campo, "valor": None, "doc": "—",
                "rotulo": motivo or "nenhum candidato encontrado",
                "trecho": "", "pts": "",
                "outros": _resumo_candidatos(candidatos)}
    return {"campo": campo, "valor": escolhido["valor"],
            "doc": escolhido["doc"], "rotulo": escolhido["rotulo"],
            "trecho": escolhido.get("trecho", ""),
            "pts": _pts_de(escolhido, candidatos),
            "outros": _resumo_candidatos(candidatos)}


def extrair_valores_da_licitacao(arquivos_texto, modalidade="",
                                 data_pub=None, ano=""):
    """Extrai valores e data de abertura. Preenche SEMPRE o melhor candidato
    disponível; os critérios de coerência da legislação ordenam a escolha e
    corrigem pares incoerentes (não vetam o preenchimento). Devolve também a
    auditoria de cada campo (documento, rótulo, trecho, pontos)."""
    res = {"valor_estimado": None, "valor_homologado": None,
           "data_abertura": None, "auditoria": []}

    cand_est = _candidatos_do_tipo(arquivos_texto, "estimado")
    cand_hom = _candidatos_do_tipo(arquivos_texto, "homologado")
    esc_est = _melhor(cand_est)
    esc_hom = _melhor(cand_hom)
    motivo_est = motivo_hom = ""

    # --- Coerência legal: homologado não deve superar o estimado ---
    if esc_est and esc_hom and esc_hom["valor"] > esc_est["valor"] * TOLERANCIA_HOMOLOGADO:
        coerentes = [c for c in cand_hom
                     if c["valor"] <= esc_est["valor"] * TOLERANCIA_HOMOLOGADO]
        alt = _melhor(coerentes)
        if alt:
            esc_hom = alt
            motivo_hom = "recombinado p/ coerência (homologado <= estimado)"
        else:
            coerentes_e = [c for c in cand_est
                           if esc_hom["valor"] <= c["valor"] * TOLERANCIA_HOMOLOGADO]
            alt_e = _melhor(coerentes_e)
            if alt_e:
                esc_est = alt_e
                motivo_est = "recombinado p/ coerência (homologado <= estimado)"
            else:
                if _pts_de(esc_hom, cand_hom) > _pts_de(esc_est, cand_est):
                    esc_est = None
                    motivo_est = "descartado: incoerente com homologado (sem alternativa)"
                else:
                    esc_hom = None
                    motivo_hom = "descartado: incoerente com estimado (sem alternativa)"

    res["valor_estimado"] = esc_est["valor"] if esc_est else None
    res["valor_homologado"] = esc_hom["valor"] if esc_hom else None

    it_e = _item_auditoria("Valor Estimado", esc_est, cand_est, motivo_est)
    it_h = _item_auditoria("Valor Homologado", esc_hom, cand_hom, motivo_hom)
    if motivo_est and esc_est:
        it_e["rotulo"] += f"  [{motivo_est}]"
    if motivo_hom and esc_hom:
        it_h["rotulo"] += f"  [{motivo_hom}]"
    res["auditoria"].append(it_e)
    res["auditoria"].append(it_h)

    # --- Data de abertura ---
    # Contratação direta (dispensa/inexigibilidade) NÃO tem sessão de
    # abertura de propostas: o campo fica vazio por definição legal.
    if eh_contratacao_direta(modalidade):
        res["auditoria"].append({
            "campo": "Data de Abertura", "valor": None, "doc": "—",
            "rotulo": "contratação direta: não há sessão de abertura (vazio correto)",
            "trecho": "", "pts": "", "outros": ""})
    else:
        d, doc_d, metodo = _achar_data_abertura(arquivos_texto, data_pub, ano)
        res["data_abertura"] = d
        if d:
            res["auditoria"].append({
                "campo": "Data de Abertura",
                "valor": f"{d[0]:02d}/{d[1]:02d}/{d[2]}",
                "doc": doc_d, "rotulo": metodo, "trecho": "", "pts": "",
                "outros": ""})
        else:
            res["auditoria"].append({
                "campo": "Data de Abertura", "valor": None, "doc": "—",
                "rotulo": "nenhuma data coerente encontrada",
                "trecho": "", "pts": "", "outros": ""})
    return res


def _achar_data_abertura(arquivos_texto, data_pub, ano):
    """Estratégia em camadas para a data de abertura. Retorna
    (data, documento, método):
      1) rótulo de abertura no AVISO/EDITAL;
      2) rótulo de abertura em qualquer documento;
      3) fallback: data com HORÁRIO adjacente coerente (aviso/edital primeiro)
         — 'dd/mm/aaaa às 09:00' é a assinatura da data de sessão;
      4) fallback final: primeira data coerente de qualquer documento."""
    docs_prior = [(n, t) for n, t in arquivos_texto
                  if t and any(k in normaliza(n) for k in ("aviso", "edital"))]
    docs_resto = [(n, t) for n, t in arquivos_texto
                  if t and (n, t) not in docs_prior]

    # 1 e 2: por rótulo
    for grupo, tag in ((docs_prior, "rótulo no aviso/edital"),
                       (docs_resto, "rótulo no documento")):
        for nome, texto in grupo:
            d = extrair_data_abertura(texto)
            if d and _data_abertura_coerente(d, data_pub, ano):
                return d, nome, tag
    # 3: data com horário adjacente
    for grupo in (docs_prior, docs_resto):
        for nome, texto in grupo:
            for d, tem_hora in datas_do_documento(texto):
                if tem_hora and _data_abertura_coerente(d, data_pub, ano):
                    return d, nome, "data seguida de horário (fallback)"
    # 4: primeira data coerente
    for grupo in (docs_prior, docs_resto):
        for nome, texto in grupo:
            for d, _h in datas_do_documento(texto):
                if _data_abertura_coerente(d, data_pub, ano):
                    return d, nome, "primeira data coerente (fallback)"
    return None, "", ""


def _data_abertura_coerente(d, data_pub, ano):
    """Sanidade da data de abertura:
      - nunca ANTERIOR à publicação (o edital é publicado antes da sessão);
      - no máximo ~1 ano após a publicação;
      - no ano do certame ou no seguinte (processos publicados em dezembro
        podem abrir em janeiro)."""
    dia, mes, a = d
    try:
        dt = datetime(a, mes, dia)
    except ValueError:
        return False
    if isinstance(data_pub, datetime):
        if dt < data_pub:
            return False
        if (dt - data_pub).days > 400:
            return False
    if ano:
        try:
            ano_i = int(ano)
            if not (ano_i <= a <= ano_i + 1):
                return False
        except ValueError:
            pass
    return True


# ============================================================================
# PARTE 7 — PLANILHA
# ============================================================================
def ultima_linha_com_dados(ws, colunas_idx):
    """Última linha que tem conteúdo real nas colunas mapeadas. (max_row do
    openpyxl conta formatação fantasma — no modelo, vai até a linha 992.)"""
    ultima = 1
    for r in range(2, ws.max_row + 1):
        if any(ws.cell(row=r, column=c).value not in (None, "")
               for c in colunas_idx):
            ultima = r
    return ultima


def preencher_planilha(linhas, auditoria, modelo, saida):
    import openpyxl
    from openpyxl.styles import Font
    from copy import copy

    if modelo and os.path.exists(modelo):
        wb = openpyxl.load_workbook(modelo)
        ws = wb.active
        header = {}
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=1, column=c).value
            if v:
                header[str(v).strip()] = c
        ref = ws.cell(row=1, column=1).font
        estilo = Font(name=ref.name or "Arial", size=ref.size or 10, bold=False)
        linha_ini = ultima_linha_com_dados(ws, header.values()) + 1
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Licitações"
        for i, nome in enumerate(COLUNAS, 1):
            ws.cell(row=1, column=i, value=nome).font = Font(
                name="Arial", size=10, bold=True)
        header = {nome: i for i, nome in enumerate(COLUNAS, 1)}
        estilo = Font(name="Arial", size=10, bold=False)
        linha_ini = 2

    fmt = {"Data de Publicação": "dd/mm/yyyy", "Data de Abertura": "dd/mm/yyyy",
           "Valor Estimado": "#,##0.00", "Valor Homologado": "#,##0.00"}

    for r_off, dados in enumerate(linhas):
        r = linha_ini + r_off
        for nome_col, valor in dados.items():
            if nome_col not in header:
                continue
            cell = ws.cell(row=r, column=header[nome_col], value=valor)
            cell.font = copy(estilo)
            if nome_col in fmt:
                cell.number_format = fmt[nome_col]

    # ----- Aba Auditoria: origem de cada dado extraído -----
    if "Auditoria" in wb.sheetnames:
        del wb["Auditoria"]
    aud = wb.create_sheet("Auditoria")
    cab = ["Licitação", "Campo", "Valor preenchido", "Documento de origem",
           "Rótulo / método / motivo", "Trecho do documento",
           "Confiança (pts)", "Outros candidatos (doc: valor (pts))"]
    for i, h in enumerate(cab, 1):
        aud.cell(row=1, column=i, value=h).font = Font(
            name="Arial", size=10, bold=True)
    ra = 2
    for item in auditoria:
        aud.cell(row=ra, column=1, value=item["licitacao"])
        aud.cell(row=ra, column=2, value=item["campo"])
        cel_v = aud.cell(row=ra, column=3,
                         value=item["valor"] if item["valor"] is not None
                         else "(em branco)")
        if isinstance(item["valor"], (int, float)):
            cel_v.number_format = "#,##0.00"
        aud.cell(row=ra, column=4, value=item["doc"])
        aud.cell(row=ra, column=5, value=item["rotulo"])
        aud.cell(row=ra, column=6, value=item["trecho"])
        aud.cell(row=ra, column=7, value=item["pts"])
        aud.cell(row=ra, column=8, value=item["outros"])
        for c in range(1, 9):
            aud.cell(row=ra, column=c).font = Font(name="Arial", size=10)
        ra += 1
    for col, w in {"A": 42, "B": 17, "C": 16, "D": 34, "E": 42,
                   "F": 60, "G": 13, "H": 55}.items():
        aud.column_dimensions[col].width = w

    wb.save(saida)


# ============================================================================
# MAIN
# ============================================================================
def main():
    ap = argparse.ArgumentParser(
        description="Baixa licitações de portais CR2 e preenche planilha.")
    ap.add_argument("--listagem", default=LISTAGEM_PADRAO,
                    help=f"URL da listagem (padrão: {LISTAGEM_PADRAO})")
    ap.add_argument("--saida", default=SAIDA_PADRAO, help="Pasta dos downloads.")
    ap.add_argument("--planilha-modelo", default="Front.xlsx",
                    help="Planilha-modelo com os cabeçalhos (padrão: Front.xlsx).")
    ap.add_argument("--planilha-saida", default="",
                    help="Caminho da planilha gerada. Vazio = "
                         f"{PLANILHA_SAIDA} DENTRO da pasta de downloads (--saida).")
    ap.add_argument("--incluir-subcategorias", action="store_true")
    ap.add_argument("--so-html", action="store_true", help="Ignora a API REST.")
    ap.add_argument("--so-planilha", action="store_true",
                    help="Não rebaixa anexos; usa os já salvos em --saida.")
    ap.add_argument("--sem-extracao", action="store_true",
                    help="Só baixa; não lê documentos nem preenche planilha.")
    ap.add_argument("--ocr", action="store_true",
                    help="Usa OCR nos PDFs sem camada de texto.")
    ap.add_argument("--idioma-ocr", default="por")
    ap.add_argument("--motor-ocr", default="", choices=["", "auto", "tesseract", "easyocr"],
                    help="Motor de OCR: auto (Tesseract + EasyOCR de reserva), "
                         "tesseract ou easyocr. Vazio usa MOTOR_OCR do topo do script.")
    ap.add_argument("--anos", default="",
                    help="Anos a extrair, separados por vírgula (ex.: 2023,2024). "
                         "Vazio usa ANOS_FILTRO do topo do script; ambos vazios = todos.")
    ap.add_argument("--sem-renomear", action="store_true",
                    help="Não renomeia anexos pelo título interno do documento.")
    ap.add_argument("--ignorar-ssl", action="store_true",
                    help="Ignora erros de certificado SSL (portais com cert quebrado).")
    args = ap.parse_args()

    p = urlparse(args.listagem)
    base = f"{p.scheme}://{p.netloc}"

    # Filtro de anos efetivo: linha de comando > configuração do topo
    anos_filtro = ([a.strip() for a in args.anos.split(",") if a.strip()]
                   if args.anos.strip() else list(ANOS_FILTRO))
    renomear = RENOMEAR_POR_TITULO and not args.sem_renomear

    os.makedirs(args.saida, exist_ok=True)

    # Planilha: por padrão, DENTRO da pasta de downloads (junto dos arquivos)
    if not args.planilha_saida.strip():
        args.planilha_saida = os.path.join(args.saida, PLANILHA_SAIDA)
    sessao = requests.Session()
    sessao.headers.update(HEADERS)
    if args.ignorar_ssl:
        sessao.verify = False
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    if args.ocr:
        motor_ocr = args.motor_ocr or MOTOR_OCR
        tess = detectar_backend_ocr()
        easy = easyocr_disponivel()
        print(f"  · OCR: motor '{motor_ocr}' | Tesseract: "
              f"{tess if tess != 'nenhum' else 'NÃO instalado'} | EasyOCR: "
              f"{'instalado' if easy else 'não instalado'}")
        if not ocr_instalado():
            print("    ! nenhum motor de OCR disponível — OCR será ignorado")
    else:
        motor_ocr = args.motor_ocr or MOTOR_OCR

    print("=" * 66)
    print(f"Entidade : {p.netloc}")
    print(f"Listagem : {raiz_categoria(args.listagem)}")
    print(f"Downloads: {args.saida}")
    print(f"Planilha : {args.planilha_saida}  (modelo: {args.planilha_modelo})")
    print(f"Anos     : {', '.join(anos_filtro) if anos_filtro else 'todos'}")
    print(f"Renomear : {'pelo título interno dos documentos' if renomear else 'não'}")
    print("=" * 66 + "\n")

    licitacoes = None
    if not args.so_html:
        print("► Coletando via API REST...")
        slugs = ["licitacoes"] + (SUBCATEGORIAS if args.incluir_subcategorias else [])
        licitacoes = coletar_via_api(sessao, base, slugs)
    if licitacoes is None:
        print("► Coletando via HTML (varredura de páginas)...")
        listagens = [args.listagem] + (
            [f"{base}/c/licitacoes/{s}/" for s in SUBCATEGORIAS]
            if args.incluir_subcategorias else [])
        licitacoes = coletar_via_html(sessao, listagens)
    print(f"\n► {len(licitacoes)} licitação(ões).\n")

    linhas_planilha, auditoria_geral = [], []

    puladas_ano = 0
    cancelado = False
    try:
        for lic in licitacoes:
            _abortar_se_cancelado()
            titulo = lic["titulo"]

            modalidade_bruta, numero = split_modalidade_numero(titulo)
            modalidade = modalidade_padrao(titulo)      # nome padronizado
            ano = extrai_ano(numero)
            objeto = extrai_objeto(titulo)

            # --- FILTRO DE ANOS: aplicado ANTES do download (economiza banda).
            # Licitação sem ano identificável é mantida, com aviso, para não
            # perder registro por falha de parsing do número.
            if anos_filtro:
                if ano and ano not in anos_filtro:
                    puladas_ano += 1
                    continue
                if not ano:
                    print(f"  ! sem ano identificável (mantida): {titulo[:60]}")

            pasta = os.path.join(args.saida, nome_pasta(titulo))
            os.makedirs(pasta, exist_ok=True)
            print(f"  ► {titulo[:70]}")

            arquivos_locais = []
            nomes_nesta_execucao = set()
            for texto_link, url_arq in lic["anexos"]:
                _abortar_se_cancelado()
                arq = nome_arquivo(texto_link, url_arq)
                # Anexos DIFERENTES com a mesma descrição (na mesma licitação):
                # numeramos ANTES de checar existência, para que o 2º não seja
                # confundido com um arquivo já baixado e pulado indevidamente.
                if arq in nomes_nesta_execucao:
                    i = 2
                    while variante_numerada(arq, i) in nomes_nesta_execucao:
                        i += 1
                    arq = variante_numerada(arq, i)
                nomes_nesta_execucao.add(arq)

                destino = os.path.join(pasta, arq)

                # MIGRAÇÃO: arquivo baixado por rodada antiga (nome sem
                # capitalização) é renomeado para o padrão novo — evita
                # duplicar o download.
                if not os.path.exists(destino):
                    legado = os.path.join(
                        pasta, nome_arquivo_bruto(texto_link, url_arq))
                    if legado != destino and os.path.exists(legado):
                        try:
                            os.replace(legado, destino)
                            sc = caminho_sidecar(legado)
                            if os.path.exists(sc):
                                os.replace(sc, caminho_sidecar(destino))
                            print(f"    [REN ] {os.path.basename(legado)} -> {arq}")
                        except OSError:
                            destino = legado          # falhou: usa o antigo

                if os.path.exists(destino):          # já veio de rodada anterior
                    arquivos_locais.append(destino)
                    continue
                if args.so_planilha:
                    continue
                print(f"    [DOWN] {arq}")
                if baixar_arquivo(sessao, url_arq, destino):
                    arquivos_locais.append(destino)
                time.sleep(PAUSA)

            if args.so_planilha:
                for f in os.listdir(pasta):
                    fp = os.path.join(pasta, f)
                    if (os.path.isfile(fp) and fp not in arquivos_locais
                            and not eh_artefato_ocr(f)
                            and os.path.splitext(f)[1].lower() in EXT_DOCS):
                        arquivos_locais.append(fp)

            # Converte a data de publicação ANTES da extração, para que sirva
            # de referência na validação da data de abertura.
            data_pub = lic["data_pub"]
            if isinstance(data_pub, str) and data_pub:
                try:
                    data_pub = datetime.strptime(data_pub, "%d/%m/%Y")
                except Exception:
                    pass

            linha = {"Modalidade": modalidade, "Número": numero, "Ano": ano,
                     "Objeto": objeto or titulo, "Data de Publicação": data_pub,
                     "Data de Abertura": "", "Valor Estimado": "",
                     "Situação da Licitação": "", "Valor Homologado": ""}

            if not args.sem_extracao:
                arquivos_texto = []
                for fp in arquivos_locais:
                    _abortar_se_cancelado()
                    texto, origem = obter_texto(fp, args.ocr, args.idioma_ocr,
                                                motor=motor_ocr)
                    if origem == "ocr":
                        print(f"        (OCR) {os.path.basename(fp)}")

                    # --- RENOMEAÇÃO PELO TÍTULO INTERNO: nome genérico + título
                    # reconhecido dentro do documento (texto nativo ou OCR).
                    nome_atual = os.path.basename(fp)
                    raiz_atual, ext = os.path.splitext(nome_atual)
                    if renomear and texto and nome_eh_generico(raiz_atual):
                        tit = titulo_interno(texto)
                        if tit:
                            novo = capitaliza_nome_arquivo(
                                limpa_nome(tit) + ext.lower())
                            novo_fp = caminho_unico_arquivo(pasta, novo, fp)
                            if novo_fp != fp:
                                try:
                                    os.replace(fp, novo_fp)
                                    # o cache de OCR acompanha o arquivo
                                    sc_velho = caminho_sidecar(fp)
                                    if os.path.exists(sc_velho):
                                        os.replace(sc_velho,
                                                   caminho_sidecar(novo_fp))
                                    print(f"        [REN ] {nome_atual} -> "
                                          f"{os.path.basename(novo_fp)}")
                                    fp = novo_fp
                                except OSError as e:
                                    print(f"        (renomear falhou: {e})")

                    arquivos_texto.append((os.path.basename(fp), texto))

                vals = extrair_valores_da_licitacao(
                    arquivos_texto, modalidade=modalidade,
                    data_pub=data_pub if isinstance(data_pub, datetime) else None,
                    ano=ano)
                if vals["valor_estimado"] is not None:
                    linha["Valor Estimado"] = vals["valor_estimado"]
                if vals["valor_homologado"] is not None:
                    linha["Valor Homologado"] = vals["valor_homologado"]
                if vals["data_abertura"]:
                    d, mth, y = vals["data_abertura"]
                    linha["Data de Abertura"] = datetime(y, mth, d)   # já validada
                linha["Situação da Licitação"] = inferir_situacao(
                    titulo, [n for n, _ in arquivos_texto],
                    modalidade=modalidade)

                for item in vals["auditoria"]:
                    item["licitacao"] = titulo
                    auditoria_geral.append(item)

            linhas_planilha.append(linha)
    except Cancelado:
        cancelado = True

    if anos_filtro and puladas_ano:
        print(f"\n  · {puladas_ano} licitação(ões) fora dos anos "
              f"{', '.join(anos_filtro)} — puladas.")

    if not args.sem_extracao and linhas_planilha:
        print(f"\n► Preenchendo planilha ({len(linhas_planilha)} linhas)...")
        preencher_planilha(linhas_planilha, auditoria_geral,
                           args.planilha_modelo, args.planilha_saida)
        print(f"  ✓ {args.planilha_saida}")

    print("\n" + "=" * 66)
    print("CANCELADO." if cancelado else "Concluído.")
    print("  Veja a aba 'Auditoria': documento de origem, rótulo, trecho e")
    print("  pontuação de confiança de cada valor — e o motivo dos em branco.")
    print("=" * 66)
    if cancelado:
        raise Cancelado()


if __name__ == "__main__":
    main()
