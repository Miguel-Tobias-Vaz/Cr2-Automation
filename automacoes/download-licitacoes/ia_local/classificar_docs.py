# -*- coding: utf-8 -*-
"""
Classifica anexos pelo nome (e opcionalmente pelo cabeçalho) e define
quais documentos a IA deve ler primeiro.

Prioridade (menor número = mais importante):
  DFD → ETP → Termo de Referência → Edital/Aviso → Homologação/Ratificação
  → Ata → Contrato (só para situação) → demais
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote, urlparse


def _norm(txt: str) -> str:
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


# (chave, rótulo, prioridade, padrões no nome/cabeçalho)
# prioridade 1 = lê primeiro; 99 = só se sobrar vaga
_TIPOS = [
    ("dfd", "DFD / Formalização de demanda", 1, [
        r"\bdfd\b", r"\bdod\b",
        r"documento de formalizacao de demanda",
        r"documento de formalizacao",
        r"formalizacao de demanda",
        r"formalizacao da demanda",
        r"doc\.?\s*de formalizacao",
        r"pedido de formalizacao",
    ]),
    ("etp", "ETP / Estudo técnico preliminar", 2, [
        r"\betp\b", r"estudo tecnico preliminar",
    ]),
    ("termo_referencia", "Termo de Referência", 3, [
        r"termo de referencia", r"termo_referencia",
        r"\bt\.?\s*r\.?\b", r"\btr\b", r"projeto basico",
    ]),
    # Orçamento / pesquisa: fonte forte de Valor Estimado (antes do edital genérico)
    ("orcamento", "Orçamento / Pesquisa de preços", 3, [
        r"orcamento estimado", r"orcamento", r"planilha de quantitativos",
        r"planilha orcamentaria", r"mapa de (precos|cotacao)",
        r"pesquisa de (mercado|precos)", r"cotacao de precos",
        r"mapa comparativo",
    ]),
    ("edital", "Edital", 4, [
        r"\bedital\b", r"instrumento convocatorio",
    ]),
    ("aviso", "Aviso / Extrato de edital", 5, [
        r"aviso de licitacao", r"aviso de abertura", r"\baviso\b",
        r"extrato d[eo] edital", r"extrato de aviso",
    ]),
    ("autorizacao", "Autorização", 6, [
        r"autorizacao", r"autorizacao do orgao",
    ]),
    ("homologacao", "Homologação / Ratificação", 7, [
        r"termo de homologacao", r"\bhomologacao\b", r"\bhomologo\b",
        r"termo de ratificacao", r"\bratificacao\b", r"\bratifico\b",
        r"adjudicacao e homologacao",
    ]),
    ("adjudicacao", "Adjudicação", 8, [
        r"termo de adjudicacao", r"\badjudicacao\b",
    ]),
    ("ata", "Ata", 9, [
        r"ata de registro", r"ata de sessao", r"ata de julgamento",
        r"\bata\b",
    ]),
    ("contrato", "Contrato", 10, [
        r"contrato administrativo", r"termo de contrato", r"\bcontrato\b",
    ]),
    ("dispensa_inexig", "Dispensa / Inexigibilidade", 5, [
        r"termo de dispensa", r"dispensa de licitacao", r"\bdispensa\b",
        r"inexigibilidade",
    ]),
    ("aceite_adesao", "Aceite / Adesão", 11, [
        r"termo de aceite", r"aceite de adesao", r"\badesao\b",
    ]),
]

# Tipos preferidos para a IA (fonte boa de número/objeto/situação/valores)
TIPOS_PRIORITARIOS = {
    "dfd", "etp", "termo_referencia", "orcamento", "edital", "aviso",
    "autorizacao", "homologacao", "adjudicacao", "ata", "dispensa_inexig",
}

# Sempre entram na leitura para valores (estimado/homologado), se existirem
TIPOS_OBRIGATORIOS_VALORES = (
    "dfd", "edital", "termo_referencia", "orcamento", "homologacao", "contrato",
)

# Só entram se faltar vaga ou para situação
TIPOS_COMPLEMENTARES = {"contrato", "aceite_adesao"}

# Páginas / caracteres por tipo (0 páginas = documento INTEIRO)
# Edital + DFD + TR + Termo de Homologação: leitura integral
PAGINAS_POR_TIPO = {
    "dfd": 0,
    "etp": 12,
    "termo_referencia": 0,
    "orcamento": 15,
    "edital": 0,
    "aviso": 8,
    "dispensa_inexig": 10,
    "autorizacao": 6,
    "homologacao": 0,
    "adjudicacao": 6,
    "ata": 14,
    "contrato": 12,
    "aceite_adesao": 4,
    "outro": 3,
}

CHARS_POR_TIPO = {
    "dfd": 120_000,
    "etp": 20_000,
    "termo_referencia": 140_000,
    "orcamento": 30_000,
    "edital": 160_000,
    "aviso": 12_000,
    "dispensa_inexig": 16_000,
    "autorizacao": 8_000,
    "homologacao": 80_000,
    "adjudicacao": 8_000,
    "ata": 28_000,
    "contrato": 20_000,
    "aceite_adesao": 5_000,
    "outro": 4_000,
}


def limites_leitura(tipo: str) -> tuple[int | None, int]:
    """Retorna (max_paginas|None, max_chars). None = todas as páginas."""
    t = tipo or "outro"
    pag = PAGINAS_POR_TIPO.get(t, PAGINAS_POR_TIPO["outro"])
    chars = CHARS_POR_TIPO.get(t, CHARS_POR_TIPO["outro"])
    if pag == 0:
        return None, chars
    return pag, chars


def _texto_busca(nome: str, url: str = "") -> str:
    partes = [nome or ""]
    if url:
        path = unquote(urlparse(url).path)
        partes.append(path.split("/")[-1])
    return _norm(" ".join(partes))


def classificar(nome: str, url: str = "", cabecalho: str = "") -> dict:
    """Devolve tipo, rótulo e prioridade do anexo."""
    alvo = _texto_busca(nome, url)
    if cabecalho:
        alvo = alvo + " " + _norm(cabecalho)[:800]

    melhor = None
    for chave, rotulo, prio, padroes in _TIPOS:
        for p in padroes:
            m = re.search(p, alvo)
            if m:
                cand = (m.start(), prio, chave, rotulo)
                if melhor is None or cand < melhor:
                    melhor = cand
                break
    if melhor is None:
        return {
            "tipo": "outro",
            "rotulo": "Outro documento",
            "prioridade": 99,
            "prioritario": False,
        }
    _pos, prio, chave, rotulo = melhor
    return {
        "tipo": chave,
        "rotulo": rotulo,
        "prioridade": prio,
        "prioritario": chave in TIPOS_PRIORITARIOS,
    }


def selecionar_para_leitura(
    anexos_ordenados: list[dict],
    max_pdfs: int = 8,
    so_pdf: bool = True,
) -> list[dict]:
    """
    Escolhe anexos para leitura profunda:
    1) SEMPRE inclui DFD + Edital + TR + Homologação (+ orçamento/contrato);
    2) demais prioritários com tipos distintos;
    3) complementares se couber.
    """
    if so_pdf:
        candidatos = [
            a for a in anexos_ordenados
            if (a.get("url") or a.get("caminho") or a.get("nome") or "")
            .lower().split("?")[0].endswith(".pdf")
            or str(a.get("nome") or "").lower().endswith(".pdf")
        ]
    else:
        candidatos = list(anexos_ordenados)

    prior = [a for a in candidatos if a.get("prioritario")]
    compl = [a for a in candidatos if a.get("tipo") in TIPOS_COMPLEMENTARES]
    outros = [a for a in candidatos
              if not a.get("prioritario") and a.get("tipo") not in TIPOS_COMPLEMENTARES]

    escolhidos: list[dict] = []
    vistos_url = set()
    tipos_ja = set()

    def _key(a):
        return a.get("url") or a.get("caminho") or a.get("nome")

    def _add(lista, respeitar_tipo_unico: bool = True):
        for a in lista:
            if len(escolhidos) >= max_pdfs:
                return
            key = _key(a)
            if key in vistos_url:
                continue
            tipo = a.get("tipo") or "outro"
            if respeitar_tipo_unico and tipo in tipos_ja and tipo != "outro":
                continue
            vistos_url.add(key)
            tipos_ja.add(tipo)
            escolhidos.append(a)

    # 0ª: obrigatórios para valores (DFD, Edital, …) — um de cada
    for tipo_ob in TIPOS_OBRIGATORIOS_VALORES:
        lote = [a for a in candidatos if a.get("tipo") == tipo_ob]
        _add(lote, respeitar_tipo_unico=True)

    # 1ª passagem: um de cada tipo prioritário
    _add(prior, respeitar_tipo_unico=True)
    # 2ª: complementares distintos
    if len(escolhidos) < max_pdfs:
        _add(compl, respeitar_tipo_unico=True)
    # 3ª: se ainda vazio, qualquer um
    if not escolhidos:
        _add(outros, respeitar_tipo_unico=False)
    elif len(escolhidos) < max_pdfs and not prior:
        _add(outros, respeitar_tipo_unico=False)
    # 4ª: completa vagas com mais prioritários (mesmo tipo ok)
    if len(escolhidos) < max_pdfs:
        _add(prior, respeitar_tipo_unico=False)

    return escolhidos
