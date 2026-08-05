#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
 BAIXADOR + EXTRATOR DE LICITAÇÕES — Portais CR2
==============================================================================

SCRIPT ÚNICO. Faz tudo:
  1) Coleta as licitações (API REST do WordPress; fallback: raspagem HTML)
  2) Baixa os anexos em pastas por licitação
  3) Lê o texto dos documentos (OCR opcional; cache em .ocr.txt)
  4) Extrai valores, datas e situação (regras + IA local Ollama opcional)
  5) Gera Licitacoes_preenchida.xlsx (intermediária) e as planilhas oficiais
     de upload: subirLicitacoes.xlsx + subirDocumentosLicitacoes.xlsx

Genérico: a entidade vem da URL de --listagem (qualquer portal CR2).

------------------------------------------------------------------------------
 REQUISITOS
------------------------------------------------------------------------------
  pip install requests beautifulsoup4 openpyxl pdfplumber

  OCR (opcional): Tesseract + Poppler (ou ocrmypdf + Ghostscript)
  IA local (opcional): Ollama com modelo llama3.2:3b (ou --modelo-ia)

------------------------------------------------------------------------------
 USO
------------------------------------------------------------------------------
  python script.py --ocr --refinar-ia
  python script.py --so-planilha --ocr --refinar-ia
  python script.py --listagem https://OUTRA.pa.gov.br/c/licitacoes/ --ocr
  python script.py --ignorar-ssl
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
# Defaults neutros — o painel / CLI deve informar listagem e pasta.
LISTAGEM_PADRAO = ""
SAIDA_PADRAO    = r"C:\Downloads\Licitacoes"
PLANILHA_SAIDA  = "Licitacoes_preenchida.xlsx"
ULTIMO_RESULTADO_UPLOAD = None  # preenchido ao final (caminhos das planilhas oficiais)
SUBCATEGORIAS   = ["licitacoes-fracassadas", "licitacoes-desertas"]
MAX_PAGINAS     = 300     # trava de segurança na varredura de /page/N/

# ----------------------------------------------------------------------------
# FILTRO DE ANOS — vazio = todos. Use --anos 2023,2024 ou o campo do painel.
# ----------------------------------------------------------------------------
ANOS_FILTRO = []

# ----------------------------------------------------------------------------
# RENOMEAÇÃO PELO TÍTULO INTERNO — quando o nome do anexo é genérico
# ("Download", "documento", "anexo1"...), o script lê o título dentro do
# PDF (via texto nativo ou OCR) e renomeia o arquivo por ele.
# ----------------------------------------------------------------------------
RENOMEAR_POR_TITULO = True

# ----------------------------------------------------------------------------
# MOTOR DE OCR — edite aqui (ou use --motor-ocr na linha de comando).
#   "auto"      = Tesseract primeiro; se fraco e EasyOCR instalado, usa o melhor
#   "tesseract" = só Tesseract (ocrmypdf/pytesseract)
#   "easyocr"   = só EasyOCR (melhor em scans ruins; mais lento sem GPU)
# ----------------------------------------------------------------------------
MOTOR_OCR = "auto"

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
# MODALIDADES — regras de reconhecimento (ordem: específica → genérica)
# Cada regra: (termos que DEVEM aparecer, nome padrão).
# ============================================================================
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
    # --- adesão / carona ---
    (["adesao"],                            "Adesão a Ata de Registro de Preço"),
    (["carona"],                            "Carona"),
    # --- contratação direta e afins ---
    (["dispensa"],                          "Dispensa de Licitação"),
    (["inexigibilidade"],                   "Inexigibilidade de Licitação"),
    (["contratacao direta"],                "Contratação Direta"),
    # --- demais modalidades (lista oficial Front) ---
    (["dialogo competitivo"],               "Diálogo Competitivo"),
    (["credenciamento"],                    "Credenciamento"),
    (["chamada publica"],                   "Chamada Pública"),
    (["chamamento publico"],                "Chamada Pública"),
    (["chamamento"],                        "Chamada Pública"),
    # Concorrência eletrônica/presencial → Concorrência (CC)
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
    "tp", "cc", "con", "rdc", "cnpj", "cpf", "me", "epp", "ltda", "eireli",
    "fme", "fms", "fmas", "fundeb", "semed", "semus", "sead", "pgm",
    "ad", "cr", "ca", "cd", "cv", "cp", "dc", "dl", "in", "ll",
    "rpcp", "rppe", "rppp",
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
_OCR_PATHS_OK = False


def _configurar_caminhos_ocr():
    """Localiza Tesseract/Poppler no Windows (INSTALAR.bat / winget)."""
    global _OCR_PATHS_OK
    if _OCR_PATHS_OK:
        return
    _OCR_PATHS_OK = True
    candidatos_tess = [
        os.environ.get("TESSERACT_CMD") or "",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        shutil.which("tesseract") or "",
    ]
    # WinGet packages
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        winget = os.path.join(local, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget):
            for nome in os.listdir(winget):
                if "Tesseract" in nome:
                    cand = os.path.join(winget, nome, "tesseract.exe")
                    if os.path.isfile(cand):
                        candidatos_tess.append(cand)
                if "Poppler" in nome:
                    for sub in ("Library\\bin", "bin"):
                        pdir = os.path.join(winget, nome, sub)
                        if os.path.isfile(os.path.join(pdir, "pdftoppm.exe")):
                            os.environ["PATH"] = pdir + os.pathsep + os.environ.get("PATH", "")
    tess = next((c for c in candidatos_tess if c and os.path.isfile(c)), None)
    if tess:
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tess
            tess_dir = os.path.dirname(tess)
            if tess_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = tess_dir + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass
    for pop in (
        r"C:\Program Files\poppler\Library\bin",
        r"C:\Program Files\poppler\bin",
    ):
        if os.path.isfile(os.path.join(pop, "pdftoppm.exe")):
            os.environ["PATH"] = pop + os.pathsep + os.environ.get("PATH", "")
            break


def detectar_backend_ocr():
    global _OCR_BACKEND
    if _OCR_BACKEND is not None:
        return _OCR_BACKEND
    _configurar_caminhos_ocr()
    if shutil.which("ocrmypdf"):
        _OCR_BACKEND = "ocrmypdf"
    else:
        try:
            import pytesseract, pdf2image  # noqa
            # Confirma que o binário existe
            try:
                pytesseract.get_tesseract_version()
                _OCR_BACKEND = "pytesseract"
            except Exception:
                _OCR_BACKEND = "nenhum"
        except Exception:
            _OCR_BACKEND = "nenhum"
    return _OCR_BACKEND


def ler_texto_pdf(caminho, max_paginas=None):
    try:
        import pdfplumber
        with pdfplumber.open(caminho) as pdf:
            pages = pdf.pages
            if max_paginas is not None and max_paginas > 0:
                pages = pages[: int(max_paginas)]
            return "\n".join((p.extract_text() or "") for p in pages)
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


def obter_texto(caminho, usar_ocr, idioma="por", min_chars=40, motor="auto",
                max_paginas=None, max_chars=None):
    """Retorna (texto, origem in {'nativo','ocr','ocr-cache','vazio'})."""
    if os.path.splitext(caminho)[1].lower() not in EXT_TEXTAVEIS:
        return "", "vazio"
    texto = ler_texto_pdf(caminho, max_paginas=max_paginas)
    if max_chars and texto and len(texto) > max_chars:
        texto = texto[:max_chars]
    if len(texto.strip()) >= min_chars:
        return texto, "nativo"
    # cache de OCR de rodadas anteriores
    txt_path = caminho_sidecar(caminho)
    if os.path.exists(txt_path):
        try:
            with open(txt_path, encoding="utf-8", errors="ignore") as f:
                cache = f.read()
            if max_chars and cache and len(cache) > max_chars:
                cache = cache[:max_chars]
            if len(cache.strip()) >= min_chars:
                return cache, "ocr-cache"
        except Exception:
            pass
    if usar_ocr and ocr_instalado():
        texto_ocr = ocr_para_texto(caminho, idioma, motor)
        if max_chars and texto_ocr and len(texto_ocr) > max_chars:
            texto_ocr = texto_ocr[:max_chars]
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
# PRIORIDADE DE DOCS + IA LOCAL (Ollama)
# ============================================================================
def _log(msg, *args):
    """Print imediato (flush) para o painel não parecer parado."""
    if args:
        msg = msg.format(*args)
    print(msg, flush=True)


def _barra(atual, total, largura=18):
    if total <= 0:
        return "[" + ("#" * largura) + "]"
    frac = max(0.0, min(1.0, float(atual) / float(total)))
    cheios = int(round(frac * largura))
    return "[" + ("#" * cheios) + ("-" * (largura - cheios)) + "]"


def _pct(atual, total):
    if total <= 0:
        return 0
    return int(100 * atual / total)


def _garantir_path_script():
    d = os.path.dirname(os.path.abspath(__file__))
    if d not in sys.path:
        sys.path.insert(0, d)
    return d


def situacao_para_front(situacao):
    """Mapeia rótulos internos (Homologada, Deserta…) para o vocabulário Front."""
    if not situacao:
        return ""
    s = str(situacao).strip()
    try:
        _garantir_path_script()
        from gestor_regras.config_front import MAPA_SITUACAO, SITUACOES
    except ImportError:
        return s
    if s in SITUACOES:
        return s
    return MAPA_SITUACAO.get(normaliza(s), s)


def numero_com_sigla_front(numero, modalidade):
    try:
        _garantir_path_script()
        from ia_local import numero_com_sigla
        return numero_com_sigla(numero or "", modalidade or "")
    except ImportError:
        return (numero or "").strip()


def _precisa_ia(linha):
    """True se falta campo que a IA pode refinar."""
    for k in ("Número", "Objeto", "Situação da Licitação",
              "Valor Estimado", "Valor Homologado"):
        v = linha.get(k)
        if v is None or str(v).strip() in ("", "Não informado"):
            return True
    return False


def _ler_docs_priorizados(arquivos_locais, usar_ocr, idioma_ocr, motor_ocr,
                          renomear, pasta):
    """
    Classifica anexos; Edital, DFD, TR e Termo de Homologação são lidos
    INTEIROS para a IA de valores. Devolve (arquivos_texto, cabecalhos, nomes).
    """
    _garantir_path_script()
    from ia_local import classificar, limites_leitura, selecionar_para_leitura
    try:
        from ia_local.classificar_docs import TIPOS_OBRIGATORIOS_VALORES
    except ImportError:
        # processo do painel pode ter módulo antigo em cache
        import importlib
        import ia_local.classificar_docs as _cd
        importlib.reload(_cd)
        TIPOS_OBRIGATORIOS_VALORES = getattr(
            _cd,
            "TIPOS_OBRIGATORIOS_VALORES",
            ("dfd", "edital", "termo_referencia", "orcamento", "homologacao", "contrato"),
        )

    metas = []
    for fp in arquivos_locais:
        nome = os.path.basename(fp)
        meta = classificar(nome, fp)
        meta["caminho"] = fp
        meta["nome"] = nome
        meta["url"] = fp  # selecionar_para_leitura usa url p/ .pdf
        metas.append(meta)

    metas.sort(key=lambda x: (x.get("prioridade", 99), x.get("nome", "").lower()))
    escolhidos = selecionar_para_leitura(metas, max_pdfs=8, so_pdf=True)
    escolhidos_paths = {os.path.abspath(e["caminho"]) for e in escolhidos}

    # Garante Edital + DFD (e demais obrigatórios de valor) mesmo se a seleção falhar
    for m in metas:
        if m.get("tipo") in TIPOS_OBRIGATORIOS_VALORES:
            escolhidos_paths.add(os.path.abspath(m["caminho"]))

    # Garante limites também nos não escolhidos (leitura curta p/ rename/situação)
    por_path = {os.path.abspath(m["caminho"]): m for m in metas}

    arquivos_texto = []
    cabecalhos = []
    novos_paths = []

    for fp in arquivos_locais:
        _abortar_se_cancelado()
        abs_fp = os.path.abspath(fp)
        meta = por_path.get(abs_fp) or classificar(os.path.basename(fp), fp)
        tipo = meta.get("tipo") or "outro"
        max_pag, max_chars = limites_leitura(tipo)
        eh_escolhido = abs_fp in escolhidos_paths
        # não-priorizados: leitura curta só p/ rename / nomes
        if not eh_escolhido:
            if max_pag is None:
                max_pag = 3
            else:
                max_pag = min(max_pag, 3)
            max_chars = min(max_chars, 3500)
        elif tipo in ("edital", "dfd", "termo_referencia", "homologacao"):
            _log(
                "        lendo {0} INTEIRO ({1})…",
                meta.get("rotulo") or tipo,
                os.path.basename(fp)[:50],
            )

        texto, origem = obter_texto(
            fp, usar_ocr, idioma_ocr, motor=motor_ocr,
            max_paginas=max_pag, max_chars=max_chars,
        )
        if origem == "ocr":
            print(f"        (OCR) {os.path.basename(fp)}")

        nome_atual = os.path.basename(fp)
        raiz_atual, ext = os.path.splitext(nome_atual)
        if renomear and texto and nome_eh_generico(raiz_atual):
            tit = titulo_interno(texto)
            if tit:
                novo = capitaliza_nome_arquivo(limpa_nome(tit) + ext.lower())
                novo_fp = caminho_unico_arquivo(pasta, novo, fp)
                if novo_fp != fp:
                    try:
                        os.replace(fp, novo_fp)
                        sc_velho = caminho_sidecar(fp)
                        if os.path.exists(sc_velho):
                            os.replace(sc_velho, caminho_sidecar(novo_fp))
                        print(f"        [REN ] {nome_atual} -> "
                              f"{os.path.basename(novo_fp)}")
                        fp = novo_fp
                        meta = classificar(os.path.basename(fp), fp)
                        meta["caminho"] = fp
                        meta["nome"] = os.path.basename(fp)
                        tipo = meta.get("tipo") or tipo
                    except OSError as e:
                        print(f"        (renomear falhou: {e})")

        nome_final = os.path.basename(fp)
        arquivos_texto.append((nome_final, texto))
        novos_paths.append(fp)

        doc = {
            "nome": nome_final,
            "tipo": tipo,
            "rotulo": meta.get("rotulo") or tipo,
            "texto": texto or "",
            "prioritario": bool(meta.get("prioritario")),
        }
        if eh_escolhido or meta.get("prioritario") or tipo in TIPOS_OBRIGATORIOS_VALORES:
            cabecalhos.append(doc)
        elif tipo in ("contrato", "aceite_adesao", "homologacao", "ata"):
            cabecalhos.append(doc)

    # ordena cabecalhos: DFD/Edital/TR/Homologação primeiro (valores)
    peso = {
        "dfd": 0, "edital": 1, "termo_referencia": 2, "homologacao": 3,
        "orcamento": 4, "etp": 5, "contrato": 6,
    }
    cabecalhos.sort(key=lambda d: (peso.get(d.get("tipo"), 40), d.get("nome", "")))

    # log dos prioritários lidos
    tipos_lidos = [
        "{0}({1}c)".format(c["tipo"], len(c.get("texto") or ""))
        for c in cabecalhos if c.get("texto")
    ]
    if tipos_lidos:
        _log("        docs p/ IA/valores: {0}", ", ".join(tipos_lidos[:8]))

    return arquivos_texto, cabecalhos, [os.path.basename(p) for p in novos_paths]


def _aplicar_valores_prioritarios(linha, cabecalhos, arquivos_texto,
                                  modalidade, data_pub, ano):
    """Valores via regras_valores (docs tipados); fallback na extração antiga."""
    _garantir_path_script()
    from ia_local import extrair_valores_dos_docs

    vals_prio = extrair_valores_dos_docs(cabecalhos)
    auditoria = []

    if vals_prio.get("valor_estimado"):
        try:
            linha["Valor Estimado"] = float(vals_prio["valor_estimado"])
        except ValueError:
            linha["Valor Estimado"] = vals_prio["valor_estimado"]
        meta = vals_prio.get("valor_estimado_meta") or {}
        auditoria.append({
            "campo": "Valor Estimado", "valor": vals_prio["valor_estimado"],
            "origem": "prioritario", "doc": meta.get("doc", ""),
            "rotulo": meta.get("rotulo", ""), "trecho": meta.get("trecho", ""),
            "pts": "", "outros": "",
        })
    if vals_prio.get("valor_homologado"):
        try:
            linha["Valor Homologado"] = float(vals_prio["valor_homologado"])
        except ValueError:
            linha["Valor Homologado"] = vals_prio["valor_homologado"]
        meta = vals_prio.get("valor_homologado_meta") or {}
        auditoria.append({
            "campo": "Valor Homologado", "valor": vals_prio["valor_homologado"],
            "origem": "prioritario", "doc": meta.get("doc", ""),
            "rotulo": meta.get("rotulo", ""), "trecho": meta.get("trecho", ""),
            "pts": "", "outros": "",
        })

    # data de abertura + fallback de valores pela lógica antiga
    vals = extrair_valores_da_licitacao(
        arquivos_texto, modalidade=modalidade,
        data_pub=data_pub if isinstance(data_pub, datetime) else None,
        ano=ano)
    if not linha.get("Valor Estimado") and vals["valor_estimado"] is not None:
        linha["Valor Estimado"] = vals["valor_estimado"]
    if not linha.get("Valor Homologado") and vals["valor_homologado"] is not None:
        linha["Valor Homologado"] = vals["valor_homologado"]
    if vals["data_abertura"]:
        d, mth, y = vals["data_abertura"]
        linha["Data de Abertura"] = datetime(y, mth, d)
    # Evita duplicar Valor Estimado/Homologado se já veio dos docs prioritários
    campos_ja = {a.get("campo") for a in auditoria}
    for item in vals.get("auditoria") or []:
        if item.get("campo") in campos_ja and item.get("campo") in (
            "Valor Estimado", "Valor Homologado",
        ):
            continue
        auditoria.append(item)
    return auditoria


def _item_aud_simples(campo, valor, doc, rotulo, trecho=""):
    return {
        "campo": campo,
        "valor": valor if valor not in ("", None) else None,
        "doc": doc or "—",
        "rotulo": rotulo or "",
        "trecho": trecho or "",
        "pts": "",
        "outros": "",
    }


def _refinar_com_ollama(titulo, linha, cabecalhos, modalidade,
                        modelo, ollama_url, pasta_cache, so_se_faltar):
    """Chama Ollama se ligado; nunca quebra o job se estiver offline."""
    import threading

    if so_se_faltar and not _precisa_ia(linha):
        _log("        etapa: IA — pulada (campos já preenchidos)")
        return None

    _garantir_path_script()
    from ia_local import ErroIA, ollama_disponivel, refinar
    from pathlib import Path

    if not ollama_disponivel(ollama_url):
        _log("        ! Ollama offline — seguindo só com regras ({0})",
             ollama_url)
        return None

    leitura_local = {
        "numero": linha.get("Número") or "",
        "numero_bruto": re.sub(r"-([A-Za-z]+)$", "", str(linha.get("Número") or "")),
        "ano": str(linha.get("Ano") or ""),
        "objeto": linha.get("Objeto") or "",
        "situacao": linha.get("Situação da Licitação") or "",
        "valor_estimado": (
            f"{linha['Valor Estimado']:.2f}"
            if isinstance(linha.get("Valor Estimado"), (int, float))
            else str(linha.get("Valor Estimado") or "")
        ),
        "valor_homologado": (
            f"{linha['Valor Homologado']:.2f}"
            if isinstance(linha.get("Valor Homologado"), (int, float))
            else str(linha.get("Valor Homologado") or "")
        ),
        "modalidade": modalidade,
    }

    stop = threading.Event()

    def _heartbeat():
        t0 = time.time()
        while not stop.wait(15):
            _log("        IA: ainda processando... {0}s (aguarde)",
                 int(time.time() - t0))

    th = threading.Thread(target=_heartbeat, daemon=True)
    try:
        _log("        etapa: IA — refinando com Ollama ({0}) — pode levar 1–3 min...",
             modelo)
        th.start()
        out = refinar(
            titulo, leitura_local, cabecalhos,
            provedor="ollama", modelo=modelo, ollama_url=ollama_url,
            pasta_cache=Path(pasta_cache) if pasta_cache else None,
            usar_cache=True,
        )
    except ErroIA as e:
        _log("        ! IA: {0}", e)
        return None
    except Exception as e:
        _log("        ! IA falhou: {0}: {1}", type(e).__name__, e)
        return None
    finally:
        stop.set()

    if out.get("cache"):
        _log("        IA: cache hit (resposta instantânea)")
    mudancas = out.get("mudancas") or []
    if mudancas:
        _log("        IA: " + "; ".join(mudancas[:4]))
    else:
        _log("        IA: sem mudanças (manteve regras)")

    # funde só o que veio validado + monta auditoria da IA
    aud_ia = []
    origem_ia = out.get("origem") or "ia_local"
    if out.get("cache"):
        origem_ia = "ia_cache"

    def _aud_ia(campo, valor, trecho="", motivo=""):
        aud_ia.append(_item_aud_simples(
            campo, valor,
            doc=origem_ia,
            rotulo=motivo or "refino Ollama",
            trecho=trecho,
        ))

    if out.get("numero"):
        ant = linha.get("Número")
        linha["Número"] = numero_com_sigla_front(out["numero"], modalidade)
        if out.get("ano"):
            linha["Ano"] = out["ano"]
        _aud_ia(
            "Número", linha["Número"],
            trecho=out.get("trecho_numero") or "",
            motivo="IA alterou (antes: {0})".format(ant or "—"),
        )
    if out.get("objeto"):
        ant = (linha.get("Objeto") or "")[:60]
        linha["Objeto"] = out["objeto"]
        _aud_ia(
            "Objeto", out["objeto"],
            trecho=out.get("trecho_objeto") or "",
            motivo="IA alterou (antes: {0})".format(ant or "—"),
        )
    if out.get("situacao"):
        ant = linha.get("Situação da Licitação")
        linha["Situação da Licitação"] = situacao_para_front(out["situacao"])
        _aud_ia(
            "Situação da Licitação", linha["Situação da Licitação"],
            trecho=out.get("motivo_situacao") or "",
            motivo="IA alterou (antes: {0})".format(ant or "—"),
        )
    for campo_linha, campo_ia, chave_trecho in (
        ("Valor Estimado", "valor_estimado", "trecho_valor_estimado"),
        ("Valor Homologado", "valor_homologado", "trecho_valor_homologado"),
    ):
        v = out.get(campo_ia) or ""
        if not v:
            continue
        ant = linha.get(campo_linha)
        try:
            linha[campo_linha] = float(v)
            valor_aud = float(v)
        except ValueError:
            linha[campo_linha] = v
            valor_aud = v
        _aud_ia(
            campo_linha, valor_aud,
            trecho=out.get(chave_trecho) or "",
            motivo="IA alterou (antes: {0})".format(ant if ant not in ("", None) else "—"),
        )
    out["auditoria"] = aud_ia
    return out


# ============================================================================
# MAIN
# ============================================================================
def main():
    ap = argparse.ArgumentParser(
        description="Baixa licitações de portais CR2 e preenche planilha.")
    ap.add_argument("--listagem", default=LISTAGEM_PADRAO,
                    help="URL da listagem de licitações (obrigatória).")
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
    ap.add_argument(
        "--link-pasta-base",
        default="",
        help="URL base (Drive/SharePoint) para montar LinkDaPasta. "
             "Vazio = usa caminho local absoluto da pasta de anexos.",
    )
    ap.add_argument(
        "--refinar-ia", action="store_true",
        help="Refina numero/objeto/situacao/valores com Ollama local (grátis).",
    )
    ap.add_argument(
        "--modelo-ia", default="llama3.2:3b",
        help="Modelo Ollama (padrão: llama3.2:3b).",
    )
    ap.add_argument(
        "--ollama-url", default="http://127.0.0.1:11434",
        help="URL do Ollama (padrão: http://127.0.0.1:11434).",
    )
    ap.add_argument(
        "--ia-sempre", action="store_true",
        help="Chama a IA mesmo quando regras já preencheram os campos "
             "(padrão: só chama se faltar número/objeto/situação/valor).",
    )
    ap.add_argument(
        "--limite", type=int, default=0,
        help="Processa no máximo N licitações (0 = todas). Útil para testes.",
    )
    args = ap.parse_args()

    if not (args.listagem or "").strip():
        ap.error("Informe --listagem com a URL da página de licitações.")

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
    if args.limite and args.limite > 0:
        print(f"Limite   : {args.limite} licitação(ões)")
    if args.refinar_ia:
        print(f"IA       : Ollama / {args.modelo_ia} @ {args.ollama_url}"
              + (" (só se faltar campo)" if not args.ia_sempre else " (sempre)"))
    else:
        print("IA       : desligada")
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
    if args.limite and args.limite > 0:
        licitacoes = licitacoes[: args.limite]
    print(f"\n► {len(licitacoes)} licitação(ões) a processar.\n")

    linhas_planilha, auditoria_geral = [], []
    itens_upload = []  # {linha, pasta, titulo} para subir*.xlsx

    puladas_ano = 0
    cancelado = False
    total_lic = len(licitacoes)
    try:
        for idx, lic in enumerate(licitacoes, 1):
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
                    _log("  · [{0}/{1}] pulada (ano {2} fora do filtro)",
                         idx, total_lic, ano)
                    continue
                if not ano:
                    _log("  ! [{0}/{1}] sem ano identificável (mantida): {2}",
                         idx, total_lic, titulo[:55])

            pasta = os.path.join(args.saida, nome_pasta(titulo))
            os.makedirs(pasta, exist_ok=True)

            barra = _barra(idx - 1, total_lic)
            _log("")
            _log("── [{0}/{1} · {2}%] {3} {4}",
                 idx, total_lic, _pct(idx - 1, total_lic), barra, titulo[:55])
            _log("    etapa: baixar anexos ({0} link(s))...",
                 len(lic.get("anexos") or []))

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
                _log("    etapa: ler documentos prioritários...")
                arquivos_texto, cabecalhos, nomes_docs = _ler_docs_priorizados(
                    arquivos_locais, args.ocr, args.idioma_ocr, motor_ocr,
                    renomear, pasta,
                )
                _log("    etapa: extrair valores / situação...")
                for item in _aplicar_valores_prioritarios(
                    linha, cabecalhos, arquivos_texto,
                    modalidade, data_pub, ano,
                ):
                    item["licitacao"] = titulo
                    auditoria_geral.append(item)

                sit = situacao_para_front(
                    inferir_situacao(titulo, nomes_docs, modalidade=modalidade)
                )
                linha["Situação da Licitação"] = sit
                auditoria_geral.append({
                    **_item_aud_simples(
                        "Situação da Licitação", sit,
                        doc="título + nomes dos anexos",
                        rotulo="inferir_situacao (regras)",
                        trecho=(titulo or "")[:120],
                    ),
                    "licitacao": titulo,
                })

                # Número com sigla (ex.: 002/2023-AD)
                num_final = numero_com_sigla_front(
                    linha.get("Número") or numero, modalidade
                )
                linha["Número"] = num_final
                auditoria_geral.append({
                    **_item_aud_simples(
                        "Número", num_final,
                        doc="título da listagem",
                        rotulo="split_modalidade_numero + sigla Front",
                        trecho=(titulo or "")[:120],
                    ),
                    "licitacao": titulo,
                })
                auditoria_geral.append({
                    **_item_aud_simples(
                        "Modalidade", modalidade,
                        doc="título da listagem",
                        rotulo="modalidade_padrao (regras)",
                        trecho=(titulo or "")[:120],
                    ),
                    "licitacao": titulo,
                })
                auditoria_geral.append({
                    **_item_aud_simples(
                        "Objeto", linha.get("Objeto") or "",
                        doc="título da listagem",
                        rotulo="extrai_objeto (texto entre parênteses)",
                        trecho=(titulo or "")[:160],
                    ),
                    "licitacao": titulo,
                })

                est = linha.get("Valor Estimado")
                hom = linha.get("Valor Homologado")
                _log(
                    "    leitura: nº {0} | sit. {1} | est. {2} | hom. {3}",
                    linha.get("Número") or "—",
                    linha.get("Situação da Licitação") or "—",
                    est if est not in ("", None) else "—",
                    hom if hom not in ("", None) else "—",
                )

                if args.refinar_ia:
                    pasta_cache = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), "cache_ia"
                    )
                    out_ia = _refinar_com_ollama(
                        titulo, linha, cabecalhos, modalidade,
                        modelo=args.modelo_ia,
                        ollama_url=args.ollama_url,
                        pasta_cache=pasta_cache,
                        so_se_faltar=not args.ia_sempre,
                    )
                    if out_ia:
                        for item in out_ia.get("auditoria") or []:
                            item["licitacao"] = titulo
                            auditoria_geral.append(item)

            linhas_planilha.append(linha)
            itens_upload.append({
                "linha": dict(linha),
                "pasta": os.path.abspath(pasta),
                "titulo": titulo,
            })
            _log("    ✓ [{0}/{1} · {2}%] concluída {3}",
                 idx, total_lic, _pct(idx, total_lic), _barra(idx, total_lic))
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
        print("  · Aba 'Auditoria': origem de cada campo (documento + trecho)")
        global ULTIMO_RESULTADO_UPLOAD
        ULTIMO_RESULTADO_UPLOAD = {
            "planilha_preenchida": os.path.abspath(args.planilha_saida),
            "planilha_auditoria": os.path.abspath(args.planilha_saida),
        }

        # Planilhas oficiais de upload (Front)
        try:
            from gestor_regras import gerar_planilhas_upload
        except ImportError:
            # execução via load_module do painel: pasta do script no path
            _dir_script = os.path.dirname(os.path.abspath(__file__))
            if _dir_script not in sys.path:
                sys.path.insert(0, _dir_script)
            from gestor_regras import gerar_planilhas_upload

        print("\n► Gerando planilhas de upload (subirLicitacoes / subirDocumentos / contratos)...")
        resultado_upload = gerar_planilhas_upload(
            itens_upload,
            args.saida,
            link_pasta_base=(args.link_pasta_base or "").strip(),
            ler_texto=obter_texto,
            usar_ocr=bool(args.ocr),
            idioma_ocr=getattr(args, "idioma_ocr", "por") or "por",
            motor_ocr=(getattr(args, "motor_ocr", None) or "auto"),
            usar_ia_contratos=bool(getattr(args, "refinar_ia", False)),
            modelo_ia=(getattr(args, "modelo_ia", None) or "llama3.2:3b"),
            ollama_url=(getattr(args, "ollama_url", None) or "http://127.0.0.1:11434"),
        )
        print(
            "  ✓ Prontas: {0}  |  Pendentes: {1}".format(
                resultado_upload["prontas"],
                resultado_upload["pendentes"],
            )
        )
        print("  ✓ {0}".format(resultado_upload["planilha_licitacoes"]))
        print("  ✓ {0}".format(resultado_upload["planilha_documentos"]))
        if resultado_upload.get("planilha_contratos"):
            print("  ✓ Contratos: {0} linha(s) → {1}".format(
                resultado_upload.get("contratos_extraidos", "?"),
                resultado_upload["planilha_contratos"],
            ))
        if resultado_upload.get("contratos_movidos"):
            print("  · Contratos separados: {0} arquivo(s) em Contratos/".format(
                resultado_upload["contratos_movidos"]))
            for msg in (resultado_upload.get("logs_contratos") or [])[:8]:
                print("  · {0}".format(msg))
        if resultado_upload["pendentes"]:
            print("  · Pendentes: {0}".format(resultado_upload["pendentes_relatorio"]))
            for msg in (resultado_upload.get("logs_move") or [])[:10]:
                print("  · Pasta pendente: {0}".format(msg))
            if len(resultado_upload.get("logs_move") or []) > 10:
                print("  · … (+{0} pastas movidas)".format(
                    len(resultado_upload["logs_move"]) - 10))
        for msg in (resultado_upload.get("logs_link") or [])[:5]:
            print("  · {0}".format(msg))
        if len(resultado_upload.get("logs_link") or []) > 5:
            print("  · … (+{0} pastas)".format(
                len(resultado_upload["logs_link"]) - 5))

        # expõe caminhos para o runner do painel
        ULTIMO_RESULTADO_UPLOAD.update(resultado_upload or {})
        ULTIMO_RESULTADO_UPLOAD["planilha_preenchida"] = os.path.abspath(
            args.planilha_saida
        )
        ULTIMO_RESULTADO_UPLOAD["planilha_auditoria"] = (
            ULTIMO_RESULTADO_UPLOAD["planilha_preenchida"]
        )  # aba Auditoria dentro do mesmo arquivo

    print("\n" + "=" * 66)
    print("CANCELADO." if cancelado else "Concluído.")
    if not args.sem_extracao:
        print("  Planilhas oficiais: subirLicitacoes.xlsx + subirDocumentosLicitacoes.xlsx")
        print("  Contratos: Contratos/ + contratos.xlsx (aba Auditoria) + contratos.csv")
        print("  Veja também a aba 'Auditoria' e a pasta PENDENTES/ se houver faltas.")
    print("=" * 66)
    if cancelado:
        raise Cancelado()


if __name__ == "__main__":
    main()
