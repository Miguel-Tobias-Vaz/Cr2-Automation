# -*- coding: utf-8 -*-
"""Mapeamento de colunas e extração de campos de repasses (planilha + OCR)."""

from __future__ import annotations

import csv
import datetime
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

CAMPOS = [
    ("link", "Link"),
    ("mes_ano", "Mês e Ano"),
    ("data_repasse", "Data"),
    ("valor_previsto", "Valor Previsto (R$)"),
    ("valor_realizado", "Valor Realizado (R$)"),
    ("descricao", "Descrição"),
    ("arquivo", "Arquivo"),
]

CHAVES = [k for k, _ in CAMPOS]
ROTINOS = [r for _, r in CAMPOS]

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
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}

# Sinônimos de cabeçalho → campo interno
# Planilhas reais costumam ter "Mês" e "Ano" separados (não "Mês e Ano").
_MAPA_CABECALHO: list[tuple[str, tuple[str, ...]]] = [
    (
        "mes_ano",
        (
            "mes e ano",
            "mes/ano",
            "mes ano",
            "competencia",
            "competência",
            "periodo",
            "período",
            "referencia",
            "referência",
        ),
    ),
    (
        "mes",
        (
            "mes",
            "mês",
            "mes ref",
            "mês ref",
            "mes referencia",
            "mês referência",
        ),
    ),
    (
        "ano",
        (
            "ano",
            "ano ref",
            "ano referencia",
            "ano referência",
            "exercicio",
            "exercício",
        ),
    ),
    (
        "data_repasse",
        (
            "data do repasse",
            "data repasse",
            "dt repasse",
            "data transferencia",
            "data transferência",
            "data",
        ),
    ),
    (
        "valor_previsto",
        (
            "valor previsto",
            "previsto",
            "valor orcado",
            "valor orçado",
            "orcado",
            "orçado",
            "vl previsto",
        ),
    ),
    (
        "valor_realizado",
        (
            "valor realizado",
            "realizado",
            "valor pago",
            "pago",
            "vl realizado",
            "valor",
        ),
    ),
    (
        "descricao",
        (
            "descricao",
            "descrição",
            "historico",
            "histórico",
            "observacao",
            "observação",
            "objeto",
            "finalidade",
            "detalhe",
            "detalhes",
        ),
    ),
    (
        "link",
        (
            "link",
            "url",
            "documento",
            "arquivo",
            "anexo",
            "pdf",
            "drive",
            "hyperlink",
            "baixar",
        ),
    ),
]

_RE_DATA_NUM = re.compile(
    r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})\b"
)
_RE_DATA_EXT = re.compile(
    r"\b(\d{1,2})\s+de\s+"
    r"(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)\s+(?:de\s+)?(\d{4})\b",
    re.I,
)
_RE_MES_ANO = re.compile(
    r"\b(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro|"
    r"jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)"
    r"(?:\s+de)?[\s/\-]+(\d{4})\b",
    re.I,
)
_RE_MES_NUM_ANO = re.compile(r"\b(0?[1-9]|1[0-2])[\s/\-]((?:20|19)\d{2})\b")
# ISO / planilha invertida: 2024-07, 2024/07
_RE_ANO_MES = re.compile(r"\b((?:20|19)\d{2})[\s/\-](0?[1-9]|1[0-2])\b")
_RE_ANO = re.compile(r"\b((?:20|19)\d{2})\b")
_RE_MES_ANO_OK = re.compile(r"^\s*(0[1-9]|1[0-2])\s*/\s*((?:20|19)\d{2})\s*$")
_RE_MOEDA = re.compile(
    r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})"
)
# Preferir formato com milhar: 318.390,34 (não 1.234,56 solto / CEP / lixo de OCR)
_RE_MOEDA_MILHAR = re.compile(r"(\d{1,3}(?:\.\d{3})+,\d{2})")
_RE_VALOR_CTX = re.compile(
    r"(?:duod[eé]cimo|repasse|transfer[eê]ncia|valor(?:\s+total|\s+do\s+repasse)?"
    r"|quantia|import[aâ]ncia|recebido|pago|total)"
    r".{0,48}?(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+,\d{2}|\d{4,},\d{2})",
    re.I | re.S,
)
_RE_PREVISTO = re.compile(
    r"(?:valor\s+)?previsto\s*[:\-]?\s*(?:R\$\s*)?"
    r"(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})",
    re.I,
)
_RE_REALIZADO = re.compile(
    r"(?:valor\s+)?(?:realizado|pago)\s*[:\-]?\s*(?:R\$\s*)?"
    r"(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})",
    re.I,
)
_RE_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_RE_DRIVE_ID = re.compile(r"(?:/file/d/|/spreadsheets/d/|[?&]id=)([a-zA-Z0-9_-]{20,})")


def normalizar(txt: str) -> str:
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", str(txt))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


def registro_vazio() -> dict[str, str]:
    return {k: "" for k in CHAVES} | {"link": ""}


def mapear_cabecalhos(headers: list[str]) -> dict[str, int]:
    """Mapeia índice de coluna → campo. Primeiro match ganha (exceto 'valor'
    genérico, que só preenche valor_realizado se previsto já tiver coluna)."""
    usados: set[int] = set()
    mapa: dict[str, int] = {}
    norms = [normalizar(h) for h in headers]

    for campo, sinonimos in _MAPA_CABECALHO:
        for i, n in enumerate(norms):
            if i in usados or not n:
                continue
            for s in sinonimos:
                if n == s or n.startswith(s + " ") or s in n.split("/"):
                    # "valor" sozinho: só se ainda não houver realizado/previsto
                    if s == "valor" and n != "valor":
                        continue
                    if s == "valor" and (
                        "valor_previsto" in mapa or "valor_realizado" in mapa
                    ):
                        continue
                    if s == "data" and "repasse" not in n and "transfer" not in n:
                        # "data" genérico só se não houver match mais específico depois
                        if any("data" in x and x != n for x in norms):
                            # preferir coluna com "repasse" — tenta depois
                            if "repasse" not in n and "transfer" not in n:
                                # aceita se for a única coluna data
                                datas = [x for x in norms if x.startswith("data") or x == "data"]
                                if len(datas) > 1 and n == "data":
                                    continue
                    mapa[campo] = i
                    usados.add(i)
                    break
            if campo in mapa:
                break
    return mapa


def _fmt_data(d: int, m: int, a: int) -> str:
    if a < 100:
        a += 2000 if a < 70 else 1900
    try:
        return datetime.date(a, m, d).strftime("%d/%m/%Y")
    except ValueError:
        return ""


def parse_data(valor: Any) -> str:
    if valor is None or valor == "":
        return ""
    if isinstance(valor, datetime.datetime):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, datetime.date):
        return valor.strftime("%d/%m/%Y")
    txt = str(valor).strip()
    if not txt:
        return ""
    m = _RE_DATA_NUM.search(txt)
    if m:
        d, mo, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _fmt_data(d, mo, a)
    m = _RE_DATA_EXT.search(txt)
    if m:
        mes = _MESES.get(normalizar(m.group(2)), 0)
        if mes:
            return _fmt_data(int(m.group(1)), mes, int(m.group(3)))
    return txt


def mes_ano_valido(valor: str) -> bool:
    """True se estiver no formato MM/AAAA com mês 01–12."""
    m = _RE_MES_ANO_OK.match(str(valor or ""))
    return bool(m)


def eh_ultimo_dia_mes(data_br: str) -> bool:
    """True se a data for o último dia do mês (ex.: 30/06/2024) — típico inventado."""
    import calendar

    d = parse_data(data_br) or (data_br or "").strip()
    m = _RE_DATA_NUM.search(d)
    if not m:
        return False
    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return dia == calendar.monthrange(ano, mes)[1]
    except ValueError:
        return False


def _mes_ano_da_data(data: str) -> str:
    data = str(data or "").strip()
    if not data:
        return ""
    m = _RE_DATA_NUM.search(data)
    if m:
        mo, a = int(m.group(2)), int(m.group(3))
        if a < 100:
            a += 2000 if a < 70 else 1900
        if 1 <= mo <= 12:
            return f"{mo:02d}/{a}"
    m = _RE_DATA_EXT.search(data)
    if m:
        mes = _MESES.get(normalizar(m.group(2)), 0)
        if mes:
            return f"{mes:02d}/{int(m.group(3))}"
    partes = data.split("/")
    if len(partes) == 3:
        try:
            mo, a = int(partes[1]), int(partes[2])
            if 1 <= mo <= 12:
                return f"{mo:02d}/{a}"
        except ValueError:
            pass
    return ""


def parse_mes_ano(valor: Any, data_fallback: str = "") -> str:
    """Retorna 'MM/AAAA' ou '' (nunca só o ano / texto solto)."""
    if isinstance(valor, datetime.datetime):
        return f"{valor.month:02d}/{valor.year}"
    if isinstance(valor, datetime.date):
        return f"{valor.month:02d}/{valor.year}"

    # Excel às vezes manda o ano como número (2024 ou 2024.0)
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        n = int(valor)
        if 1900 <= n <= 2100 and float(valor) == n:
            fb = _mes_ano_da_data(data_fallback)
            return fb  # sem inventar mês 01
        if isinstance(valor, float) and 1 <= valor <= 12:
            # improvável; deixa cair no texto
            pass

    txt = str(valor or "").strip()
    if txt:
        # "2024.0" vindo de float virado string
        if re.fullmatch(r"(?:19|20)\d{2}\.0+", txt):
            fb = _mes_ano_da_data(data_fallback)
            return fb

        m = _RE_MES_ANO_OK.match(txt)
        if m:
            return f"{int(m.group(1)):02d}/{m.group(2)}"

        m = _RE_MES_ANO.search(txt)
        if m:
            mes = _MESES.get(normalizar(m.group(1)), 0)
            if mes:
                return f"{mes:02d}/{m.group(2)}"

        # Prefere MM/AAAA (07/2024) a AAAA/MM — evita confundir dia/mês em datas
        m = _RE_MES_NUM_ANO.search(txt)
        if m:
            return f"{int(m.group(1)):02d}/{m.group(2)}"

        m = _RE_ANO_MES.search(txt)
        if m:
            return f"{int(m.group(2)):02d}/{m.group(1)}"

        # Só ano no texto → usa a data se houver mês; senão vazio (não inventa 01)
        if re.fullmatch(r"\s*(?:19|20)\d{2}\s*", txt) or re.search(
            r"(?:ano|exerc[ií]cio|exercicio|compet[eê]ncia)\s*(?:de\s*)?((?:19|20)\d{2})\b",
            txt,
            re.I,
        ):
            return _mes_ano_da_data(data_fallback)

    fb = _mes_ano_da_data(data_fallback)
    if fb:
        return fb
    return ""


def juntar_mes_e_ano(
    mes: str = "",
    ano: str = "",
    mes_ano: str = "",
    data_fallback: str = "",
) -> str:
    """
    Une colunas separadas Mês + Ano (ex.: Novembro | 2024 → 11/2024).
    Se já houver mes_ano válido, mantém.
    """
    if mes_ano_valido(mes_ano):
        return parse_mes_ano(mes_ano, data_fallback)

    mes = str(mes or "").strip()
    ano = str(ano or "").strip()
    # Ano numérico do Excel
    if ano:
        ano = re.sub(r"\.0+$", "", ano)
        m_ano = _RE_ANO.search(ano)
        ano = m_ano.group(1) if m_ano else ano

    candidatos = []
    if mes and ano:
        candidatos.append(f"{mes} {ano}")
        candidatos.append(f"{mes}/{ano}")
    if mes_ano:
        candidatos.append(mes_ano)
    if mes and ano:
        # "Novembro" + "2024" já coberto; tenta número do mês
        pass
    if mes:
        candidatos.append(mes)
    if ano:
        candidatos.append(ano)

    for c in candidatos:
        out = parse_mes_ano(c, data_fallback)
        if mes_ano_valido(out):
            return out

    # Mês por nome + ano separado (quando parse não juntou)
    if mes and ano:
        nome = normalizar(mes)
        # "novembro" ou "11" ou "nov"
        num = _MESES.get(nome, 0)
        if not num:
            mnum = re.fullmatch(r"0?([1-9]|1[0-2])", mes.strip())
            if mnum:
                num = int(mnum.group(1))
        if num and re.fullmatch(r"(?:19|20)\d{2}", ano):
            return f"{num:02d}/{ano}"

    out = parse_mes_ano(mes_ano or "", data_fallback)
    return out if mes_ano_valido(out) else ""


def parse_valor(valor: Any) -> str:
    if valor is None or valor == "":
        return ""
    if isinstance(valor, (int, float)):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    txt = str(valor).strip()
    if not txt:
        return ""
    m = _RE_MOEDA.search(txt.replace(" ", ""))
    if m:
        return m.group(1)
    # número simples
    try:
        n = float(txt.replace(".", "").replace(",", ".").replace("R$", "").strip())
        return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return txt


def extrair_ano(mes_ano: str, data_repasse: str = "") -> str:
    for fonte in (mes_ano, data_repasse):
        m = _RE_ANO.search(fonte or "")
        if m:
            return m.group(1)
    return ""


def extrair_mes(mes_ano: str, data_repasse: str = "") -> str:
    ma = parse_mes_ano(mes_ano, data_repasse)
    if not mes_ano_valido(ma):
        ma = parse_mes_ano("", data_repasse)
    m = re.match(r"^(\d{2})/", ma or "")
    return m.group(1) if m else ""


def duplicar_valores(reg: dict[str, str]) -> None:
    """Se só um valor existir, copia para o outro (previsto ↔ realizado)."""
    prev = (reg.get("valor_previsto") or "").strip()
    real = (reg.get("valor_realizado") or "").strip()
    if prev and not real:
        reg["valor_realizado"] = prev
    elif real and not prev:
        reg["valor_previsto"] = real


def completar_mes_ano_e_data(reg: dict[str, str]) -> None:
    """Garante mes_ano MM/AAAA. NÃO inventa data (último dia do mês).

    A data deve vir do documento / planilha (dia do repasse). Se não houver,
    deixa data_repasse vazia. Se mes_ano faltar, tenta o nome do arquivo
    (ex.: Repasse 01-2023 - Recibo…).
    """
    data = parse_data(reg.get("data_repasse") or "") or (
        reg.get("data_repasse") or ""
    ).strip()
    if data and _RE_DATA_NUM.search(data):
        reg["data_repasse"] = parse_data(data) or data
        data = reg["data_repasse"]
    else:
        reg["data_repasse"] = ""
        data = ""

    # Colunas separadas Mês + Ano (planilha tipo Ordem|Ano|Mês|Descrição|Documento)
    mes_ano = juntar_mes_e_ano(
        mes=reg.get("mes") or "",
        ano=reg.get("ano") or "",
        mes_ano=reg.get("mes_ano") or "",
        data_fallback=data,
    )
    if not mes_ano_valido(mes_ano):
        mes_ano = mes_ano_do_arquivo(
            reg.get("arquivo") or reg.get("_nome_arquivo") or ""
        )
    if mes_ano_valido(mes_ano):
        reg["mes_ano"] = mes_ano
    else:
        reg["mes_ano"] = ""

    # Corrige ano OCR absurdo usando a competência
    if reg.get("data_repasse") and mes_ano_valido(reg.get("mes_ano") or ""):
        corr = _corrigir_ano_ocr(reg["data_repasse"], reg["mes_ano"])
        if corr:
            reg["data_repasse"] = corr


_RE_NOME_REPASSE = re.compile(
    r"(?:repasse|recibo)\s*(\d{1,2})\s*[-_/]\s*(\d{4})",
    re.I,
)


def mes_ano_do_arquivo(caminho_ou_nome: str) -> str:
    """Extrai MM/AAAA de 'Repasse 01-2023 - Recibo…' ou pasta/ano."""
    if not caminho_ou_nome:
        return ""
    p = Path(str(caminho_ou_nome))
    for fonte in (p.stem, p.name, str(caminho_ou_nome)):
        m = _RE_NOME_REPASSE.search(fonte.replace("\\", "/"))
        if m:
            out = parse_mes_ano(f"{m.group(1)}/{m.group(2)}")
            if mes_ano_valido(out):
                return out
    # pasta .../2023/Repasse 01-...
    partes = [x for x in str(caminho_ou_nome).replace("\\", "/").split("/") if x]
    ano_pasta = next((x for x in partes if re.fullmatch(r"20\d{2}", x)), "")
    m2 = re.search(r"\b(\d{1,2})\b", p.stem)
    if ano_pasta and m2:
        out = parse_mes_ano(f"{m2.group(1)}/{ano_pasta}")
        if mes_ano_valido(out):
            return out
    return ""


def _datas_no_texto(texto: str) -> list[str]:
    out = []
    for m in _RE_DATA_NUM.finditer(texto or ""):
        d = _fmt_data(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            out.append(d)
    return out


def _corrigir_ano_ocr(data: str, mes_ano_pref: str = "") -> str:
    """Corrige anos absurdos do OCR (ex.: 20/06/2624 → 20/06/2024)."""
    d = parse_data(data) or (data or "").strip()
    m = _RE_DATA_NUM.search(d)
    if not m:
        return ""
    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if ano < 100:
        ano += 2000 if ano < 70 else 1900
    # Preferência da competência
    if mes_ano_valido(mes_ano_pref):
        try:
            mo_p, ano_p = mes_ano_pref.split("/")
            ano_p = int(ano_p)
            # mesmo mês (ou ±1) e ano OCR absurdo → usa ano da competência
            if abs(mes - int(mo_p)) <= 1 and (ano < 1990 or ano > 2100 or abs(ano - ano_p) >= 50):
                ano = ano_p
            elif abs(ano - ano_p) >= 50 and 1990 <= ano_p <= 2100:
                ano = ano_p
        except ValueError:
            pass
    if ano < 1990 or ano > 2100:
        return ""
    return _fmt_data(dia, mes, ano)


def _escolher_data_repasse(texto: str, mes_ano_pref: str = "") -> str:
    """Escolhe a data do repasse; se houver competência, prefere dia no mesmo mês/ano."""
    data = ""
    for padrao in (
        r"(?:data\s+(?:do\s+)?(?:repasse|transfer[eê]ncia|documento|recibo))"
        r".{0,48}?" + _RE_DATA_NUM.pattern,
        r"(?:emitid[oa]|datad[oa]|assinad[oa]|recebid[oa]|creditad[oa])\s+em"
        r".{0,24}?" + _RE_DATA_NUM.pattern,
        r"(?:repasse|transfer[eê]ncia|recibo\s+de\s+duod[eé]cimo)"
        r".{0,60}?" + _RE_DATA_NUM.pattern,
    ):
        for m in re.finditer(padrao, texto, re.I | re.S):
            g = m.groups()
            data = _fmt_data(int(g[-3]), int(g[-2]), int(g[-1]))
            if data:
                break
        if data:
            break
    if not data:
        m = _RE_DATA_EXT.search(texto)
        if m:
            mes = _MESES.get(normalizar(m.group(2)), 0)
            if mes:
                data = _fmt_data(int(m.group(1)), mes, int(m.group(3)))

    candidatas = []
    for d in _datas_no_texto(texto):
        corr = _corrigir_ano_ocr(d, mes_ano_pref)
        if corr:
            candidatas.append(corr)
    if data:
        data = _corrigir_ano_ocr(data, mes_ano_pref) or data
        if data and data not in candidatas:
            candidatas.insert(0, data)

    ma = mes_ano_pref if mes_ano_valido(mes_ano_pref) else ""
    if ma and candidatas:
        no_mes = [d for d in candidatas if _mes_ano_da_data(d) == ma]
        if no_mes:
            return no_mes[0]
    if data:
        return _corrigir_ano_ocr(data, mes_ano_pref) or data
    return candidatas[0] if candidatas else ""


def celula_para_texto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, datetime.datetime):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, datetime.date):
        return valor.strftime("%d/%m/%Y")
    # Ano puro do Excel (2024 ou 2024.0) — mantém como texto do ano
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        n = int(valor)
        if 1900 <= n <= 2100 and float(valor) == n:
            return str(n)
    return str(valor).strip()


def achar_url_na_celula(valor: Any, hyperlink: str | None = None) -> str:
    if hyperlink and str(hyperlink).startswith("http"):
        return str(hyperlink).strip()
    txt = celula_para_texto(valor)
    if not txt:
        return ""
    if txt.startswith("http"):
        return txt.split()[0].rstrip(".,;)")
    m = _RE_URL.search(txt)
    if m:
        return m.group(0).rstrip(".,;)")
    if _RE_DRIVE_ID.search(txt) or re.fullmatch(r"[a-zA-Z0-9_-]{25,}", txt):
        return f"https://drive.google.com/file/d/{txt}/view"
    return ""


def _moeda_para_float(s: str) -> float:
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


# Exemplos/placeholders que a IA e o OCR costumam inventar (NÃO são valores reais)
_VALORES_LIXO_EXATOS = {
    "1.234,56",
    "12.345,67",
    "123.456,78",
    "1.234,00",
    "12.345,00",
    "123.456,00",
    "1234,56",
    "12345,67",
    "123456,78",
    "0,00",
    "0.00",
}


def valor_parece_lixo(s: str) -> bool:
    """True para placeholder (1.234,56), zero ou valor inválido."""
    t = re.sub(r"^\s*R\$\s*", "", str(s or "").strip(), flags=re.I)
    if not t:
        return True
    if t in _VALORES_LIXO_EXATOS:
        return True
    digitos = re.sub(r"\D", "", t)
    if digitos in ("123456", "1234567", "12345678", "123456789", "0", "00", "000"):
        return True
    # 123456… em sequência curta (placeholder clássico)
    if len(digitos) >= 4 and digitos == "".join(str(i % 10) for i in range(1, len(digitos) + 1)):
        return True
    v = _moeda_para_float(t)
    if v <= 0:
        return True
    return False


def sanitizar_valores_reg(reg: dict[str, str]) -> None:
    """Remove valores placeholder dos campos de moeda."""
    for k in ("valor_previsto", "valor_realizado"):
        if valor_parece_lixo(reg.get(k) or ""):
            reg[k] = ""


def escolher_valor_repasse(texto: str) -> str:
    """
    Escolhe o valor principal do recibo (ex.: 318.390,34), evitando lixo de OCR
    tipo 1.234,56 / CEP 68.524,00 / telefone.
    """
    if not texto:
        return ""
    # remove CEP / telefone (viram falso 68.524,00 no OCR)
    limpo = re.sub(
        r"CEP[:\s]*\d{2}\.?\d{3}[-\s./,]?\d{0,3}", " ", texto, flags=re.I
    )
    limpo = re.sub(
        r"(?:tel(?:efone)?|fone|whatsapp|celular)[^\d]{0,12}\+?\d[\d\s.\-()]{7,}",
        " ",
        limpo,
        flags=re.I,
    )
    limpo = re.sub(r"\b\d{2}\.\d{3}-\d{3}\b", " ", limpo)

    def _ok(v: str) -> bool:
        return bool(v) and not valor_parece_lixo(v) and _moeda_para_float(v) >= 1000

    # 1) perto de palavras-chave do recibo
    ctx = []
    for m in _RE_VALOR_CTX.finditer(limpo):
        if _ok(m.group(1)):
            ctx.append(m.group(1))
    if ctx:
        # Valor que aparece 2+ vezes no PDF costuma ser o correto (OCR erra uma vez)
        todos = [v for v in _RE_MOEDA_MILHAR.findall(limpo) if _ok(v)]
        cont = Counter(todos)
        repetidos = [v for v, n in cont.items() if n >= 2]
        if repetidos:
            return max(repetidos, key=lambda v: (cont[v], _moeda_para_float(v)))

        # Preferência: VALOR TOTAL / transferência > importância
        for rotulo in (
            r"valor\s+(?:total|da\s+transfer[eê]ncia|do\s+repasse)",
            r"import[aâ]ncia\s+de",
            r"trezentos|duzentos|cem\s+mil",
        ):
            preferidos = []
            for m in re.finditer(
                rotulo + r".{0,40}?(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+,\d{2})",
                limpo,
                re.I,
            ):
                if _ok(m.group(1)):
                    preferidos.append(m.group(1))
            if preferidos:
                return max(preferidos, key=_moeda_para_float)
        milhar = [v for v in ctx if _RE_MOEDA_MILHAR.fullmatch(v)]
        pool = milhar or ctx
        # Em empate, prefere o menor >= 100 mil (OCR às vezes lê 318 como 378)
        grandes = [v for v in pool if _moeda_para_float(v) >= 100000]
        if len(grandes) >= 2:
            return min(grandes, key=_moeda_para_float)
        return max(pool, key=_moeda_para_float)

    # 2) todos com milhar — prefere >= 100 mil (duodécimo típico)
    milhares = [v for v in _RE_MOEDA_MILHAR.findall(limpo) if _ok(v)]
    if milhares:
        grandes = [v for v in milhares if _moeda_para_float(v) >= 100000]
        if grandes:
            return max(grandes, key=_moeda_para_float)
        medios = [v for v in milhares if _moeda_para_float(v) >= 10000]
        if medios:
            return max(medios, key=_moeda_para_float)
        # milhar com 2+ grupos (ex.: 318.390,34) — mais confiável que 1.234,56
        duplos = [
            v for v in milhares if v.count(".") >= 2 and _moeda_para_float(v) >= 1000
        ]
        if duplos:
            return max(duplos, key=_moeda_para_float)
        bons = [v for v in milhares if _moeda_para_float(v) >= 5000]
        if bons:
            return max(bons, key=_moeda_para_float)

    # 3) com R$ explícito (evita CEP/número solto)
    com_rs = []
    for m in re.finditer(
        r"R\$\s*(\d{1,3}(?:\.\d{3})+,\d{2}|\d{4,},\d{2})", limpo, re.I
    ):
        if _ok(m.group(1)) and _moeda_para_float(m.group(1)) >= 5000:
            com_rs.append(m.group(1))
    if com_rs:
        return max(com_rs, key=_moeda_para_float)

    # 4) fallback: maior moeda >= 10 mil (nunca 1.234,56)
    vals = [
        v
        for v in _RE_MOEDA.findall(re.sub(r"\s+", "", limpo))
        if _ok(v) and _moeda_para_float(v) >= 10000
    ]
    if vals:
        return max(vals, key=_moeda_para_float)
    return ""


def extrair_do_texto(texto: str, *, nome_arquivo: str = "") -> dict[str, str]:
    """Preenche campos a partir do texto OCR/PDF."""
    reg = registro_vazio()
    ma_nome = mes_ano_do_arquivo(nome_arquivo) if nome_arquivo else ""
    if nome_arquivo:
        reg["_nome_arquivo"] = nome_arquivo
        reg["arquivo"] = nome_arquivo
    if not texto or not texto.strip():
        if mes_ano_valido(ma_nome):
            reg["mes_ano"] = ma_nome
            completar_mes_ano_e_data(reg)
        return reg

    # Competência: nome do arquivo (Repasse MM-AAAA) tem prioridade
    mes_ano = ma_nome if mes_ano_valido(ma_nome) else ""
    if not mes_ano_valido(mes_ano):
        for padrao in (
            r"(?:compet[eê]ncia|refer[eê]ncia|per[ií]odo|m[eê]s\s*/?\s*ano|m[eê]s\s+e\s+ano)"
            r"\s*[:\-]?\s*([^\n\r.]{3,40})",
            r"(?:referente\s+ao\s+m[eê]s\s+de|referente\s+a)\s*([^\n\r.]{3,40})",
        ):
            m = re.search(padrao, texto, re.I)
            if m:
                mes_ano = parse_mes_ano(m.group(1), "")
                if mes_ano_valido(mes_ano):
                    break
                mes_ano = ""
    if not mes_ano_valido(mes_ano):
        m = _RE_MES_ANO.search(texto) or _RE_MES_NUM_ANO.search(texto) or _RE_ANO_MES.search(
            texto
        )
        if m:
            mes_ano = parse_mes_ano(m.group(0), "")
    reg["mes_ano"] = mes_ano if mes_ano_valido(mes_ano) else ""

    # Data do repasse (prefere dia no mês da competência)
    reg["data_repasse"] = _escolher_data_repasse(texto, reg["mes_ano"])

    m = _RE_PREVISTO.search(texto)
    if m and _moeda_para_float(m.group(1)) >= 1000 and not valor_parece_lixo(m.group(1)):
        reg["valor_previsto"] = m.group(1)
    m = _RE_REALIZADO.search(texto)
    if m and _moeda_para_float(m.group(1)) >= 1000 and not valor_parece_lixo(m.group(1)):
        reg["valor_realizado"] = m.group(1)
    if not reg["valor_previsto"] and not reg["valor_realizado"]:
        melhor = escolher_valor_repasse(texto)
        if melhor:
            reg["valor_realizado"] = melhor
    # se previsto/realizado veio pequeno demais ou placeholder, troca pelo melhor
    for k in ("valor_previsto", "valor_realizado"):
        v = (reg.get(k) or "").strip()
        if not v:
            continue
        if valor_parece_lixo(v) or _moeda_para_float(v) < 1000:
            alt = escolher_valor_repasse(texto)
            if alt and _moeda_para_float(alt) > _moeda_para_float(v):
                reg[k] = alt
            elif valor_parece_lixo(v):
                reg[k] = ""

    # Descrição: linha com finalidade/objeto/histórico ou trecho útil
    for padrao in (
        r"(?:descri[cç][aã]o|finalidade|objeto|hist[oó]rico|assunto)\s*[:\-]\s*(.+)",
        r"(?:referente\s+a[o]?\s+)(.+)",
        r"(recibo\s+de\s+duod[eé]cimo[^\n]{0,40})",
    ):
        m = re.search(padrao, texto, re.I)
        if m:
            desc = re.sub(r"\s+", " ", m.group(1)).strip()
            desc = re.split(r"[\n\r]|R\$", desc)[0].strip(" .-;")
            if 8 <= len(desc) <= 180:
                reg["descricao"] = desc
                break
    if not reg["descricao"]:
        linhas = [
            re.sub(r"\s+", " ", ln).strip()
            for ln in texto.splitlines()
            if ln.strip() and len(ln.strip()) > 20
        ]
        for ln in linhas[:8]:
            low = normalizar(ln)
            if any(
                x in low
                for x in (
                    "repasse",
                    "transfer",
                    "convenio",
                    "convênio",
                    "fpm",
                    "fundeb",
                    "duodecimo",
                    "duodécimo",
                )
            ):
                reg["descricao"] = ln[:180]
                break

    duplicar_valores(reg)
    completar_mes_ano_e_data(reg)
    return reg


def extrair_com_ia(
    texto: str,
    *,
    nome_arquivo: str = "",
    modelo: str = "llama3.2:3b",
    ollama_url: str = "http://127.0.0.1:11434",
) -> dict[str, str]:
    """
    Usa Ollama para extrair os campos do modal Cadastrar Repasse a partir do PDF.
    Retorna registro parcial (so o que o modelo achar com confianca).
    """
    reg = registro_vazio()
    if not (texto or "").strip():
        return reg
    try:
        import sys
        from pathlib import Path

        auto = Path(__file__).resolve().parent.parent
        if str(auto) not in sys.path:
            sys.path.insert(0, str(auto))
        from _comum.ia_ollama import chamar_json
    except Exception as e:
        print(f"  [AVISO] IA indisponivel: {str(e)[:100]}")
        return reg

    trecho = re.sub(r"\s+", " ", (texto or "").strip())[:4000]
    prompt = (
        "Voce le um documento de REPASSE / transferencia / recibo de duodecimo "
        "de ente publico brasileiro.\n"
        "Extraia os campos abaixo.\n"
        "mes_ano = competencia a que o documento SE REFERE (MM/AAAA). "
        "A data de assinatura pode ser de outro mes — prefira a competencia.\n"
        "Nunca devolva so o ano em mes_ano. Se nao souber o mes, deixe vazio.\n"
        "data_repasse = DATA IMPRESSA NO DOCUMENTO (dia do repasse / transferencia / "
        "emissao / recibo). Use o dia REAL (ex.: 15/06/2024). "
        "NUNCA invente o ultimo dia do mes (30/06, 31/01 etc.) so a partir do mes/ano. "
        "Se so souber mes/ano e nao achar o dia no texto, deixe data_repasse vazia.\n"
        "VALORES: copie o valor REAL do documento (ex.: 318.390,34). "
        "NUNCA use exemplos ficticios como 1.234,56 ou 12.345,67. "
        "Se nao encontrar o valor no texto, deixe string vazia.\n"
        "Arquivo: {nome}\n"
        "Texto:\n{txt}\n\n"
        "Responda APENAS JSON:\n"
        "{{\n"
        '  "mes_ano": "MM/AAAA",\n'
        '  "data_repasse": "DD/MM/AAAA",\n'
        '  "valor_previsto": "318.390,34",\n'
        '  "valor_realizado": "318.390,34",\n'
        '  "descricao": "texto curto",\n'
        '  "confianca": 0.0\n'
        "}}\n"
        "Use string vazia se nao souber. Valores sem R$. confianca de 0 a 1."
    ).format(nome=nome_arquivo or "documento.pdf", txt=trecho)

    try:
        dados = chamar_json(
            prompt, modelo=modelo, base_url=ollama_url, temperatura=0.05, timeout=120
        )
    except Exception as e:
        print(f"  [AVISO] IA falhou: {str(e)[:120]}")
        return reg

    conf = float(dados.get("confianca") or 0)
    print(f"  [IA] confianca={conf:.2f}")

    mes_ano = str(dados.get("mes_ano") or "").strip()
    data = str(dados.get("data_repasse") or "").strip()
    prev = str(dados.get("valor_previsto") or "").strip()
    real = str(dados.get("valor_realizado") or "").strip()
    desc = str(dados.get("descricao") or "").strip()

    # Aceita campos uteis mesmo com confianca baixa (modelo às vezes manda 0.0)
    tem_util = any((mes_ano, data, prev, real, desc))
    if conf < 0.15 and not tem_util:
        return reg
    if conf < 0.15 and tem_util:
        print("  [IA] confianca baixa, mas usando campos preenchidos")

    if mes_ano:
        reg["mes_ano"] = parse_mes_ano(mes_ano, data)
        if not mes_ano_valido(reg["mes_ano"]):
            reg["mes_ano"] = ""
    if data:
        reg["data_repasse"] = parse_data(data)
    if prev:
        pv = parse_valor(prev)
        if not valor_parece_lixo(pv):
            reg["valor_previsto"] = pv
        else:
            print(f"  [IA] valor_previsto ignorado (placeholder): {pv}")
    if real:
        rv = parse_valor(real)
        if not valor_parece_lixo(rv):
            reg["valor_realizado"] = rv
        else:
            print(f"  [IA] valor_realizado ignorado (placeholder): {rv}")
    if desc:
        reg["descricao"] = normalizar_descricao(desc)

    duplicar_valores(reg)
    sanitizar_valores_reg(reg)
    completar_mes_ano_e_data(reg)
    return reg


def mesclar(base: dict[str, str], extra: dict[str, str]) -> dict[str, str]:
    """Mantém o que já veio da planilha; completa com OCR/IA.

    Se o mês/ano da planilha for só ano (inválido), deixa o OCR/IA/data sobrescrever.
    Se o valor atual for lixo de OCR (< 1000) e o novo for maior, troca.
    """
    out = dict(base)
    for k in CHAVES + ["link"]:
        if k not in out:
            out[k] = ""
        atual = (out.get(k) or "").strip()
        novo = (extra.get(k) or "").strip()
        if not novo:
            continue
        if k in ("valor_previsto", "valor_realizado") and valor_parece_lixo(novo):
            continue
        if not atual or (
            k in ("valor_previsto", "valor_realizado") and valor_parece_lixo(atual)
        ):
            out[k] = novo
            continue
        # Data inventada (último dia do mês) cede para data real do documento
        if k == "data_repasse" and eh_ultimo_dia_mes(atual) and not eh_ultimo_dia_mes(novo):
            out[k] = parse_data(novo) or novo
            continue
        if k == "mes_ano" and not mes_ano_valido(atual) and (
            mes_ano_valido(novo)
            or mes_ano_valido(parse_mes_ano(novo, out.get("data_repasse") or ""))
        ):
            out[k] = parse_mes_ano(novo, out.get("data_repasse") or "") or novo
            continue
        if k in ("valor_previsto", "valor_realizado"):
            a = _moeda_para_float(atual)
            n = _moeda_para_float(novo)
            # troca lixo (ex.: 1.234,56) pelo valor real (ex.: 318.390,34)
            if n >= 10000 and (a < 10000 or n > a * 1.5):
                out[k] = novo
            elif a < 1000 and n >= 1000:
                out[k] = novo
    sanitizar_valores_reg(out)
    if (out.get("descricao") or "").strip():
        out["descricao"] = normalizar_descricao(out["descricao"])
    completar_mes_ano_e_data(out)
    duplicar_valores(out)
    sanitizar_valores_reg(out)
    return out


def limpar_nome_arquivo(nome: str) -> str:
    """Mesma regra de download-normas / documentos: so tira invalidos do Windows."""
    nome = unicodedata.normalize("NFKC", str(nome or ""))
    for c in '<>:"/\\|?*':
        nome = nome.replace(c, "-")
    nome = re.sub(r"\s+", " ", nome).strip()
    return nome or "documento"


def nome_arquivo_final(nome_logico: str) -> str:
    """
    Nome logico: 'Repasse 07/2024 - Recibo de Duodecimo'
    Arquivo:     'Repasse 07-2024 - Recibo de Duodecimo.pdf'
    """
    base = limpar_nome_arquivo((nome_logico or "").replace("/", "-"))
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


def normalizar_descricao(desc: str) -> str:
    """Limpa descricao para planilha (espacos, quebras, lixo de OCR)."""
    if not desc:
        return ""
    s = unicodedata.normalize("NFKC", str(desc))
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = re.sub(r"\s+", " ", s).strip(" .-;|,")
    s = re.split(r"\s{2,}|\|", s)[0].strip()
    if len(s) > 180:
        s = s[:177].rstrip() + "..."
    return s


_PREPOSICOES = frozenset(
    {"de", "da", "do", "das", "dos", "e", "a", "o", "em", "no", "na", "nos", "nas", "para", "por"}
)


def titulo_descricao(desc: str) -> str:
    """
    Titulo legivel no estilo das outras automacoes:
      'recibo de duodecimo' → 'Recibo de Duodecimo'
    """
    s = normalizar_descricao(desc)
    if not s:
        return ""
    partes = []
    for i, w in enumerate(s.split(" ")):
        if not w:
            continue
        low = w.lower()
        if i > 0 and low in _PREPOSICOES:
            partes.append(low)
        elif w.isupper() and len(w) <= 5:
            # siglas curtas: FPM, FUNDEB, SUS
            partes.append(w.upper())
        else:
            partes.append(w[:1].upper() + w[1:].lower())
    return " ".join(partes)


def nome_logico_repasse(reg: dict[str, str]) -> str:
    """Ex.: 'Repasse 07/2024 - Recibo de Duodecimo'."""
    mes = extrair_mes(reg.get("mes_ano") or "", reg.get("data_repasse") or "") or "00"
    ano = extrair_ano(reg.get("mes_ano") or "", reg.get("data_repasse") or "") or "sem-ano"
    desc = titulo_descricao(reg.get("descricao") or "")
    base = f"Repasse {mes}/{ano}"
    if desc:
        base = f"{base} - {desc}"
    return base


def nome_arquivo_repasse(reg: dict[str, str]) -> str:
    """
    Mesmo padrao das normas/documentos (espacos, acentos, Titulo):
      Repasse 07-2024 - Recibo de Duodecimo.pdf
    """
    return nome_arquivo_final(nome_logico_repasse(reg))


def salvar_planilha_repasses(
    registros: list[dict[str, Any]], pasta: str | Path
) -> Path | None:
    """
    Grava Repasses.csv + Repasses.xlsx no mesmo espirito de Sessoes.xlsx:
    colunas do modal CR2 (Link, Mes e Ano, Data, Valores, Descricao, Arquivo).
    """
    if not registros:
        return None
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    csv_path = pasta / "Repasses.csv"
    xlsx_path = pasta / "Repasses.xlsx"

    rows = []
    for r in registros:
        completar_mes_ano_e_data(r)
        duplicar_valores(r)
        if (r.get("descricao") or "").strip():
            r["descricao"] = normalizar_descricao(r["descricao"])
        rows.append([r.get(k, "") for k in CHAVES])

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(ROTINOS)
        w.writerows(rows)

    try:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Repasses"
        ws.append(list(ROTINOS))
        for row in rows:
            ws.append(row)
        for col in ws.columns:
            maxlen = 14
            letter = col[0].column_letter
            for cell in col:
                maxlen = max(maxlen, min(56, len(str(cell.value or ""))))
            ws.column_dimensions[letter].width = maxlen + 2
        wb.save(xlsx_path)
        print("[INFO] Planilha: {} ({} linhas)".format(xlsx_path, len(rows)))
        print(
            "[INFO] Colunas: "
            + " | ".join(ROTINOS)
        )
        return xlsx_path
    except Exception as e:
        print("[AVISO] XLSX falhou ({}). CSV: {}".format(str(e)[:80], csv_path))
        print("[INFO] Planilha CSV: {} ({} linhas)".format(csv_path, len(rows)))
        return csv_path
