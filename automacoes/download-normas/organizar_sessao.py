# -*- coding: utf-8 -*-
"""
Organização de Pautas / Atas / Presença / Votações por Sessão.

Fonte típica:
  https://camaranovatimboteua.pa.gov.br/c/atividades-legislativas/pautas-e-atas-das-sessoes/

Exemplos de título:
  ATA Nº 018 DA SESSÃO ORDINÁRIA, DE 16 DE NOVEMBRO DE 2023
  PAUTA Nº 011 DA SESSÃO EXTRAORDINÁRIA, DE 05 DE JUNHO DE 2023
  PAUTA Nº 006 DA SESSÃO SOLENE, DE 16 DE MARÇO DE 2023
  PAUTA DA SESSÃO ESPECIAL DIA DOS PAIS, DE 12 DE AGOSTO DE 2023
    → pasta: Sessão Especial - Dia dos Pais - 12-08-2023/

Tipos (filtro do portal):
  Audiência Pública, Especial, Extraordinária, Itinerante,
  Ordinária, Preparatória, Solene, Tribuna Popular
  (+ Declaração: não houve sessão → pasta Declarações)

Pasta destino (agrupa tudo da mesma sessão):
  18ª Sessão Ordinária - 16-11-2023/
    Pauta.pdf
    Ata e Certidão.pdf   ← certidão anexada ao fim da ata
    Lista de Presença.pdf
    Votações Nominais.pdf

Comissões (uma pasta só por ano; data no nome do arquivo):
  {ano}/Comissões/
    Pauta - 22-11-2023.pdf
    Ata - 08-11-2023.pdf

Listas mensais (portal agrupa por mês, sem nº de sessão):
  Lista de votação nominal – abril
    → {ano}/_Mensais/Votações Nominais - Abril.pdf
    → cópia em TODAS as pastas de sessão com data …-04-YYYY/
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

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

_TIPOS_SESSAO = (
    ("Extraordinária", re.compile(r"extra\s*ordin[aá]ria", re.I)),
    ("Audiência Pública", re.compile(r"audi[eê]ncia\s+p[uú]blica", re.I)),
    ("Tribuna Popular", re.compile(r"tribuna\s+popular", re.I)),
    ("Preparatória", re.compile(r"preparat[oó]ria", re.I)),
    ("Itinerante", re.compile(r"itinerante", re.I)),
    ("Especial", re.compile(r"especial", re.I)),
    ("Solene", re.compile(r"solene", re.I)),
    ("Ordinária", re.compile(r"ordin[aá]ria", re.I)),
)

# Estes não usam o prefixo "Sessão" no nome da pasta
_TIPOS_SEM_PREFIXO_SESSAO = frozenset({"Audiência Pública", "Tribuna Popular"})

_RE_TIPO_ALT = (
    r"extra\s*ordin[aá]ria|audi[eê]ncia\s+p[uú]blica|tribuna\s+popular|"
    r"preparat[oó]ria|itinerante|especial|solene|ordin[aá]ria"
)

_RE_FONTE_SESSOES = re.compile(
    r"pautas?\s*e\s*atas|atas?\s*das?\s*sess|pautas?\s*das?\s*sess|"
    r"sesso?es|atividades[\-_ ]legislativas|"
    r"lista\s*de\s*presen|vota[cç][oõ]es?\s*nomin|"
    r"audi[eê]ncia\s+p[uú]blica|tribuna\s+popular",
    re.I,
)

_RE_DECLARACAO = re.compile(
    r"declara[cç][aã]o\s+de\s+pautas|sem\s+pautas|recesso|"
    r"declara[cç][aã]o\s+de\s+atas|"
    r"n[aã]o\s+houve\s+sess[aã]o|declara[cç][aã]o\s*:\s*n[aã]o\s+houve",
    re.I,
)

# Reunião / sessão em conjunto das comissões permanentes
_RE_COMISSAO = re.compile(
    r"(?:reuni[aã]o|sess[aã]o).{0,80}?comiss[oõ]es|"
    r"comiss[oõ]es\s+permanentes|"
    r"em\s+conjunto\s+(?:das?\s+)?comiss",
    re.I,
)

PASTA_DECLARACOES = "Declarações"
PASTA_COMISSOES = "Comissões"
PASTA_MENSAIS = "_Mensais"
PASTA_VERIFICAR = "Verificar"

# ATA Nº 018 DA SESSÃO ORDINÁRIA, DE 16 DE NOVEMBRO DE 2023
_RE_DOC_SESSAO = re.compile(
    r"(pauta|ata|lista\s+de\s+presen[cç]a|presen[cç]a|"
    r"vota[cç][oõ]es?\s+nominais?|vota[cç][aã]o\s+nominal)"
    r"\s*(?:n[º°o\.º]*\s*)?(\d{1,4})?"
    r".{0,60}?"
    r"(?:sess[aã]o\s+)?"
    r"(" + _RE_TIPO_ALT + r")",
    re.I,
)

_RE_SESSAO_NUM_TIPO = re.compile(
    r"(?:n[º°o\.º]*\s*)?(\d{1,4})\s*[ªa]?\s*"
    r"(?:sess[aã]o\s+)?"
    r"(" + _RE_TIPO_ALT + r")",
    re.I,
)

# Salvaterra / similares: sem "sessão ordinária" no título
# PAUTA DE Nº 20 DO SEGUNDO PERÍODO DA 15ª LEGISLATURA, DE 22 DE AGOSTO DE 2023
# ATA DE ABERTURA Nº 18 DO SEGUNDO PERÍODO...
# PAUTA DO DIA 25 DE ABRIL DE 2023
_RE_NUM_DOC_LEGISLATURA = re.compile(
    r"(?:pauta|ata(?:\s+de\s+abertura)?)"
    r"(?!\s+do\s+dia)"
    r"\s*(?:de\s+)?(?:n[º°o\.º]*\s*)?(\d{1,4})\b",
    re.I,
)
_RE_SESSAO_LEGISLATURA = re.compile(
    r"\b(?:pauta|ata)\b.{0,160}?(?:per[ií]odo|legislatura)|"
    r"(?:pauta|ata)\s+do\s+dia\b|"
    r"ata\s+de\s+abertura\b",
    re.I,
)

_RE_DATA_EXT = re.compile(
    r"(?:de\s+)?(\d{1,2})\s+de\s+"
    r"(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)\s+(?:de\s+)?(\d{4})",
    re.I,
)
_RE_DATA_NUM = re.compile(
    r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})\b"
)

# Tipo do arquivo dentro da pasta da sessão
_DOC_ARQUIVO = {
    "pauta": "Pauta",
    "ata": "Ata",
    "presenca": "Lista de Presença",
    "votacoes": "Votações Nominais",
    "certidao": "Certidão",
}

_TIPOS_UNICO_POR_SESSAO = frozenset({"pauta", "ata", "presenca", "votacoes"})

# Período legislativo: Nº Período (qualquer N), por extenso ou romano.
_RE_PERIODO_NUM = re.compile(
    r"(?:\b|\s)(\d{1,2})\s*[º°o]\s*per[ií]odo(?:\s+legislativo)?",
    re.I,
)
_RE_PERIODO_ROMANO = re.compile(
    r"\b([ivxlcdm]{1,6})\s+per[ií]odo(?:\s+legislativo)?",
    re.I,
)

# Chaves já normalizadas (_norm); ordem decrescente de tamanho.
_ORDINAIS_PERIODO: tuple[tuple[str, int], ...] = (
    ("decimo terceiro", 13),
    ("decima terceira", 13),
    ("decimo segundo", 12),
    ("decima segunda", 12),
    ("decimo primeiro", 11),
    ("decima primeira", 11),
    ("decimo", 10),
    ("decima", 10),
    ("nono", 9),
    ("nona", 9),
    ("oitavo", 8),
    ("oitava", 8),
    ("setimo", 7),
    ("setima", 7),
    ("sexto", 6),
    ("sexta", 6),
    ("quinto", 5),
    ("quinta", 5),
    ("quarto", 4),
    ("quarta", 4),
    ("terceiro", 3),
    ("terceira", 3),
    ("segundo", 2),
    ("segunda", 2),
    ("primeiro", 1),
    ("primeira", 1),
)

_ROMANOS = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}

_MESES_NOME = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

# Lista mensal: "Lista de votação nominal – abril" (sem nº de sessão)
_RE_DOC_MENSAL = re.compile(
    r"(?:"
    r"lista\s+de\s+(?:presen[cç]a|vota[cç][aã]o)|"
    r"vota[cç][oõ]es?\s+nominais?|"
    r"vota[cç][aã]o\s+nominal|"
    r"lista\s+de\s+frequ[eê]ncia|"
    r"presen[cç]a|"
    r"frequ[eê]ncia"
    r").{0,80}?"
    r"(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)",
    re.I,
)

_RE_MES_NO_TEXTO = re.compile(
    r"\b(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)\b",
    re.I,
)

# Data no início (preferido) ou no fim do nome da pasta
_RE_DATA_PASTA_INI = re.compile(r"^(\d{2})-(\d{2})-(\d{4})\s*-\s*")
_RE_DATA_PASTA_FIM = re.compile(r"-\s*(\d{2})-(\d{2})-(\d{4})\s*$")


def _data_na_pasta(nome_pasta: str) -> str | None:
    """Data DD-MM-YYYY no início ou no fim do nome da pasta."""
    n = nome_pasta or ""
    m = _RE_DATA_PASTA_INI.match(n)
    if m:
        return "{0}-{1}-{2}".format(m.group(1), m.group(2), m.group(3))
    m = _RE_DATA_PASTA_FIM.search(n)
    if m:
        return "{0}-{1}-{2}".format(m.group(1), m.group(2), m.group(3))
    return None


def _nome_sem_data_pasta(nome_pasta: str) -> str:
    """Remove data DD-MM-YYYY do início/fim para comparar prefixo da sessão."""
    n = (nome_pasta or "").strip()
    n = _RE_DATA_PASTA_INI.sub("", n, count=1)
    n = _RE_DATA_PASTA_FIM.sub("", n)
    return n.strip(" -–—")


def _pasta_comeca_com_prefixo(nome_pasta: str, prefix: str) -> bool:
    if not prefix:
        return False
    return _nome_sem_data_pasta(nome_pasta).startswith(prefix)


def _pastas_mesma_data(
    pastas: list[Path],
    data: str,
    periodo: str | None,
) -> list[Path]:
    """Pastas da mesma sessão (mesma data), respeitando período legislativo."""
    if not data:
        return []
    out: list[Path] = []
    for p in pastas:
        if not _periodo_compativel(p.name, periodo):
            continue
        dp = _data_na_pasta(p.name)
        if dp == data or p.name.endswith(data) or data in p.name:
            out.append(p)
    return sorted(out, key=lambda p: p.name)

_RE_ANO_NO_TEXTO = re.compile(r"\b(20\d{2})\b")


def _norm(txt: str) -> str:
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


def parece_fonte_sessoes(
    *,
    url: str = "",
    pasta_hint: str = "",
    titulo: str = "",
) -> bool:
    """True se a fonte é de pautas/atas/sessões (regra geral)."""
    blob = " ".join([url or "", pasta_hint or "", titulo or ""])
    return bool(_RE_FONTE_SESSOES.search(blob))


def link_indica_sessao(*urls: str) -> bool:
    """
    True se alguma URL contém pauta, ata, sessão, lista de presença ou votações
    no caminho/link. Portarias e demais publicações não entram como sessão só
    pelo título do PDF.
    """
    from urllib.parse import unquote

    for raw in urls:
        if not raw or not str(raw).strip():
            continue
        u = _norm(unquote(str(raw)))
        if not u:
            continue
        if re.search(r"pautas?", u):
            return True
        if re.search(r"sess(?:ao|oes)", u):
            return True
        if re.search(r"(?:^|[/_.\-])atas?(?:[/_.\-]|$)", u):
            return True
        if re.search(r"\batas?\b", u):
            return True
        if re.search(r"lista[\-_ ]de[\-_ ]presen", u):
            return True
        if re.search(r"vota[cç][oõ]es?[\-_ ]nomin", u):
            return True
    return False


def _normalizar_tipo(bruto: str) -> str:
    n = _norm(bruto)
    for nome, rx in _TIPOS_SESSAO:
        if rx.search(n):
            return nome
    return "Ordinária"


def prefixo_pasta_sessao(
    numero: int | None,
    tipo: str,
    evento: str = "",
) -> str:
    """
    Ex.: 18ª Sessão Ordinária
         Sessão Especial - Dia dos Pais
         4ª Audiência Pública
    """
    evento = re.sub(r"\s+", " ", (evento or "").strip(" -–—,"))
    if numero is not None:
        if tipo in _TIPOS_SEM_PREFIXO_SESSAO:
            base = "{0}ª {1}".format(numero, tipo)
        else:
            base = "{0}ª Sessão {1}".format(numero, tipo)
        if evento:
            return "{0} - {1}".format(base, evento)
        return base

    if tipo in _TIPOS_SEM_PREFIXO_SESSAO:
        base = tipo
    else:
        base = "Sessão {0}".format(tipo)
    if evento:
        return "{0} - {1}".format(base, evento)
    return base


def _extrair_evento(texto: str, tipo: str) -> str:
    """Ex.: 'SESSÃO ESPECIAL DIA DOS PAIS, DE 12…' → 'Dia dos Pais'"""
    if not texto or not tipo:
        return ""
    tipo_rx = None
    for nome, rx in _TIPOS_SESSAO:
        if nome == tipo:
            tipo_rx = rx.pattern
            break
    if not tipo_rx:
        tipo_rx = re.escape(tipo)

    m = re.search(
        r"(?:sess[aã]o\s+)?" + tipo_rx + r"\s*[-–—,:]?\s*(.+)$",
        texto,
        re.I,
    )
    if not m:
        return ""
    resto = m.group(1).strip()
    resto = re.split(
        r",\s*de\s+\d|"
        r"\bde\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\b|"
        r"\brealizad[ao]s?\s+em\b|"
        r"\b\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{4}\b|"
        r"\bn[º°o\.]|"
        r"\d{1,2}\s*[º°o]?\s*per[ií]odo",
        resto,
        maxsplit=1,
        flags=re.I,
    )[0]
    resto = re.sub(r"\s+", " ", resto).strip(" -–—,:.")
    resto = re.sub(
        r"^(?:da|de|do|em|sobre|para|alusiv[oa]\s+a[o]?)\s+",
        "",
        resto,
        flags=re.I,
    ).strip()
    rn = _norm(resto)
    if rn.startswith("realizad") or re.search(r"\bper[ií]odo\b", rn):
        return ""
    if len(resto) < 3 or re.fullmatch(r"\d{1,4}", resto):
        return ""
    # Title case (DIA DOS PAIS → Dia dos Pais); mantém preposições em minúsculo
    palavras = resto[:80].split()
    pequenos = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "ao", "à"}
    out = []
    for i, w in enumerate(palavras):
        wl = w.lower()
        if i > 0 and wl in pequenos:
            out.append(wl)
        else:
            out.append(wl[:1].upper() + wl[1:] if wl else w)
    return " ".join(out)


def _tipo_documento(texto: str) -> str | None:
    n = _norm(texto)
    if not n:
        return None
    # "(SEM PAUTA)" no fim de atas não pode virar tipo=pauta
    n = re.sub(r"\(\s*sem\s+pauta[s]?\s*\)", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    if re.search(
        r"certid[aã]o\s+de\s+publica|"
        r"certid[aã]o\s+d[aeo]\s+|"
        r"certifico\s+para\s+os\s+devidos\s+fins|"
        r"\bcertid[aã]o\b",
        n,
    ):
        return "certidao"
    if re.search(
        r"vota[cç][oõ]es?\s*nomin|vota[cç][aã]o\s*nominal|lista\s*de\s*vota",
        n,
    ):
        return "votacoes"
    if re.search(r"lista\s*de\s*presen|presen[cç]a|frequ[eê]ncia", n):
        return "presenca"
    # Prefere o tipo no início do título (ATA … vs menção a pauta no meio)
    m = re.match(
        r"^(?:ata(?:\s+de\s+abertura)?|pauta)\b",
        n,
    )
    if m:
        return "ata" if m.group(0).startswith("ata") else "pauta"
    if re.search(r"\bpauta\b", n):
        return "pauta"
    if re.search(r"\bata\b", n):
        return "ata"
    return None


def _parece_sessao_formato_legislatura(*textos: str) -> bool:
    """Pauta/ata numerada por período/legislatura (ex.: Salvaterra), sem 'sessão ordinária'."""
    blob = "\n".join(t for t in textos if t)
    if not blob.strip():
        return False
    return bool(_RE_SESSAO_LEGISLATURA.search(blob))


def _extrair_numero_doc_legislatura(*textos: str) -> int | None:
    for texto in textos:
        if not texto:
            continue
        m = _RE_NUM_DOC_LEGISLATURA.search(texto)
        if m:
            return int(m.group(1))
    return None


def _rotulo_periodo(numero: int) -> str:
    """Rótulo canônico: 1º Período, 4º Período, etc."""
    return "{0}º Período".format(numero)


def _romano_para_int(s: str) -> int | None:
    s = (s or "").strip().lower()
    if not s or not re.fullmatch(r"[ivxlcdm]+", s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        val = _ROMANOS.get(ch)
        if val is None:
            return None
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total if total > 0 else None


def _numero_periodo_de_texto(texto: str) -> int | None:
    """Extrai o número do período legislativo (1, 2, 3, 4…)."""
    if not texto:
        return None
    bruto = texto
    n = _norm(texto)
    m = _RE_PERIODO_NUM.search(bruto) or _RE_PERIODO_NUM.search(n)
    if m:
        num = int(m.group(1))
        return num if num > 0 else None
    m = _RE_PERIODO_ROMANO.search(bruto) or _RE_PERIODO_ROMANO.search(n)
    if m:
        return _romano_para_int(m.group(1))
    for palavra, num in _ORDINAIS_PERIODO:
        if re.search(r"\b" + re.escape(palavra) + r"\s+per[ií]odo", n):
            return num
    return None


def _extrair_periodo_legislativo(*textos: str) -> str | None:
    """Nº Período quando o PDF/título menciona período legislativo (qualquer N)."""
    for texto in textos:
        num = _numero_periodo_de_texto(texto)
        if num is not None:
            return _rotulo_periodo(num)
    return None


def _periodo_na_pasta(nome_pasta: str) -> str | None:
    num = _numero_periodo_de_texto(nome_pasta)
    if num is not None:
        return _rotulo_periodo(num)
    return None


def _periodo_compativel(nome_pasta: str, periodo: str | None) -> bool:
    """
    Separa sessões do 1º vs 2º período legislativo.
    Com período no doc → só pasta com o mesmo período.
    Sem período no doc → só pasta sem período no nome.
    """
    na_pasta = _periodo_na_pasta(nome_pasta)
    if periodo:
        return na_pasta == periodo
    return na_pasta is None


def _pasta_verificar(pasta_ano: str | Path) -> Path:
    p = Path(pasta_ano) / PASTA_VERIFICAR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _destino_arquivo_sessao(
    pasta: str | Path,
    meta: dict[str, Any],
    *,
    pasta_ano: str | Path | None = None,
) -> tuple[Path, str]:
    """
    Pasta e nome do PDF. Se já há Pauta/Ata e o período não foi lido → Verificar/.
    Nunca apaga o que já existe.
    """
    pasta = Path(pasta)
    doc_tipo = meta.get("doc_tipo")
    doc_nome = meta.get("doc_nome") or "Documento"
    arquivo_canon = "{0}.pdf".format(doc_nome)

    if doc_tipo in _TIPOS_UNICO_POR_SESSAO and (pasta / arquivo_canon).is_file():
        periodo_doc = meta.get("periodo")
        periodo_pasta = _periodo_na_pasta(pasta.name)
        data_doc = (meta.get("data") or "").strip()
        data_pasta = _data_na_pasta(pasta.name)

        if data_doc and data_pasta and data_doc != data_pasta:
            nova = Path(pasta_ano or pasta.parent) / nome_pasta_sessao(meta)
            nova.mkdir(parents=True, exist_ok=True)
            pasta = nova
        elif periodo_doc and periodo_pasta and periodo_doc != periodo_pasta:
            nova = Path(pasta_ano or pasta.parent) / nome_pasta_sessao(meta)
            nova.mkdir(parents=True, exist_ok=True)
            pasta = nova
        elif not periodo_doc and (
            not data_doc or not data_pasta or data_doc == data_pasta
        ):
            ver = _pasta_verificar(pasta_ano or pasta.parent)
            rotulo = prefixo_pasta_sessao(
                meta.get("numero"),
                meta.get("tipo") or "Ordinária",
                meta.get("evento") or "",
            )
            desc = rotulo
            if meta.get("data"):
                desc = "{0} - {1}".format(desc, meta["data"])
            desc = "{0} - {1}".format(desc, doc_nome)
            return ver, nome_arquivo_sessao({"doc_nome": desc}, ver)
        elif data_doc and not data_pasta:
            nova = Path(pasta_ano or pasta.parent) / nome_pasta_sessao(meta)
            nova.mkdir(parents=True, exist_ok=True)
            pasta = nova

    return pasta, nome_arquivo_sessao(meta, pasta)


def _pasta_compativel_tipo(nome_pasta: str, tipo: str, evento: str = "") -> bool:
    """True se a pasta existente parece ser do mesmo tipo (e evento, se houver)."""
    n = _norm(nome_pasta)
    if not n:
        return False
    achou_tipo = False
    for nome, rx in _TIPOS_SESSAO:
        if nome != tipo:
            continue
        if rx.search(n):
            achou_tipo = True
        break
    if not achou_tipo:
        # pasta sem o tipo explícito — só aceita se o tipo pedido for genérico
        return False
    if evento and _norm(evento) not in n:
        return False
    return True


def _parse_data_extenso(m: re.Match) -> tuple[str, int] | tuple[str, None]:
    mes_txt = _norm(m.group(2)).replace("ç", "c")
    mes = _MESES.get(mes_txt)
    if not mes:
        for k, v in _MESES.items():
            if _norm(k) == mes_txt:
                mes = v
                break
    if not mes:
        return "", None
    d, a = int(m.group(1)), int(m.group(3))
    try:
        dt = datetime.date(a, mes, d)
        return dt.strftime("%d-%m-%Y"), a
    except ValueError:
        return "", None


def _extrair_data(*textos: str) -> tuple[str, int | None]:
    for texto in textos:
        if not texto:
            continue
        m = _RE_DATA_EXT.search(texto)
        if m:
            data, ano = _parse_data_extenso(m)
            if data:
                return data, ano
        m = _RE_DATA_NUM.search(texto)
        if m:
            try:
                dt = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                return dt.strftime("%d-%m-%Y"), dt.year
            except ValueError:
                continue
    return "", None


def parece_declaracao(*textos: str) -> bool:
    """Declarações de pautas/atas, recesso — não são sessão nem comissão."""
    blob = "\n".join(t for t in textos if t)
    if not blob.strip():
        return False
    if parece_comissao(*textos):
        return False
    # Se for pauta/ata de sessão numerada, não é só declaração
    if _RE_DOC_SESSAO.search(blob):
        return False
    # Ata/pauta com período/legislatura (mesmo com "(SEM PAUTA)" no título)
    if _parece_sessao_formato_legislatura(*textos):
        return False
    return bool(_RE_DECLARACAO.search(blob))


def parece_comissao(*textos: str) -> bool:
    """Reunião/sessão em conjunto das comissões permanentes."""
    blob = "\n".join(t for t in textos if t)
    if not blob.strip():
        return False
    return bool(_RE_COMISSAO.search(blob))


def parse_comissao(*textos: str, ano_fallback: int | None = None) -> dict[str, Any] | None:
    """
    Ex.: PAUTA DA REUNIÃO EM CONJUNTO DAS COMISSÕES PERMANENTES, DE 08 DE NOVEMBRO DE 2023
    Tudo vai para uma única pasta Comissões/; a data entra no nome do arquivo.
    """
    if not parece_comissao(*textos):
        return None
    blob = "\n".join(t for t in textos if t)

    doc_tipo = None
    for texto in textos:
        if texto and _tipo_documento(texto) == "certidao":
            doc_tipo = "certidao"
            break
    if not doc_tipo:
        for texto in textos:
            if not texto or len(texto) > 400:
                continue
            doc_tipo = _tipo_documento(texto)
            if doc_tipo:
                break
    if not doc_tipo:
        nblob = _norm(blob)
        if re.search(r"\bata\b", nblob):
            doc_tipo = "ata"
        elif re.search(r"\bpauta\b", nblob):
            doc_tipo = "pauta"
        else:
            doc_tipo = "pauta"

    data, ano = _extrair_data(*textos)
    ano = ano or ano_fallback

    base = _DOC_ARQUIVO.get(doc_tipo, "Documento")
    if data:
        doc_nome = "{0} - {1}".format(base, data)
    else:
        doc_nome = base

    return {
        "numero": None,
        "tipo": "Comissão",
        "evento": "",
        "data": data,
        "ano": ano,
        "doc_tipo": doc_tipo,
        "doc_nome": doc_nome,
    }


def _limpar_nome_arquivo(nome: str) -> str:
    nome = (nome or "").strip()
    for c in '<>:"/\\|?*':
        nome = nome.replace(c, "-")
    nome = re.sub(r"\s+", " ", nome).strip(" .-_")
    return nome[:140] or "Declaracao"


def nome_arquivo_declaracao(*textos: str) -> str:
    """Usa o título do post/link como nome do PDF."""
    for t in textos:
        if not t or not str(t).strip():
            continue
        if str(t).strip().lower() in ("clique aqui", "baixar", "download", "pdf"):
            continue
        base = _limpar_nome_arquivo(str(t))
        if len(base) >= 8:
            return base
    return "Declaracao"


def parse_sessao(*textos: str) -> dict[str, Any] | None:
    """
    Extrai metadados da sessão.
    Aceita com número (18ª Ordinária), só com evento (Sessão Especial Dia dos Pais)
    ou só com tipo + data (PAUTA DA SESSÃO ORDINÁRIA, DE 04 DE DEZEMBRO DE 2023).
    """
    blob = "\n".join(t for t in textos if t)
    if not blob.strip():
        return None
    if parece_comissao(*textos):
        return None
    if parece_declaracao(*textos):
        return None

    doc_tipo = None
    numero = None
    tipo_sessao = None
    evento = ""

    # Certidão no PDF/cabeçalho vence título enganoso ("Ata", "Ata (2)")
    for texto in textos:
        if texto and _tipo_documento(texto) == "certidao":
            doc_tipo = "certidao"
            break

    for texto in textos:
        if not texto:
            continue
        if not doc_tipo:
            doc_tipo = _tipo_documento(texto)
        m = _RE_DOC_SESSAO.search(texto)
        if m:
            if not doc_tipo:
                doc_tipo = _tipo_documento(m.group(1))
            if m.group(2):
                numero = int(m.group(2))
            tipo_sessao = _normalizar_tipo(m.group(3))
            break

    if tipo_sessao is None or numero is None:
        for texto in textos:
            if not texto:
                continue
            m = _RE_SESSAO_NUM_TIPO.search(texto)
            if m:
                if numero is None:
                    numero = int(m.group(1))
                if tipo_sessao is None:
                    tipo_sessao = _normalizar_tipo(m.group(2))
                break

    if tipo_sessao is None:
        for tipo_nome, rx in _TIPOS_SESSAO:
            if rx.search(blob) and (
                re.search(r"sess[aã]o", blob, re.I)
                or tipo_nome in _TIPOS_SEM_PREFIXO_SESSAO
            ):
                tipo_sessao = tipo_nome
                break

    # Formato sem "sessão ordinária": PAUTA/ATA Nº N DO Nº PERÍODO DA LEGISLATURA
    if not tipo_sessao and _parece_sessao_formato_legislatura(*textos):
        tipo_sessao = "Ordinária"
        if numero is None:
            numero = _extrair_numero_doc_legislatura(*textos)

    if not tipo_sessao:
        return None

    # Evento (Dia dos Pais, etc.) — só em título/link curtos (PDF gera falso positivo)
    for texto in textos:
        if not texto or len(texto) > 280:
            continue
        cand = _extrair_evento(texto, tipo_sessao)
        if not cand:
            continue
        cn = _norm(cand)
        if cn in ("dia", "de", "da", "do", "em", "no", "na") or re.fullmatch(r"dia\s+\d+", cn):
            continue
        if cn.startswith("realizad") or re.search(r"\b\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\b", cn):
            continue
        evento = cand
        break

    data, ano = _extrair_data(*textos)

    if numero is None and not evento:
        # Pauta/Ata de ordinária/extraordinária costuma vir SÓ com a data no título.
        if data:
            pass
        elif tipo_sessao in (
            "Especial",
            "Solene",
            "Audiência Pública",
            "Tribuna Popular",
            "Preparatória",
            "Itinerante",
        ):
            if not doc_tipo:
                return None
        else:
            return None

    if not doc_tipo:
        nblob = _norm(blob)
        if re.search(r"\bata\b", nblob):
            doc_tipo = "ata"
        elif re.search(r"\bpauta\b", nblob):
            doc_tipo = "pauta"
        else:
            doc_tipo = "pauta"

    periodo = _extrair_periodo_legislativo(*textos)

    return {
        "numero": numero,
        "tipo": tipo_sessao,
        "evento": evento,
        "data": data,
        "ano": ano,
        "periodo": periodo,
        "doc_tipo": doc_tipo,
        "doc_nome": _DOC_ARQUIVO.get(doc_tipo, "Documento"),
    }


def nome_pasta_sessao(meta: dict[str, Any]) -> str:
    """Ex.: 03-11-2023 - 13ª Sessão Ordinária - 1º Período (data primeiro = ordem cronológica)."""
    base = prefixo_pasta_sessao(
        meta.get("numero"),
        meta.get("tipo") or "Ordinária",
        meta.get("evento") or "",
    )
    partes: list[str] = []
    data = (meta.get("data") or "").strip()
    if data and data not in base:
        partes.append(data)
    partes.append(base)
    periodo = (meta.get("periodo") or "").strip()
    if periodo and _norm(periodo) not in _norm(base):
        partes.append(periodo)
    return " - ".join(partes)


def resolver_dir_sessao(pasta_ano: str | Path, meta: dict[str, Any]) -> Path:
    """
    Reusa pasta existente da mesma sessão:
      - mesma data (DD-MM-YYYY) + tipo  → une pauta s/nº com ata 766ª do mesmo dia
      - com número: mesmo nº + tipo
      - sem número: mesmo tipo + evento (+ data)
    """
    root = Path(pasta_ano)
    root.mkdir(parents=True, exist_ok=True)
    numero = meta.get("numero")
    tipo = meta.get("tipo") or "Ordinária"
    evento = (meta.get("evento") or "").strip()
    data = (meta.get("data") or "").strip()
    periodo = (meta.get("periodo") or "").strip() or None

    try:
        dirs = [p for p in root.iterdir() if p.is_dir()]
    except OSError:
        dirs = []

    def _eh_pasta_sessao(p: Path) -> bool:
        if p.name in (PASTA_MENSAIS, PASTA_DECLARACOES) or p.name.startswith("_"):
            return False
        return True

    # 1) Mesma data + tipo → mesma sessão (pauta sem nº encontra ata numerada)
    if data:
        mesmos: list[Path] = []
        for p in dirs:
            if not _eh_pasta_sessao(p):
                continue
            data_pasta = _data_na_pasta(p.name)
            if data_pasta != data:
                continue
            if not _periodo_compativel(p.name, periodo):
                continue
            if _pasta_compativel_tipo(p.name, tipo, evento):
                mesmos.append(p)
        if mesmos:
            # Prefere pasta já numerada (766ª …) e nome mais completo
            def _chave(p: Path) -> tuple:
                tem_num = 0 if re.search(r"\d+\s*ª", p.name) else 1
                return (tem_num, -len(p.name), p.name)

            escolhida = sorted(mesmos, key=_chave)[0]
            # Pauta veio antes sem nº → renomeia quando a ata traz o número
            if numero is not None and not re.search(r"\d+\s*ª", escolhida.name):
                novo = root / nome_pasta_sessao(meta)
                if escolhida.resolve() != novo.resolve() and not novo.exists():
                    try:
                        escolhida.rename(novo)
                        return novo
                    except OSError:
                        pass
            return escolhida

    # 2) Mesmo número + tipo (+ mesma data quando houver)
    if numero is not None:
        prefix = prefixo_pasta_sessao(numero, tipo, "")
        existentes = sorted(
            p
            for p in dirs
            if _eh_pasta_sessao(p)
            and _pasta_comeca_com_prefixo(p.name, prefix)
            and _periodo_compativel(p.name, periodo)
        )
        if data:
            mesmos = _pastas_mesma_data(existentes, data, periodo)
            if mesmos:
                return mesmos[0]
            return root / nome_pasta_sessao(meta)
        if existentes:
            return existentes[0]

    # 3) Sem número: tipo + evento (e data no nome)
    alvo = nome_pasta_sessao(meta)
    if (root / alvo).is_dir():
        return root / alvo

    if numero is None:
        prefix = prefixo_pasta_sessao(None, tipo, evento)
        candidatos = [
            p
            for p in dirs
            if _eh_pasta_sessao(p)
            and _pasta_comeca_com_prefixo(p.name, prefix)
            and _periodo_compativel(p.name, periodo)
        ]
        if data:
            com_data = [
                p
                for p in candidatos
                if (_data_na_pasta(p.name) == data or data in p.name)
                and _periodo_compativel(p.name, periodo)
            ]
            if com_data:
                return sorted(com_data, key=lambda p: p.name)[0]
        elif evento and candidatos:
            return sorted(candidatos, key=lambda p: p.name)[0]

    return root / alvo


def nome_arquivo_sessao(meta: dict[str, Any], pasta: str | Path) -> str:
    """Pauta.pdf, Ata.pdf… — sufixo (2) só se ainda couber na mesma pasta."""
    base = meta.get("doc_nome") or "Documento"
    pasta = Path(pasta)
    candidato = "{0}.pdf".format(base)
    if not (pasta / candidato).exists():
        return candidato
    n = 2
    while True:
        alt = "{0} ({1}).pdf".format(base, n)
        if not (pasta / alt).exists():
            return alt
        n += 1


def organizar_destino_sessao(
    *,
    pasta_base: str,
    pasta_hint: str,
    ano_fallback: int | None,
    textos: list[str],
    url_fonte: str = "",
    url_pdf: str = "",
) -> dict[str, Any] | None:
    """
    Se for documento de sessão ou declaração da fonte de sessões, devolve:
      { pasta, arquivo_logico, meta }
    senão None (fluxo normal).

    Só aplica regras de sessão quando a URL do post ou do PDF contém
    pauta, ata ou sessão — evita classificar portarias pelo texto do PDF.
    """
    if not link_indica_sessao(url_fonte, url_pdf):
        return None

    titulo = textos[1] if len(textos) > 1 else (textos[0] if textos else "")
    fonte_ok = parece_fonte_sessoes(
        url=url_fonte,
        pasta_hint=pasta_hint,
        titulo=titulo,
    )

    meta = parse_sessao(*textos)
    if meta:
        ano = meta.get("ano") or ano_fallback or "sem_ano"
        pasta_ano = os.path.join(pasta_base, pasta_hint, str(ano))
        pasta = resolver_dir_sessao(pasta_ano, meta)
        pasta, arquivo = _destino_arquivo_sessao(pasta, meta, pasta_ano=pasta_ano)
        out = {
            "pasta": str(pasta),
            "arquivo": arquivo,
            "nome_logico": arquivo[:-4] if arquivo.lower().endswith(".pdf") else arquivo,
            "meta": meta,
        }
        if PASTA_VERIFICAR in Path(pasta).parts:
            out["verificar"] = True
        return out

    # Reuniões / sessões de comissões → uma pasta só: {ano}/Comissões/
    meta_c = parse_comissao(*textos, ano_fallback=ano_fallback)
    if meta_c and (fonte_ok or parece_comissao(*textos)):
        ano = meta_c.get("ano") or ano_fallback or "sem_ano"
        pasta = Path(pasta_base) / pasta_hint / str(ano) / PASTA_COMISSOES
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = nome_arquivo_sessao(meta_c, pasta)
        return {
            "pasta": str(pasta),
            "arquivo": arquivo,
            "nome_logico": arquivo[:-4] if arquivo.lower().endswith(".pdf") else arquivo,
            "meta": meta_c,
            "comissao": True,
        }

    # Declarações / recesso → pasta Declarações
    if fonte_ok and parece_declaracao(*textos):
        data, ano_doc = _extrair_data(*textos)
        ano = ano_doc or ano_fallback or "sem_ano"
        pasta = Path(pasta_base) / pasta_hint / str(ano) / PASTA_DECLARACOES
        pasta.mkdir(parents=True, exist_ok=True)
        nome = nome_arquivo_declaracao(*textos)
        if data and data not in nome:
            nome = "{0} - {1}".format(nome, data)
        arquivo = nome_arquivo_sessao({"doc_nome": nome}, pasta)
        return {
            "pasta": str(pasta),
            "arquivo": arquivo,
            "nome_logico": arquivo[:-4] if arquivo.lower().endswith(".pdf") else arquivo,
            "meta": {
                "numero": None,
                "tipo": "Declaração",
                "data": data,
                "ano": ano_doc or ano_fallback,
                "doc_tipo": "declaracao",
                "doc_nome": nome,
            },
        }

    # Listas mensais (presença / votação nominal – abril) → _Mensais + cópia nas sessões
    org_m = organizar_destino_mensal(
        pasta_base=pasta_base,
        pasta_hint=pasta_hint,
        ano_fallback=ano_fallback,
        textos=textos,
        url_fonte=url_fonte,
    )
    if org_m:
        return org_m

    return None


def parece_doc_mensal(*textos: str) -> bool:
    """
    True para 'Lista de votação nominal – abril' / 'Lista de Presença – junho'
    (por mês, sem número/tipo de sessão).
    """
    blob = "\n".join(t for t in textos if t)
    if not blob.strip():
        return False
    if _RE_DOC_SESSAO.search(blob) or _RE_SESSAO_NUM_TIPO.search(blob):
        return False
    n = _norm(blob)
    if not re.search(
        r"lista\s+de\s+(?:presen|vota)|"
        r"vota[cç][oõ]es?\s*nomin|vota[cç][aã]o\s*nominal|"
        r"presen[cç]a|frequ[eê]ncia",
        n,
    ):
        return False
    return bool(_RE_DOC_MENSAL.search(blob) or _RE_MES_NO_TEXTO.search(blob))


def parse_doc_mensal(
    *textos: str,
    ano_fallback: int | None = None,
) -> dict[str, Any] | None:
    """Extrai mês/ano e tipo (presença ou votações) de um documento mensal."""
    if not parece_doc_mensal(*textos):
        return None
    blob = "\n".join(t for t in textos if t)
    doc_tipo = _tipo_documento(blob)
    if doc_tipo not in ("presenca", "votacoes"):
        # Título genérico com mês — assume votação se "vota", senão presença
        n = _norm(blob)
        doc_tipo = "votacoes" if re.search(r"vota", n) else "presenca"

    mes = None
    m = _RE_DOC_MENSAL.search(blob)
    mes_bruto = m.group(1) if m else None
    if not mes_bruto:
        m2 = _RE_MES_NO_TEXTO.search(blob)
        mes_bruto = m2.group(1) if m2 else None
    if mes_bruto:
        mes_txt = _norm(mes_bruto).replace("ç", "c")
        mes = _MESES.get(mes_txt) or _MESES.get(mes_bruto.lower())
        if not mes:
            for k, v in _MESES.items():
                if _norm(k) == mes_txt:
                    mes = v
                    break
    if not mes:
        return None

    ano = None
    m_ano = _RE_ANO_NO_TEXTO.search(blob)
    if m_ano:
        ano = int(m_ano.group(1))
    ano = ano or ano_fallback

    mes_nome = _MESES_NOME[mes]
    doc_base = _DOC_ARQUIVO.get(doc_tipo, "Documento")
    return {
        "mes": mes,
        "mes_nome": mes_nome,
        "ano": ano,
        "doc_tipo": doc_tipo,
        "doc_nome": "{0} - {1}".format(doc_base, mes_nome),
        "doc_nome_sessao": doc_base,
        "tipo": "Mensal",
    }


def organizar_destino_mensal(
    *,
    pasta_base: str,
    pasta_hint: str,
    ano_fallback: int | None,
    textos: list[str],
    url_fonte: str = "",
) -> dict[str, Any] | None:
    """
    Salva o canônico em {hint}/{ano}/_Mensais/Votações Nominais - Abril.pdf
    (a propagação para pastas de sessão fica a cargo de propagar_doc_mensal).
    """
    titulo = textos[1] if len(textos) > 1 else (textos[0] if textos else "")
    fonte_ok = parece_fonte_sessoes(
        url=url_fonte,
        pasta_hint=pasta_hint,
        titulo=titulo,
    )
    # Aceita se a fonte for de sessões OU o título já deixar claro que é lista mensal
    if not fonte_ok and not parece_doc_mensal(*textos):
        return None

    meta = parse_doc_mensal(*textos, ano_fallback=ano_fallback)
    if not meta:
        return None

    ano = meta.get("ano") or ano_fallback or "sem_ano"
    pasta = Path(pasta_base) / pasta_hint / str(ano) / PASTA_MENSAIS
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = nome_arquivo_sessao({"doc_nome": meta["doc_nome"]}, pasta)
    return {
        "pasta": str(pasta),
        "arquivo": arquivo,
        "nome_logico": arquivo[:-4] if arquivo.lower().endswith(".pdf") else arquivo,
        "meta": meta,
        "mensal": True,
    }


def pastas_sessao_do_mes(pasta_ano: str | Path, mes: int) -> list[Path]:
    """Pastas '… - DD-MM-YYYY' cujo mês bate com `mes` (1–12)."""
    root = Path(pasta_ano)
    if not root.is_dir():
        return []
    out: list[Path] = []
    try:
        entradas = list(root.iterdir())
    except OSError:
        return []
    for p in entradas:
        if not p.is_dir():
            continue
        if p.name in (PASTA_MENSAIS, PASTA_DECLARACOES) or p.name.startswith("_"):
            continue
        data_p = _data_na_pasta(p.name)
        if not data_p:
            continue
        try:
            if int(data_p.split("-")[1]) == int(mes):
                out.append(p)
        except (IndexError, ValueError):
            continue
    return out


def propagar_doc_mensal(
    caminho_origem: str | Path,
    meta: dict[str, Any],
    pasta_ano: str | Path,
) -> int:
    """
    Copia o PDF mensal para todas as pastas de sessão daquele mês
    como Lista de Presença.pdf / Votações Nominais.pdf.
    Não sobrescreve se já existir arquivo no destino.
    Retorna quantas cópias novas foram feitas.
    """
    mes = meta.get("mes")
    if not mes:
        return 0
    origem = Path(caminho_origem)
    if not origem.is_file():
        return 0
    nome_dest = "{0}.pdf".format(
        meta.get("doc_nome_sessao")
        or _DOC_ARQUIVO.get(meta.get("doc_tipo") or "", "Documento")
    )
    n = 0
    for pasta in pastas_sessao_do_mes(pasta_ano, int(mes)):
        dest = pasta / nome_dest
        if dest.exists():
            continue
        try:
            shutil.copy2(origem, dest)
            n += 1
        except OSError:
            continue
    return n


def propagar_todos_mensais(pasta_base: str | Path) -> int:
    """
    Percorre todas as pastas _Mensais sob pasta_base e propaga
    para as sessões do mês correspondente (útil no fim do download,
    quando sessões chegam depois das listas).
    """
    root = Path(pasta_base)
    if not root.is_dir():
        return 0
    total = 0
    try:
        pastas_mensais = [p for p in root.rglob(PASTA_MENSAIS) if p.is_dir()]
    except OSError:
        return 0
    for mensais in pastas_mensais:
        pasta_ano = mensais.parent
        ano_fb = None
        try:
            ano_fb = int(pasta_ano.name)
        except ValueError:
            ano_fb = None
        try:
            pdfs = list(mensais.glob("*.pdf"))
        except OSError:
            continue
        for pdf in pdfs:
            meta = parse_doc_mensal(pdf.stem, ano_fallback=ano_fb)
            if not meta:
                continue
            total += propagar_doc_mensal(pdf, meta, pasta_ano)
    return total


# ---------------------------------------------------------------------------
# Junção Certidão → documento principal (Ata/Pauta/…)
# ---------------------------------------------------------------------------

_RE_NOME_CERTIDAO = re.compile(
    r"^certid[aã]o(?:\s*\(\d+\))?(?:\s*-\s*\d{2}-\d{2}-\d{4})?$",
    re.I,
)


def _data_no_nome_arquivo(stem: str) -> str:
    m = re.search(r"(\d{2}-\d{2}-\d{4})\s*$", (stem or "").strip())
    return m.group(1) if m else ""


def _ler_cabecalho_pdf(caminho: str | Path, max_paginas: int = 2) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return ""
    try:
        reader = PdfReader(str(caminho))
        partes = []
        for i, page in enumerate(reader.pages):
            if i >= max_paginas:
                break
            partes.append(page.extract_text() or "")
        return "\n".join(partes)
    except Exception:
        return ""


def juntar_pdfs_principal_mais_anexo(
    path_principal: str | Path,
    path_anexo: str | Path,
) -> bool:
    """Anexa páginas do anexo ao fim do principal. Sobrescreve o principal."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        try:
            from PyPDF2 import PdfReader, PdfWriter  # type: ignore
        except ImportError:
            return False
    principal = Path(path_principal)
    anexo = Path(path_anexo)
    if not principal.is_file() or not anexo.is_file():
        return False
    if principal.resolve() == anexo.resolve():
        return False
    try:
        writer = PdfWriter()
        for page in PdfReader(str(principal)).pages:
            writer.add_page(page)
        for page in PdfReader(str(anexo)).pages:
            writer.add_page(page)
        tmp = str(principal) + ".tmp_merge.pdf"
        with open(tmp, "wb") as fh:
            writer.write(fh)
        os.replace(tmp, principal)
        return True
    except Exception:
        tmp = str(principal) + ".tmp_merge.pdf"
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def _eh_pdf_certidao_avulsa(path: Path) -> bool:
    """True para Certidão.pdf / Certidão (2).pdf — não para 'Ata e Certidão'."""
    if path.suffix.lower() != ".pdf":
        return False
    stem = (path.stem or "").strip()
    if _RE_NOME_CERTIDAO.match(stem):
        return True
    n = _norm(stem)
    if n.startswith("certidao") and " e certidao" not in n:
        return True
    return False


def _alvo_certidao_na_sessao(texto: str, pasta: Path) -> str:
    """Devolve chave doc_tipo: ata, pauta, presenca, votacoes."""
    t = _norm(texto or "")
    pares = (
        ("pauta", r"\bpauta\b"),
        ("ata", r"\bata\b"),
        ("presenca", r"lista\s+de\s+presen|presen[cç]a|frequ[eê]ncia"),
        ("votacoes", r"vota[cç]"),
    )
    for chave, rx in pares:
        if re.search(rx, t):
            return chave
    # Fallback: documento principal que existir na pasta
    for chave in ("ata", "pauta", "presenca", "votacoes"):
        if _achar_principal_sessao(pasta, chave) is not None:
            return chave
    return "ata"


def _achar_principal_sessao(pasta: Path, doc_tipo: str) -> Path | None:
    """Localiza Ata.pdf / Ata e Certidão.pdf / Pauta.pdf …"""
    base = _DOC_ARQUIVO.get(doc_tipo)
    if not base:
        return None
    base_n = _norm(base)
    candidatos: list[Path] = []
    try:
        pdfs = list(pasta.glob("*.pdf"))
    except OSError:
        return None
    for f in pdfs:
        if _eh_pdf_certidao_avulsa(f):
            continue
        stem_n = _norm(f.stem)
        if stem_n == base_n:
            candidatos.append(f)
            continue
        if stem_n.startswith(base_n + " e certidao"):
            candidatos.append(f)
            continue
        if re.match(re.escape(base_n) + r"\s*\(\d+\)$", stem_n):
            candidatos.append(f)
    if not candidatos:
        return None

    def _score(p: Path) -> tuple:
        sn = _norm(p.stem)
        # Prefere já fundido, depois nome exato, depois maior arquivo
        ja_fundido = 0 if "e certidao" in sn else 1
        exato = 0 if sn == base_n else 1
        try:
            tam = -p.stat().st_size
        except OSError:
            tam = 0
        return (ja_fundido, exato, tam, p.name.lower())

    return sorted(candidatos, key=_score)[0]


def fundir_certidoes_na_pasta_sessao(pasta: str | Path) -> int:
    """
    Em uma pasta de sessão: anexa cada Certidão.pdf ao principal citado
    (Ata / Pauta / …), remove a certidão avulsa e renomeia para
    «Ata e Certidão.pdf».
    Retorna quantas certidões foram fundidas.
    """
    root = Path(pasta)
    if not root.is_dir():
        return 0
    try:
        pdfs = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    except OSError:
        return 0

    certs = sorted(
        (p for p in pdfs if _eh_pdf_certidao_avulsa(p)),
        key=lambda p: p.name.lower(),
    )
    if not certs:
        return 0

    fundidas = 0
    for cert in certs:
        if not cert.is_file():
            continue
        cab = _ler_cabecalho_pdf(cert, max_paginas=2)
        alvo = _alvo_certidao_na_sessao(cab, root)
        principal = _achar_principal_sessao(root, alvo)
        if principal is None:
            for alt in ("ata", "pauta", "presenca", "votacoes"):
                principal = _achar_principal_sessao(root, alt)
                if principal is not None:
                    alvo = alt
                    break
        if principal is None:
            continue
        if not juntar_pdfs_principal_mais_anexo(principal, cert):
            continue
        try:
            cert.unlink()
        except OSError:
            pass

        base = _DOC_ARQUIVO.get(alvo, "Documento")
        destino = root / "{0} e Certidão.pdf".format(base)
        if principal.resolve() != destino.resolve():
            if not destino.exists():
                try:
                    principal.rename(destino)
                    principal = destino
                except OSError:
                    pass
            elif destino.resolve() != principal.resolve():
                # Já existe fundido: anexa o que restou do principal e remove
                if juntar_pdfs_principal_mais_anexo(destino, principal):
                    try:
                        principal.unlink()
                    except OSError:
                        pass
                    principal = destino
        fundidas += 1
    return fundidas


def _achar_principal_comissao(
    pasta: Path,
    doc_tipo: str,
    data: str,
) -> Path | None:
    """Localiza 'Pauta - 22-11-2023.pdf' / 'Ata e Certidão - 22-11-2023.pdf'."""
    base = _DOC_ARQUIVO.get(doc_tipo)
    if not base:
        return None
    base_n = _norm(base)
    data = (data or "").strip()
    candidatos: list[Path] = []
    try:
        pdfs = list(pasta.glob("*.pdf"))
    except OSError:
        return None
    for f in pdfs:
        if _eh_pdf_certidao_avulsa(f):
            continue
        if data and _data_no_nome_arquivo(f.stem) != data:
            continue
        stem_n = _norm(f.stem)
        if stem_n == base_n or stem_n.startswith(base_n + " -") or stem_n.startswith(
            base_n + " e certidao"
        ):
            candidatos.append(f)
    if not candidatos:
        return None

    def _score(p: Path) -> tuple:
        sn = _norm(p.stem)
        ja = 0 if "e certidao" in sn else 1
        try:
            tam = -p.stat().st_size
        except OSError:
            tam = 0
        return (ja, tam, p.name.lower())

    return sorted(candidatos, key=_score)[0]


def fundir_certidoes_na_pasta_comissoes(pasta: str | Path) -> int:
    """
    Pasta única Comissões/: junta 'Certidão - DD-MM-YYYY' em
    'Ata - DD-MM-YYYY' → 'Ata e Certidão - DD-MM-YYYY.pdf'.
    """
    root = Path(pasta)
    if not root.is_dir():
        return 0
    try:
        pdfs = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    except OSError:
        return 0

    certs = sorted(
        (p for p in pdfs if _eh_pdf_certidao_avulsa(p)),
        key=lambda p: p.name.lower(),
    )
    if not certs:
        return 0

    fundidas = 0
    for cert in certs:
        if not cert.is_file():
            continue
        cab = _ler_cabecalho_pdf(cert, max_paginas=2)
        data = _data_no_nome_arquivo(cert.stem)
        if not data:
            data, _ = _extrair_data(cab)
        alvo = _alvo_certidao_na_sessao(cab, root)
        principal = _achar_principal_comissao(root, alvo, data)
        if principal is None:
            for alt in ("ata", "pauta", "presenca", "votacoes"):
                principal = _achar_principal_comissao(root, alt, data)
                if principal is not None:
                    alvo = alt
                    break
        if principal is None:
            continue
        if not juntar_pdfs_principal_mais_anexo(principal, cert):
            continue
        try:
            cert.unlink()
        except OSError:
            pass

        base = _DOC_ARQUIVO.get(alvo, "Documento")
        data_final = data or _data_no_nome_arquivo(principal.stem)
        if data_final:
            destino_nome = "{0} e Certidão - {1}.pdf".format(base, data_final)
        else:
            destino_nome = "{0} e Certidão.pdf".format(base)
        destino = root / destino_nome
        if principal.resolve() != destino.resolve():
            if not destino.exists():
                try:
                    principal.rename(destino)
                except OSError:
                    pass
            elif destino.resolve() != principal.resolve():
                if juntar_pdfs_principal_mais_anexo(destino, principal):
                    try:
                        principal.unlink()
                    except OSError:
                        pass
        fundidas += 1
    return fundidas


def fundir_certidoes_em_sessoes(pasta_base: str | Path) -> int:
    """Percorre pastas de sessão (e Comissões/) sob pasta_base e funde certidões."""
    root = Path(pasta_base)
    if not root.is_dir():
        return 0
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in (PASTA_MENSAIS,) and not d.startswith(".")
            ]
            p = Path(dirpath)
            if p.name in (PASTA_MENSAIS, PASTA_DECLARACOES):
                continue
            if p.name == PASTA_COMISSOES or _norm(p.name) in ("comissoes", "comissao"):
                n = fundir_certidoes_na_pasta_comissoes(p)
                if n:
                    total += n
                    print(
                        "  [JUNÇÃO]  Comissões: {0} certidão(ões) → documento principal".format(
                            n
                        )
                    )
                continue
            if not _data_na_pasta(p.name):
                continue
            if not any(f.lower().endswith(".pdf") for f in filenames):
                continue
            n = fundir_certidoes_na_pasta_sessao(p)
            if n:
                total += n
                print(
                    "  [JUNÇÃO]  {0}: {1} certidão(ões) → documento principal".format(
                        p.name[:60], n
                    )
                )
    except OSError:
        return total
    return total
