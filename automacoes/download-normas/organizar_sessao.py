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
    Ata.pdf
    Lista de Presença.pdf
    Votações Nominais.pdf
"""

from __future__ import annotations

import datetime
import os
import re
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
    r"declara[cç][aã]o\s+de\s+atas|comiss[oõ]es|"
    r"n[aã]o\s+houve\s+sess[aã]o|declara[cç][aã]o\s*:\s*n[aã]o\s+houve",
    re.I,
)

PASTA_DECLARACOES = "Declarações"

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
}


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
        r"\b\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{4}\b|"
        r"\bn[º°o\.]",
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
    if re.search(r"vota[cç][oõ]es?\s*nomin|vota[cç][aã]o\s*nominal", n):
        return "votacoes"
    if re.search(r"lista\s*de\s*presen|presen[cç]a|frequ[eê]ncia", n):
        return "presenca"
    if re.search(r"\bpauta\b", n):
        return "pauta"
    if re.search(r"\bata\b", n):
        return "ata"
    return None


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
    """Declarações de pautas/atas, recesso, comissões — não são sessão numerada."""
    blob = "\n".join(t for t in textos if t)
    if not blob.strip():
        return False
    # Se for pauta/ata de sessão numerada, não é só declaração
    if _RE_DOC_SESSAO.search(blob):
        return False
    return bool(_RE_DECLARACAO.search(blob))


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
    Aceita com número (18ª Ordinária) ou só com evento (Sessão Especial Dia dos Pais).
    """
    blob = "\n".join(t for t in textos if t)
    if not blob.strip():
        return None
    if parece_declaracao(*textos):
        return None

    doc_tipo = None
    numero = None
    tipo_sessao = None
    evento = ""

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

    if not tipo_sessao:
        return None

    # Evento (Dia dos Pais, etc.) — útil sobretudo sem número
    for texto in textos:
        if not texto:
            continue
        evento = _extrair_evento(texto, tipo_sessao)
        if evento:
            break

    if numero is None and not evento:
        # Sem número e sem evento: só tipos “temáticos”
        if tipo_sessao not in (
            "Especial",
            "Solene",
            "Audiência Pública",
            "Tribuna Popular",
            "Preparatória",
            "Itinerante",
        ):
            return None
        if not doc_tipo:
            return None

    data, ano = _extrair_data(*textos)
    if not doc_tipo:
        nblob = _norm(blob)
        if re.search(r"\bata\b", nblob):
            doc_tipo = "ata"
        elif re.search(r"\bpauta\b", nblob):
            doc_tipo = "pauta"
        else:
            doc_tipo = "pauta"

    return {
        "numero": numero,
        "tipo": tipo_sessao,
        "evento": evento,
        "data": data,
        "ano": ano,
        "doc_tipo": doc_tipo,
        "doc_nome": _DOC_ARQUIVO.get(doc_tipo, "Documento"),
    }


def nome_pasta_sessao(meta: dict[str, Any]) -> str:
    """Ex.: Sessão Especial - Dia dos Pais - 12-08-2023"""
    base = prefixo_pasta_sessao(
        meta.get("numero"),
        meta.get("tipo") or "Ordinária",
        meta.get("evento") or "",
    )
    data = (meta.get("data") or "").strip()
    if data and data not in base:
        return "{0} - {1}".format(base, data)
    return base


def resolver_dir_sessao(pasta_ano: str | Path, meta: dict[str, Any]) -> Path:
    """
    Reusa pasta existente da mesma sessão:
      - com número: mesmo nº + tipo
      - sem número: mesmo tipo + evento
    """
    root = Path(pasta_ano)
    root.mkdir(parents=True, exist_ok=True)
    numero = meta.get("numero")
    tipo = meta.get("tipo") or "Ordinária"
    evento = (meta.get("evento") or "").strip()

    if numero is not None:
        prefix = prefixo_pasta_sessao(numero, tipo, "")
    else:
        prefix = prefixo_pasta_sessao(None, tipo, evento)

    try:
        existentes = sorted(
            p for p in root.iterdir() if p.is_dir() and p.name.startswith(prefix)
        )
    except OSError:
        existentes = []
    if existentes:
        return existentes[0]
    return root / nome_pasta_sessao(meta)


def nome_arquivo_sessao(meta: dict[str, Any], pasta: str | Path) -> str:
    """Pauta.pdf, Ata.pdf… — evita colisão com sufixo."""
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
) -> dict[str, Any] | None:
    """
    Se for documento de sessão ou declaração da fonte de sessões, devolve:
      { pasta, arquivo_logico, meta }
    senão None (fluxo normal).
    """
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
        arquivo = nome_arquivo_sessao(meta, pasta)
        return {
            "pasta": str(pasta),
            "arquivo": arquivo,
            "nome_logico": arquivo[:-4] if arquivo.lower().endswith(".pdf") else arquivo,
            "meta": meta,
        }

    # Declarações / recesso / comissões → pasta Declarações
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

    return None
