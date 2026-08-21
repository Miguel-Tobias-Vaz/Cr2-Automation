# -*- coding: utf-8 -*-
"""Campos da planilha de contratos (subirContratos.xlsx) a partir do texto dos PDFs.

Regras puras: recebem nome de arquivo + texto e devolvem o valor já no formato
do portal. Sem I/O — quem lê PDF é upload_contratos.py.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

from .config_front import (
    CAMPOS_OBRIGATORIOS_CONTRATO,
    ROTULOS_CONTRATO,
    TIPO_ADITIVO,
    TIPO_CONTRATO,
)
from .front import data_front, valor_front

# Nome de pessoa/empresa: letras acentuadas, espaço, ponto, hífen e apóstrofo.
_NOME = r"A-Za-zÀ-ÿ'\.\- "

# --------------------------------------------------------------------------
# tipoContrato — "Contrato" ou "Aditivo 01"
# --------------------------------------------------------------------------
_ORDINAIS = {
    "primeiro": 1, "segundo": 2, "terceiro": 3, "quarto": 4, "quinto": 5,
    "sexto": 6, "setimo": 7, "oitavo": 8, "nono": 9, "decimo": 10,
    "undecimo": 11, "duodecimo": 12,
}
_RE_ADITIVO = re.compile(r"termo\s*aditivo|\baditivo\b|apostilamento", re.I)
# "1º Termo Aditivo", "2 TERMO ADITIVO", "3o. termo aditivo"
_RE_ADITIVO_ANTES = re.compile(r"(\d{1,2})\s*[ºo°ª.]{0,2}\s*termo\s*aditivo", re.I)
# "Termo Aditivo nº 02", "aditivo 2", "aditivo n. 03"
_RE_ADITIVO_DEPOIS = re.compile(
    r"(?:termo\s*)?aditivo\s*(?:n[ºo°.\s]*)?(\d{1,2})\b", re.I
)
_RE_ADITIVO_ORDINAL = re.compile(
    r"\b(primeiro|segundo|terceiro|quarto|quinto|sexto|s[eé]timo|oitavo|nono|"
    r"d[eé]cimo|und[eé]cimo|duod[eé]cimo)\s+termo\s+aditivo",
    re.I,
)


def _sem_acento(txt: str) -> str:
    n = unicodedata.normalize("NFKD", str(txt or ""))
    return "".join(c for c in n if not unicodedata.combining(c))


def _plano(txt: str) -> str:
    """Minúsculo e sem acento, MESMO tamanho do original.

    Preserva o comprimento para que um índice achado aqui sirva para fatiar o
    texto original (NFKD normal muda o tamanho e desalinha as posições).
    """
    saida = []
    for ch in str(txt or ""):
        base = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in base if not unicodedata.combining(c))
        saida.append((base[:1] or ch).lower())
    return "".join(saida)


def _flex(palavra: str) -> str:
    """Regex tolerante à sujeira de PDF destes portais.

    Ex.: "vigência" sai do pdfplumber como "vige ncia" (acento virou espaço) ou
    "vig�ncia" (virou U+FFFD). Cada letra aceita as duas formas.
    """
    partes = []
    for ch in _plano(palavra):
        if ch.isspace():
            partes.append(r"\s+")
        else:
            partes.append("(?:%s|�)[\\s�]{0,2}" % re.escape(ch))
    return "".join(partes)


def _limpa(txt: str) -> str:
    return re.sub(r"\s+", " ", str(txt or "")).strip(" \t\n\r.,;:-")


def eh_aditivo(nome_arquivo: str, texto: str = "") -> bool:
    """Aditivo/apostilamento — decide pelo nome; texto só como reforço."""
    base = os.path.splitext(os.path.basename(nome_arquivo or ""))[0]
    if _RE_ADITIVO.search(base):
        return True
    # nome genérico (ex. "doc01.pdf"): olha o começo do documento
    if base and not re.search(r"contrato", base, re.I):
        return bool(_RE_ADITIVO.search((texto or "")[:1500]))
    return False


def tipo_contrato(nome_arquivo: str, texto: str = "") -> str:
    """Devolve "Contrato" ou "Aditivo NN" (NN com 2 dígitos)."""
    if not eh_aditivo(nome_arquivo, texto):
        return TIPO_CONTRATO
    base = os.path.splitext(os.path.basename(nome_arquivo or ""))[0]
    for fonte in (base, (texto or "")[:2000]):
        if not fonte:
            continue
        m = _RE_ADITIVO_ANTES.search(fonte)
        if m:
            return "%s %02d" % (TIPO_ADITIVO, int(m.group(1)))
        m = _RE_ADITIVO_ORDINAL.search(fonte)
        if m:
            n = _ORDINAIS.get(_sem_acento(m.group(1)).lower())
            if n:
                return "%s %02d" % (TIPO_ADITIVO, n)
        m = _RE_ADITIVO_DEPOIS.search(fonte)
        if m:
            return "%s %02d" % (TIPO_ADITIVO, int(m.group(1)))
    # aditivo sem ordem identificada — portal trata o 01 como primeiro
    return "%s 01" % TIPO_ADITIVO


# --------------------------------------------------------------------------
# numero / ano — número DO CONTRATO (aditivo herda o número do contrato)
# --------------------------------------------------------------------------
_RE_NUM_ROTULADO = re.compile(r"contrato[^\n\d]{0,60}?(\d{1,6})\s*/\s*(\d{4})", re.I)
_RE_NUM_SOLTO = re.compile(r"(?<!\d)(\d{1,6})\s*/\s*(\d{4})(?!\d)")
# No nome do arquivo a barra não existe: "Contrato 003-2025.pdf", "contrato_12_2024"
_RE_NUM_ARQ_ROTULADO = re.compile(
    r"contrato[^\d]{0,20}?(\d{1,6})\s*[-_/.]\s*(\d{4})(?!\d)", re.I
)
_RE_NUM_ARQ_SOLTO = re.compile(r"(?<!\d)(\d{1,6})\s*[-_/.]\s*(\d{4})(?!\d)")


def _num_normalizado(num: str, ano: str) -> str:
    num = (num or "").lstrip("0") or "0"
    return "%s/%s" % (num.zfill(3), ano)


def _ano_ok(ano: str) -> bool:
    return 1990 <= int(ano) <= 2100


def numero_contrato(nome_arquivo: str, texto: str = "") -> str:
    """Número do contrato no formato NNN/AAAA (texto tem prioridade sobre o nome)."""
    base = os.path.splitext(os.path.basename(nome_arquivo or ""))[0]
    corpo = (texto or "")[:4000]

    # 1) "CONTRATO Nº 003/2025" no texto ou no nome
    for rx, fonte in (
        (_RE_NUM_ROTULADO, corpo),
        (_RE_NUM_ARQ_ROTULADO, base),
    ):
        if not fonte:
            continue
        m = rx.search(fonte)
        if m and _ano_ok(m.group(2)):
            return _num_normalizado(m.group(1), m.group(2))

    # 2) qualquer NNN/AAAA no texto; depois NNN-AAAA no nome
    for rx, fonte in (
        (_RE_NUM_SOLTO, corpo),
        (_RE_NUM_ARQ_SOLTO, base),
    ):
        if not fonte:
            continue
        for m in rx.finditer(fonte):
            if _ano_ok(m.group(2)):
                return _num_normalizado(m.group(1), m.group(2))
    return ""


def ano_contrato(numero: str, *datas: str) -> str:
    """Ano do contrato: do número; senão da 1ª data válida informada."""
    m = re.search(r"/(\d{4})$", (numero or "").strip())
    if m and 1990 <= int(m.group(1)) <= 2100:
        return m.group(1)
    for d in datas:
        m = re.search(r"/(\d{4})$", data_front(d) or "")
        if m:
            return m.group(1)
    return ""


# --------------------------------------------------------------------------
# objeto
# --------------------------------------------------------------------------
_FIM_CLAUSULA = r"(?=\n\s*(?:cl[áa]usula|par[áa]grafo|art\.|artigo)\b|$)"
_RES_OBJETO = (
    re.compile(
        r"\b(?:objeto|objeto\s+da\s+contrata[çc]ao|objeto\s+do\s+contrato)\s*[:\-–]?\s*(.{40,1500}?)"
        + _FIM_CLAUSULA,
        re.I | re.S,
    ),
    re.compile(
        r"cl[áa]usula\s+\S+[^\n]{0,60}?\bobjeto\b\s*[:\-–]?\s*(.{40,1500}?)" + _FIM_CLAUSULA,
        re.I | re.S,
    ),
    re.compile(r"\bdo\s+objeto\b\s*[:\-–]?\s*(.{40,1500}?)" + _FIM_CLAUSULA, re.I | re.S),
    re.compile(r"\bobjeto\b\s*[:\-–]\s*(.{40,1500}?)" + _FIM_CLAUSULA, re.I | re.S),
    re.compile(
        r"\btem\s+(?:como\s+)?por\s+objeto\b\s*[:\-–]?\s*(.{40,1500}?)" + _FIM_CLAUSULA, re.I | re.S
    ),
    re.compile(
        r"\bobjeto\s+(?:d[ae]|do)\s+(?:presente\s+)?(?:contrat(?:a[cç][ãa]o|o))\b[^.]{0,40}?[:\-–]?\s*(.{40,1500}?)"
        + _FIM_CLAUSULA,
        re.I | re.S,
    ),
    re.compile(
        r"\bobjeto\s+d[oe]\s+(?:presente\s+)?contrato\b[^.]{0,40}?[:\-–]?\s*(.{40,1500}?)"
        + _FIM_CLAUSULA,
        re.I | re.S,
    ),
)


def objeto_contrato(texto: str, max_chars: int = 600) -> str:
    for rx in _RES_OBJETO:
        m = rx.search(texto or "")
        if not m:
            continue
        obj = _limpa(m.group(1))
        # corta em fim de frase para não arrastar a cláusula seguinte
        if len(obj) > max_chars:
            corte = obj.rfind(".", 0, max_chars)
            obj = obj[: corte + 1] if corte > 120 else obj[:max_chars]
        if len(obj) >= 20:
            return obj
    return ""


# --------------------------------------------------------------------------
# contratada (nomeRazaoSocial) + cpfCnpj
# --------------------------------------------------------------------------
_RE_CNPJ = re.compile(r"\b(\d{2}\.?\d{3}\.?\d{3}\s*/\s*\d{4}\s*-?\s*\d{2})\b")
_RE_CPF = re.compile(r"\b(\d{3}\.\d{3}\.\d{3}\s*-\s*\d{2})\b")
# Forma 1: "CONTRATADA: <nome> ... CNPJ" (exige separador, senão casa
# "CONTRATADA, feita na sessão…" no meio do texto).
_RE_CONTRATADA_ROTULO = re.compile(r"contratad[oa]\s*(?:\(a\))?\s*[:\-–]\s*", re.I)
# Forma 2: "<nome> ... CNPJ ... doravante denominada (simplesmente de) CONTRATADA"
_RE_CONTRATADA_DORAVANTE = re.compile(
    r"doravante\s+denominad[oa][^.]{0,60}?contratad[oa]\b", re.I
)
_RE_CONTRATANTE_DORAVANTE = re.compile(
    r"denominad[oa]s?\s+contratante\s*[:\-–]?", re.I
)
# Entre o nome e o CNPJ cabe "inscrita no Cadastro Nacional de Pessoa Jurídica -".
# Sem \n na classe: o bloco é normalizado antes (o nome quebra linha no PDF,
# ex. "APFORM\nINDUSTRIA E COMERCIO DE MOVEIS LTDA").
_RE_NOME_ANTES_CNPJ = re.compile(
    r"([A-ZÀ-Þ][^,;:]{4,120}?)\s*,?\s*"
    r"(?:pessoa\s+jur[íi]dica[^,]{0,60},?\s*)?"
    r"(?:devidamente\s+)?(?:inscrit[ao]|cadastrad[ao])?[^,;]{0,80}?"
    r"C\.?\s?N\.?\s?P\.?\s?J",
    re.I,
)
_RE_BLOCO_CONTRATADA = _RE_CONTRATADA_ROTULO  # compat: usado por cnpj_orgao
_RE_CORTE_NOME = re.compile(
    r",|\s+inscrit|\s+pessoa\s+jur|\s+cadastrad|\s+estabelecid|\s+com\s+sede|"
    r"\s+sediad|\s+doravante|\s+CNPJ|\s+C\.N\.P\.J|\s+neste\s+ato",
    re.I,
)
_SUFIXOS_EMPRESA = re.compile(
    r"\b(ltda|eireli|s\.?/?a|me|epp|mei|eirl|sociedade|comercio|com[eé]rcio|"
    r"servi[çc]os|constru[çt]|transporte|distribuidora|empreendimentos)\b",
    re.I,
)


def _so_digitos(txt: str) -> str:
    return re.sub(r"\D", "", str(txt or ""))


def _fmt_doc(bruto: str) -> str:
    d = _so_digitos(bruto)
    if len(d) == 14:
        return "%s.%s.%s/%s-%s" % (d[:2], d[2:5], d[5:8], d[8:12], d[12:])
    if len(d) == 11:
        return "%s.%s.%s-%s" % (d[:3], d[3:6], d[6:9], d[9:])
    return _limpa(bruto)


def _nome_limpo(bruto: str) -> str:
    nome = _limpa(bruto)
    m = _RE_CORTE_NOME.search(nome)
    if m:
        nome = nome[: m.start()].strip(" \t.,;:-")
    nome = re.sub(
        r"^(?:a\s+empresa|o\s+senhor|a\s+senhora|sr\.?|sra\.?)\s+",
        "",
        nome,
        flags=re.I,
    )
    return _limpa(nome)


def bloco_contratada(texto: str) -> str:
    """Trecho do preâmbulo que descreve a CONTRATADA (nome + CNPJ + sede)."""
    texto = texto or ""

    # Forma 1: rótulo "CONTRATADA:" seguido do nome
    m = _RE_CONTRATADA_ROTULO.search(texto)
    if m:
        depois = texto[m.end(): m.end() + 700]
        if _RE_CNPJ.search(depois) or _RE_CPF.search(depois):
            return depois

    # Forma 2: descrição ANTES de "doravante denominada … CONTRATADA".
    # Corta no "denominado CONTRATANTE" anterior para não pegar o órgão.
    m = _RE_CONTRATADA_DORAVANTE.search(texto)
    if m:
        bloco = texto[max(0, m.start() - 1000): m.start()]
        cortes = list(_RE_CONTRATANTE_DORAVANTE.finditer(bloco))
        if cortes:
            bloco = bloco[cortes[-1].end():]
        return bloco
    return ""


def contratada(texto: str, cnpj_orgao: str = "") -> tuple[str, str]:
    """(nomeRazaoSocial, cpfCnpj) da empresa contratada."""
    texto = texto or ""
    dig_orgao = _so_digitos(cnpj_orgao)
    # quebra de linha no meio do nome/do rótulo do CNPJ atrapalha os regexes
    bloco = re.sub(r"\s+", " ", bloco_contratada(texto))
    texto = re.sub(r"[ \t]*\n[ \t]*", " ", texto)

    # 1) nome imediatamente antes do CNPJ, preferindo o bloco da CONTRATADA
    for fonte in (bloco, texto):
        if not fonte:
            continue
        for mm in _RE_NOME_ANTES_CNPJ.finditer(fonte):
            nome = _nome_limpo(mm.group(1))
            depois = fonte[mm.end(): mm.end() + 60]
            mdoc = _RE_CNPJ.search(depois) or _RE_CPF.search(depois)
            doc = _fmt_doc(mdoc.group(1)) if mdoc else ""
            if doc and dig_orgao and _so_digitos(doc) == dig_orgao:
                continue
            if nome and len(nome) >= 5:
                return nome, doc

    # 2) primeiro documento que não é do órgão + nome logo antes dele
    for fonte in (bloco, texto):
        if not fonte:
            continue
        for mdoc in list(_RE_CNPJ.finditer(fonte)) + list(_RE_CPF.finditer(fonte)):
            doc = _fmt_doc(mdoc.group(1))
            if dig_orgao and _so_digitos(doc) == dig_orgao:
                continue
            antes = fonte[max(0, mdoc.start() - 220): mdoc.start()]
            partes = [p for p in re.split(r"[\n,;]", antes) if _limpa(p)]
            nome = _nome_limpo(partes[-1]) if partes else ""
            if nome and (len(nome) >= 8 or _SUFIXOS_EMPRESA.search(nome)):
                return nome, doc
            return "", doc
    return "", ""


def cnpj_orgao(texto: str) -> str:
    """CNPJ do órgão — só o que aparece ANTES do bloco da CONTRATADA.

    Aditivo costuma não repetir o CNPJ da prefeitura: nesse caso devolve vazio,
    senão o CNPJ da contratada seria descartado como se fosse do órgão.
    """
    texto = texto or ""
    bloco = bloco_contratada(texto)
    pos = texto.find(bloco) if bloco else -1
    trecho = texto[:pos] if pos > 0 else ("" if bloco else texto)
    m = _RE_CNPJ.search(trecho[:2500])
    return _fmt_doc(m.group(1)) if m else ""


# --------------------------------------------------------------------------
# vigência
# --------------------------------------------------------------------------
_D = r"(\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{2,4}|\d{1,2}\s+de\s+\w+\s+de\s+\d{4})"
# Âncoras via _flex: o PDF pode trazer "vige ncia" / "vig�ncia".
_VIG = _flex("vigenc") + r"\w*"
_RE_VIG_INTERVALO = re.compile(
    _VIG + r"[^.]{0,240}?" + _D + r"[^.]{0,60}?\b(?:a|at[ée]|ao?\s+dia|at[eé])\b[^.]{0,60}?" + _D,
    re.I | re.S,
)
_RE_VIG_INTERVALO_SIMPLES = re.compile(
    r"\b(?:prazo\s+de\s+)?(?:vig[eê]ncia|prazo)\b[^.]{0,80}?"
    + _D + r"\s*(?:a|at[ée]|at[eé]|ate|até|ao?\s+dia)\s*" + _D,
    re.I | re.S,
)
_RE_VIG_INICIO_FIM = re.compile(
    _flex("inicio") + r"[^.]{0,80}?" + _D + r"[^.]{0,160}?"
    + _flex("termino") + r"[^.]{0,80}?" + _D,
    re.I | re.S,
)
_RE_VIG_ATE = re.compile(
    _VIG + r"[^.]{0,200}?\b(?:at[ée]|viger[áa]\s+at[ée])\b[^.]{0,60}?" + _D,
    re.I | re.S,
)
_RE_VIG_PERIODO = re.compile(
    r"(?:prazo|" + _VIG + r")[^.]{0,160}?(\d{1,3})\s*(?:\([^)]{0,40}\))?\s*"
    r"(mes(?:es)?|dias?|anos?)[^.]{0,160}?"
    r"(?:a\s+(?:contar|partir)\s+d[eoa]s?|com\s+in[íi]cio\s+em|"
    r"a\s+partir\s+da\s+data\s+de)[^.]{0,80}?" + _D,
    re.I | re.S,
)
_RE_ASSINATURA = re.compile(
    r"(?:assinad[oa]|assinatura|firmad[oa]|aos?)\s*[,:]?\s*" + _D, re.I
)
_MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
    "dezembro": 12,
}


def _data_extenso(txt: str) -> str:
    m = re.match(r"\s*(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", str(txt or ""), re.I)
    if not m:
        return ""
    mes = _MESES.get(_sem_acento(m.group(2)).lower())
    if not mes:
        return ""
    return "%02d/%02d/%s" % (int(m.group(1)), mes, m.group(3))


def _data(txt: str) -> str:
    return data_front(txt) or _data_extenso(txt)


def _mais_periodo(data_ini: str, quanto: int, unidade: str) -> str:
    """data_ini + N meses/dias/anos (fim da vigência), em dd/mm/aaaa."""
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", data_ini or "")
    if not m or quanto <= 0:
        return ""
    import calendar
    from datetime import date, timedelta

    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    u = _sem_acento(unidade).lower()
    try:
        base = date(ano, mes, dia)
    except ValueError:
        return ""
    if u.startswith("dia"):
        fim = base + timedelta(days=quanto)
    else:
        meses = quanto * 12 if u.startswith("ano") else quanto
        total = (mes - 1) + meses
        ano_f, mes_f = ano + total // 12, total % 12 + 1
        dia_f = min(dia, calendar.monthrange(ano_f, mes_f)[1])
        fim = date(ano_f, mes_f, dia_f)
    return fim.strftime("%d/%m/%Y")


def vigencia(texto: str) -> tuple[str, str]:
    """(dataVigenciaIN, dataVigenciaFIM) em dd/mm/aaaa.

    Busca no texto achatado (_plano) porque as âncoras dependem de letras; as
    datas são dígitos, então saem iguais ao original.
    """
    texto = _plano(texto or "")
    for rx in (_RE_VIG_INTERVALO_SIMPLES, _RE_VIG_INTERVALO, _RE_VIG_INICIO_FIM):
        m = rx.search(texto)
        if not m:
            continue
        if rx is _RE_VIG_INTERVALO_SIMPLES:
            grupos = [g for g in m.groups() if g]
            if len(grupos) >= 2:
                ini, fim = _data(grupos[0]), _data(grupos[1])
                if ini and fim:
                    return ini, fim
            continue
        if len(m.groups()) >= 2:
            ini, fim = _data(m.group(1)), _data(m.group(2))
            if ini and fim:
                return ini, fim
    m = _RE_VIG_PERIODO.search(texto)
    if m:
        ini = _data(m.group(3))
        if ini:
            return ini, _mais_periodo(ini, int(m.group(1)), m.group(2))
    m = _RE_VIG_ATE.search(texto)
    if m:
        fim = _data(m.group(1))
        if fim:
            ma = _RE_ASSINATURA.search(texto)
            return (_data(ma.group(1)) if ma else ""), fim
    return "", ""


# --------------------------------------------------------------------------
# valor
# --------------------------------------------------------------------------
_ROTULOS_VALOR = (
    "valor global", "valor total", "valor do contrato", "valor contratado",
    "valor do presente contrato", "importa em", "valor da contratacao",
    "valor estimado", "valor acrescido", "valor do acrescimo", "valor mensal",
)
_RE_RS = re.compile(r"R\$\s*([\d.,]{4,25})")


def valor_contrato(texto: str, janela: int = 260) -> str:
    """Valor no formato do portal (0.00). Prioriza global/total.

    _plano preserva o tamanho, então a posição achada no texto achatado serve
    para fatiar o original (onde o "R$ 1.234,56" está intacto).
    """
    texto = texto or ""
    plano = _plano(texto)
    for rotulo in _ROTULOS_VALOR:
        for m_rot in re.finditer(_flex(rotulo), plano, re.I):
            m = _RE_RS.search(texto[m_rot.start(): m_rot.start() + janela])
            if m:
                v = valor_front(m.group(1))
                if v and float(v) > 0:
                    return v
    # Sem rótulo, NÃO adivinha: o primeiro "R$" do documento costuma ser preço
    # de item de tabela. Vazio + alerta no relatório é melhor que valor errado
    # subindo no portal.
    return ""


# --------------------------------------------------------------------------
# fiscal do contrato
# --------------------------------------------------------------------------
_RE_FISCAL_ROTULO = re.compile(
    r"(?:fiscal|gestor)\s*(?:d[oe]\s*(?:presente\s*)?contrato)?\s*[:\-–]\s*"
    r"([" + _NOME + r"]{6,80})",
    re.I,
)
# Cada grupo opcional termina em \s+ para consumir a palavra inteira — sem isso
# "os servidores" casava só o "o" e sobrava "s servidores" no nome.
_RE_FISCAL_DESIGNAR = re.compile(
    r"(?:designar|designo|fica[mn]?\s+designad[oa]s?|nomear|nomeio)\s+"
    r"(?:(?:os?|as?)\s+)?"
    r"(?:(?:servidor(?:a|es|as)?|senhor(?:a|es)?|sr\.?|sra\.?|"
    r"funcion[áa]ri[oa]s?)\s+)?"
    r"([" + _NOME + r"]{6,80}?)"
    r"(?=,|\s+matr[íi]cula|\s+portador|\s+inscrit|\s+CPF|\s+para|\s+como|\.|\n)",
    re.I,
)
# "… como FISCAL TITULAR" — em termo de designação com titular + substituto,
# o titular é o fiscal do contrato. Aceita pontos no meio ("CPF nº. 036...").
_RE_FISCAL_TITULAR = re.compile(
    r"([" + _NOME + r"]{6,80}?)\s*,.{0,260}?como\s+fiscal\s+titular", re.I | re.S
)
# Lixo que antecede o nome dentro da captura ("Ficam designado os servidores X").
# Guloso de propósito: corta até a ÚLTIMA palavra de função antes do nome.
_RE_PREFIXO_NOME = re.compile(
    r"^.*\b(?:servidor(?:a|es|as)?|funcion[áa]ri[oa]s?|designad[oa]s?|"
    r"senhor(?:a|es)?)\b\s*",
    re.I | re.S,
)
_RE_FISCAL_COMO = re.compile(
    r"([" + _NOME + r"]{6,80}?)\s*,?\s*(?:como|para)\s+(?:ser\s+)?(?:o|a)?\s*fiscal\s+d[oe]",
    re.I,
)
_RUIDO_NOME = re.compile(
    r"\b(contrato|contratante|contratada|prefeitura|munic[íi]pio|municipio|"
    r"c[âa]mara|secretaria|portaria|decreto|lei|cl[áa]usula|processo|"
    r"fiscaliza[çc][ãa]o|gest[ãa]o|servidor|comiss[ãa]o|objeto|empresa)\b",
    re.I,
)


def fiscal_contrato(texto: str) -> str:
    """Nome do fiscal — do contrato ou do termo/portaria de designação."""
    texto = texto or ""
    ordem = (
        _RE_FISCAL_TITULAR,   # titular vence o substituto
        _RE_FISCAL_ROTULO,
        _RE_FISCAL_COMO,
        _RE_FISCAL_DESIGNAR,
    )
    for rx in ordem:
        for m in rx.finditer(texto):
            nome = _limpa(m.group(1))
            nome = re.sub(r"\s+(?:para|como|matr[íi]cula).*$", "", nome, flags=re.I)
            # "Ficam designado os servidores MARCELO …" -> "MARCELO …"
            nome = _limpa(_RE_PREFIXO_NOME.sub("", nome))
            if len(nome) < 6 or _RUIDO_NOME.search(nome):
                continue
            if len(nome.split()) < 2:
                continue
            return nome
    return ""


# --------------------------------------------------------------------------
# linha completa
# --------------------------------------------------------------------------
def linha_contrato(
    nome_arquivo: str,
    texto: str,
    *,
    licitacao_origem: str = "",
    documento: str = "",
    texto_portaria: str = "",
) -> dict[str, Any]:
    """Monta a linha da planilha de contratos a partir de um documento."""
    texto = texto or ""
    numero = numero_contrato(nome_arquivo, texto)
    ini, fim = vigencia(texto)
    nome, doc_cnpj = contratada(texto, cnpj_orgao(texto))
    fiscal = fiscal_contrato(texto)
    if not fiscal and texto_portaria:
        fiscal = fiscal_contrato(texto_portaria)
    return {
        "licitacao_origem": _limpa(licitacao_origem),
        "ano": ano_contrato(numero, ini, fim),
        "tipo_contrato": tipo_contrato(nome_arquivo, texto),
        "numero": numero,
        "objeto": objeto_contrato(texto),
        "nome_razao_social": nome,
        "cpf_cnpj": doc_cnpj,
        "data_vigencia_in": ini,
        "data_vigencia_fim": fim,
        "valor": valor_contrato(texto),
        "fiscal_contrato": fiscal,
        "documento": documento or os.path.basename(nome_arquivo or ""),
    }


def falta_para_o_portal(linha: dict[str, Any]) -> list[str]:
    """Campos obrigatórios ausentes (rótulos da planilha)."""
    return [
        ROTULOS_CONTRATO.get(c, c)
        for c in CAMPOS_OBRIGATORIOS_CONTRATO
        if not str(linha.get(c) or "").strip()
    ]


def alertas_contrato(linha: dict[str, Any]) -> list[str]:
    """Campos opcionais que ficaram vazios — vão para o relatório."""
    alertas = []
    for chave in (
        "cpf_cnpj", "data_vigencia_in", "data_vigencia_fim", "valor",
        "fiscal_contrato", "licitacao_origem",
    ):
        if not str(linha.get(chave) or "").strip():
            alertas.append("%s: não encontrado" % ROTULOS_CONTRATO.get(chave, chave))
    return alertas
