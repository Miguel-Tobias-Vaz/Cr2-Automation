# -*- coding: utf-8 -*-
"""Regras de extração de campos de Portarias / atos de Diárias."""

from __future__ import annotations

import csv
import datetime
import re
import unicodedata
from pathlib import Path
from typing import Any

# Colunas da planilha (ordem fixa)
CAMPOS_DIARIAS = [
    ("numero_portaria", "Número da Portaria"),
    ("data_portaria", "Data da Portaria"),
    ("inicio_viagem", "Início da Viagem"),
    ("fim_viagem", "Fim da Viagem"),
    ("quantidade_diarias", "Quantidade de Diárias"),
    ("nome", "Nome"),
    ("cargo", "Cargo"),
    ("motivo", "Motivo da Viagem"),
    ("destino", "Destino da Viagem"),
    ("valor_total", "Valor Total"),
    ("arquivo", "Arquivo"),
]

CHAVES = [k for k, _ in CAMPOS_DIARIAS]
ROTINOS = [r for _, r in CAMPOS_DIARIAS]

_MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

_RE_DIARIAS = re.compile(
    r"\bdi[aá]rias?\b|\bajuda\s+de\s+custo\b|\bdeslocamento\b.*\bviagem\b",
    re.I,
)
# Fonte/URL já declara o tipo (ex.: /diarias-ate-2023/)
_RE_FONTE_DIARIAS = re.compile(
    r"di[aá]rias?|ajuda[\-_]?de[\-_]?custo",
    re.I,
)
_RE_DATA_NUM = re.compile(
    r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})\b"
)
_RE_DATA_EXT = re.compile(
    r"\b(\d{1,2})\s+de\s+"
    r"(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})\b",
    re.I,
)
_RE_PORTARIA_NUM = re.compile(
    r"portaria\s*(?:n[º°o\.º]*\s*)?(\d{1,5})\s*[/\-.\s]\s*((?:20|19)\d{2})",
    re.I,
)
_RE_MOEDA = re.compile(
    r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})"
)
_RE_QTD = re.compile(
    r"(?:quantidade\s*(?:de\s*)?di[aá]rias?\s*[:\-]?\s*|"
    r"concedendo(?:\-lhe)?\s*|"
    r"concede(?:\-se)?\s*(?:o\s+total\s+de\s+)?"
    r"|total\s+de\s+)"
    r"(\d{1,3})(?:\s*\([^)]{0,40}\))?\s*(?:\(\s*)?di[aá]rias?",
    re.I,
)
_RE_QTD_ALT = re.compile(
    r"(\d{1,3})\s*(?:\([^)]{0,40}\))?\s*di[aá]rias?\b",
    re.I,
)


def normalizar(txt: str) -> str:
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


def parece_diarias(
    texto: str,
    *,
    pasta_hint: str = "",
    nome_arquivo: str = "",
    url: str = "",
) -> bool:
    """True se a fonte ou o documento for de diárias (regra geral)."""
    # URL/pasta já dizem "diárias" → aplica regras sem depender do corpo do PDF
    for sinal in (url, pasta_hint, nome_arquivo):
        if sinal and _RE_FONTE_DIARIAS.search(sinal):
            return True
    return bool(_RE_DIARIAS.search(texto or ""))


def registro_vazio() -> dict[str, str]:
    return {k: "" for k in CHAVES}


def _fmt_data(d: int, m: int, a: int) -> str:
    try:
        return datetime.date(a, m, d).strftime("%d/%m/%Y")
    except ValueError:
        return ""


def _parse_data_extenso(m: re.Match) -> str:
    mes_txt = normalizar(m.group(2)).replace("ç", "c")
    mes = _MESES.get(mes_txt) or _MESES.get(m.group(2).lower())
    if not mes:
        # marco / março
        for k, v in _MESES.items():
            if normalizar(k) == mes_txt:
                mes = v
                break
    if not mes:
        return ""
    return _fmt_data(int(m.group(1)), mes, int(m.group(3)))


def _datas_no_texto(texto: str) -> list[str]:
    out: list[str] = []
    for m in _RE_DATA_NUM.finditer(texto or ""):
        fmt = _fmt_data(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if fmt:
            out.append(fmt)
    for m in _RE_DATA_EXT.finditer(texto or ""):
        fmt = _parse_data_extenso(m)
        if fmt:
            out.append(fmt)
    return out


def _campo_apos(
    texto: str,
    padroes: list[str],
    *,
    janela: int = 180,
    ate: str | None = None,
) -> str:
    n = texto or ""
    for padrao in padroes:
        for m in re.finditer(padrao, n, flags=re.I):
            trecho = n[m.end() : m.end() + janela]
            if ate:
                trecho = re.split(ate, trecho, maxsplit=1, flags=re.I)[0]
            trecho = re.sub(r"\s+", " ", trecho).strip(" \t:;-–—,.\n")
            if trecho:
                return trecho[:220]
    return ""


def _limpar_frase(bruto: str) -> str:
    t = re.sub(r"\s+", " ", bruto or "").strip(" \t:;-–—,.")
    t = re.split(r"[;\n]|,\s*(?:matriculado|portaria|art\.|considerando)", t, maxsplit=1, flags=re.I)[0]
    t = t.strip(" \t:;-–—,.")
    # Remove artigos / preposições iniciais comuns
    t = re.sub(
        r"^(?:o|a|ao|à|aos|às|de|do|da|dos|das|em|no|na|para|com)\s+",
        "",
        t,
        flags=re.I,
    ).strip()
    return t[:200]


def _extrair_numero_portaria(texto: str) -> str:
    m = _RE_PORTARIA_NUM.search(texto or "")
    if not m:
        m = re.search(
            r"(?:n[º°o\.º]*\s*)(\d{1,5})\s*[/\-.]\s*((?:20|19)\d{2})",
            texto or "",
            re.I,
        )
    if not m:
        return ""
    return "{0}/{1}".format(m.group(1).zfill(3), m.group(2))


def _extrair_data_portaria(texto: str) -> str:
    # Preferência: data logo após "PORTARIA" / "Gabinete" / cabeçalho
    for padrao in (
        r"portaria\b.{0,80}?",
        r"gabinete\b.{0,60}?",
        r"aos?\s+",
        r"data\s*(?:da\s*)?portaria\s*[:\-]?\s*",
    ):
        for m in re.finditer(padrao, texto or "", flags=re.I):
            datas = _datas_no_texto(texto[m.start() : m.start() + 160])
            if datas:
                return datas[0]
    datas = _datas_no_texto(texto or "")
    return datas[0] if datas else ""


def _extrair_periodo(texto: str) -> tuple[str, str]:
    # período de DD/MM/AAAA a DD/MM/AAAA
    m = re.search(
        r"(?:per[ií]odo|viagem|deslocamento|de)\s*"
        r"(?:de\s+|entre\s+|in[ií]cio\s*[:\-]?\s*)?"
        r"(\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{4}"
        r"|\d{1,2}\s+de\s+\w+\s+de\s+\d{4})"
        r"\s*(?:a|at[eé]|e|/|\-)\s*"
        r"(\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{4}"
        r"|\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
        texto or "",
        re.I,
    )
    if m:
        d1 = _datas_no_texto(m.group(1))
        d2 = _datas_no_texto(m.group(2))
        return (d1[0] if d1 else "", d2[0] if d2 else "")

    ini = _campo_apos(
        texto,
        [
            r"in[ií]cio\s*(?:da\s*)?viagem\s*[:\-]?\s*",
            r"data\s*(?:de\s*)?in[ií]cio\s*[:\-]?\s*",
        ],
        janela=40,
    )
    fim = _campo_apos(
        texto,
        [
            r"fim\s*(?:da\s*)?viagem\s*[:\-]?\s*",
            r"t[eé]rmino\s*(?:da\s*)?viagem\s*[:\-]?\s*",
            r"data\s*(?:de\s*)?(?:fim|t[eé]rmino)\s*[:\-]?\s*",
        ],
        janela=40,
    )
    d_ini = _datas_no_texto(ini)
    d_fim = _datas_no_texto(fim)
    return (d_ini[0] if d_ini else "", d_fim[0] if d_fim else "")


def _extrair_quantidade(texto: str) -> str:
    m = _RE_QTD.search(texto or "")
    if m:
        return str(int(m.group(1)))
    m = _RE_QTD_ALT.search(texto or "")
    if m:
        return str(int(m.group(1)))
    bruto = _campo_apos(
        texto,
        [r"quantidade\s*(?:de\s*)?di[aá]rias?\s*[:\-]?\s*"],
        janela=20,
    )
    m = re.search(r"(\d{1,3})", bruto)
    return str(int(m.group(1))) if m else ""


def _extrair_nome(texto: str) -> str:
    bruto = _campo_apos(
        texto,
        [
            r"nome\s*(?:do\s*servidor(?:\(a\))?|da\s*pessoa)?\s*[:\-]?\s*",
            r"concede(?:\-se)?\s*(?:di[aá]rias?\s*)?(?:ao|a|à)\s*(?:servidor(?:a)?\s*)?",
            r"autoriza(?:\-se)?\s*(?:o|a)\s*(?:servidor(?:a)?\s*)?",
            r"servidor(?:a)?\s*[:\-]?\s*",
            r"benefici[aá]rio(?:a)?\s*[:\-]?\s*",
        ],
        janela=90,
        ate=r"(?:,|\bcargo\b|\bfun[cç][aã]o\b|\bmatriculado\b|\bocupante\b|\bpara\b|\bno\s+per)",
    )
    nome = _limpar_frase(bruto)
    # Remove prefixos residuais
    nome = re.sub(
        r"^(?:o|a|ao|à|sr\.?|sra\.?|servidor(?:a)?)\s+",
        "",
        nome,
        flags=re.I,
    ).strip()
    if len(nome) >= 5 and re.search(r"[A-Za-zÁ-ú]{2,}", nome):
        return nome[:120]
    # Fallback: bloco em MAIÚSCULAS de 2+ palavras perto de "diária"
    m = re.search(
        r"(?:concede|autoriza|servidor).{0,40}?"
        r"([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]{2,}(?:\s+(?:D[AEOa]|E|DOS?|DAS?)?\s*"
        r"[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]{2,}){1,6})",
        texto or "",
    )
    return _limpar_frase(m.group(1)) if m else ""


def _extrair_cargo(texto: str) -> str:
    bruto = _campo_apos(
        texto,
        [
            r"cargo\s*[:\-]?\s*",
            r"fun[cç][aã]o\s*[:\-]?\s*",
            r"ocupante\s+do\s+cargo\s+(?:de\s+)?",
            r"no\s+cargo\s+(?:de\s+)?",
            r"exercendo\s+(?:o\s+)?cargo\s+(?:de\s+)?",
        ],
        janela=80,
        ate=r"(?:,|\.|para\b|matriculado\b|lotad|\bno\s+per|destino|motivo)",
    )
    return _limpar_frase(bruto)


def _extrair_motivo(texto: str) -> str:
    bruto = _campo_apos(
        texto,
        [
            r"motivo\s*(?:da\s*)?viagem\s*[:\-]?\s*",
            r"motivo\s*[:\-]?\s*",
            r"objetivando\s+",
            r"a\s+fim\s+de\s+",
            r"para\s+(?:participar|representar|acompanhar|realizar|tratar)\s+(?:de\s+|em\s+)?",
            r"finalidade\s*[:\-]?\s*",
        ],
        janela=200,
        ate=r"(?:destino|per[ií]odo|conced|valor|art\.|;)",
    )
    return _limpar_frase(bruto)


def _extrair_destino(texto: str) -> str:
    bruto = _campo_apos(
        texto,
        [
            r"destino\s*(?:da\s*)?viagem\s*[:\-]?\s*",
            r"destino\s*[:\-]?\s*",
            r"deslocamento\s+para\s+(?:a\s+(?:cidade|localidade)\s+de\s+)?",
            r"viajar\s+para\s+(?:a\s+(?:cidade|localidade)\s+de\s+)?",
            r"com\s+destino\s+(?:a|à|ao)\s+",
            r"(?:cidade|munic[ií]pio|localidade)\s+de\s+",
        ],
        janela=100,
        ate=r"(?:motivo|per[ií]odo|no\s+per|conced|valor|art\.|;|,?\s*no\s+per)",
    )
    return _limpar_frase(bruto)


def _extrair_valor(texto: str) -> str:
    for padrao in (
        r"valor\s+total\s*[:\-]?\s*",
        r"totalizando\s*",
        r"no\s+valor\s*(?:total\s*)?(?:de\s*)?",
        r"import[aâ]ncia\s*(?:total\s*)?(?:de\s*)?",
        r"montante\s*(?:de\s*)?",
    ):
        for m in re.finditer(padrao, texto or "", flags=re.I):
            trecho = texto[m.end() : m.end() + 40]
            mm = _RE_MOEDA.search(trecho)
            if mm:
                return "R$ {0}".format(mm.group(1))
    # Última moeda no texto costuma ser o total
    todas = list(_RE_MOEDA.finditer(texto or ""))
    if todas:
        return "R$ {0}".format(todas[-1].group(1))
    return ""


def extrair_diarias(
    texto: str,
    *,
    arquivo: str = "",
    pasta_hint: str = "",
    url: str = "",
    texto_link: str = "",
) -> dict[str, str] | None:
    """
    Extrai campos de um PDF de diárias (regra geral quando a fonte/doc é de diárias).
    Retorna None se não for diárias.

    texto_link: âncora da página (ex. "Portaria Nº 025/2023") — usada quando o
    PDF é escaneado e o OCR falha, para não perder o número na planilha.
    """
    if not parece_diarias(
        texto, pasta_hint=pasta_hint, nome_arquivo=arquivo, url=url
    ):
        return None

    reg = registro_vazio()
    reg["arquivo"] = arquivo or ""
    # Na listagem da página o âncora é a fonte da verdade do número
    # (PDF escaneado / OCR costuma errar ou vir vazio — ex.: 022 e 025).
    num_link = _extrair_numero_portaria(texto_link) or _extrair_numero_portaria(arquivo)
    num_pdf = _extrair_numero_portaria(texto)
    reg["numero_portaria"] = num_link or num_pdf
    reg["data_portaria"] = _extrair_data_portaria(texto)
    ini, fim = _extrair_periodo(texto)
    reg["inicio_viagem"] = ini
    reg["fim_viagem"] = fim
    reg["quantidade_diarias"] = _extrair_quantidade(texto)
    reg["nome"] = _extrair_nome(texto)
    reg["cargo"] = _extrair_cargo(texto)
    reg["motivo"] = _extrair_motivo(texto)
    reg["destino"] = _extrair_destino(texto)
    reg["valor_total"] = _extrair_valor(texto)
    return reg


def salvar_planilha_diarias(registros: list[dict[str, Any]], pasta: str | Path) -> Path | None:
    """Grava Diarias.csv e Diarias.xlsx na pasta. Retorna caminho do xlsx/csv."""
    if not registros:
        return None
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    csv_path = pasta / "Diarias.csv"
    xlsx_path = pasta / "Diarias.xlsx"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(ROTINOS)
        for r in registros:
            w.writerow([r.get(k, "") for k in CHAVES])

    try:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Diárias"
        ws.append(ROTINOS)
        for r in registros:
            ws.append([r.get(k, "") for k in CHAVES])
        for col in ws.columns:
            maxlen = 12
            letter = col[0].column_letter
            for cell in col:
                maxlen = max(maxlen, min(48, len(str(cell.value or ""))))
            ws.column_dimensions[letter].width = maxlen + 2
        wb.save(xlsx_path)
        return xlsx_path
    except Exception:
        return csv_path
