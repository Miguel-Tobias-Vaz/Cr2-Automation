# -*- coding: utf-8 -*-
"""Refino de nome de documento (Extração Pro / Categorias) via Ollama."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from .ia_ollama import (
    MODELO_PADRAO,
    OLLAMA_URL_PADRAO,
    ErroOllama,
    chamar_json,
    ollama_disponivel,
)

_CACHE_DIR = Path(__file__).resolve().parent / "cache_ia_nome"
_RE_NOME_CATALOGO = re.compile(
    r"^(.+?)\s+N[º°o\.]*\s*(\d{1,5})\s*/\s*(\d{4})\s*$",
    re.I,
)


def nome_fraco(nome: str, tipos_catalogo: Iterable[str] | None = None) -> bool:
    """True se o nome das regras parece incompleto / genérico."""
    n = (nome or "").strip()
    if not n or n.lower() in ("documento", "download", "arquivo", "pdf"):
        return True
    if len(n) < 6:
        return True
    m = _RE_NOME_CATALOGO.match(n)
    if m:
        tipo = m.group(1).strip()
        if tipos_catalogo:
            cats = {t.lower() for t in tipos_catalogo}
            if tipo.lower() in cats:
                return False  # já está bom
        return False
    # Título livre longo sem número: ainda pode melhorar
    if not re.search(r"\d{1,5}\s*/\s*20\d{2}", n):
        return True
    return False


def _chave_cache(payload: dict) -> str:
    bruto = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()


def _ler_cache(chave: str) -> dict | None:
    path = _CACHE_DIR / f"{chave}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _gravar_cache(chave: str, dados: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (_CACHE_DIR / f"{chave}.json").write_text(
            json.dumps(dados, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _evidencia_ok(valor: str, fonte: str) -> bool:
    if not valor or not fonte:
        return False
    v = re.sub(r"\s+", "", valor.lower())
    f = re.sub(r"\s+", "", fonte.lower())
    return v[:40] in f or valor.lower()[:40] in fonte.lower()


def refinar_nome_documento(
    *,
    nome_regras: str,
    textos: list[str],
    tipos_catalogo: list[str],
    modelo: str = MODELO_PADRAO,
    ollama_url: str = OLLAMA_URL_PADRAO,
    forcar: bool = False,
) -> str:
    """
    Se o nome das regras for fraco, pede à IA tipo/número/ano.
    Só aceita se tipo ∈ catálogo e número aparecer no texto.
    Em falha/offline devolve nome_regras.
    """
    nome_atual = (nome_regras or "").strip() or "Documento"
    if not forcar and not nome_fraco(nome_atual, tipos_catalogo):
        return nome_atual

    if not ollama_disponivel(ollama_url):
        print("    [IA]      Ollama offline — mantendo nome das regras")
        return nome_atual

    fonte = "\n".join(t for t in textos if t).strip()
    if len(fonte) < 20:
        return nome_atual
    fonte = fonte[:6000]

    tipos = sorted({t.strip() for t in tipos_catalogo if t and t.strip()})
    lista_tipos = ", ".join(tipos[:80])

    prompt = (
        "Você nomeia documentos oficiais brasileiros (leis, decretos, portarias…).\n"
        "Responda SOMENTE JSON com as chaves:\n"
        '  {"tipo":"...", "numero":"123", "ano":"2024", "trecho":"...", "confianca":"alta|media|baixa"}\n'
        "Regras:\n"
        "- tipo DEVE ser um destes (copie exatamente): {tipos}\n"
        "- numero = só dígitos do ato; ano = 4 dígitos\n"
        "- trecho = trecho LITERAL do texto onde tipo/número aparecem\n"
        "- Se não tiver certeza, use confianca baixa e tipo vazio\n"
        "- NÃO invente número que não esteja no texto\n\n"
        "Nome sugerido pelas regras: {nome}\n\n"
        "Texto do documento / título:\n{fonte}\n"
    ).format(tipos=lista_tipos, nome=nome_atual, fonte=fonte)

    payload_cache = {
        "modelo": modelo,
        "nome": nome_atual,
        "fonte": fonte[:2000],
    }
    chave = _chave_cache(payload_cache)
    dados = _ler_cache(chave)
    if dados is None:
        try:
            print("    [IA]      refinando nome com Ollama ({0})…".format(modelo))
            sys.stdout.flush()
            dados = chamar_json(prompt, modelo=modelo, base_url=ollama_url)
            _gravar_cache(chave, dados)
        except ErroOllama as exc:
            print("    [IA]      {0} — mantendo regras".format(exc))
            return nome_atual
        except Exception as exc:
            print("    [IA]      erro: {0} — mantendo regras".format(exc))
            return nome_atual

    tipo = str(dados.get("tipo") or "").strip()
    numero = re.sub(r"\D", "", str(dados.get("numero") or ""))
    ano = str(dados.get("ano") or "").strip()
    trecho = str(dados.get("trecho") or "")
    conf = str(dados.get("confianca") or "").lower()

    if conf == "baixa" or not tipo or not numero or not re.fullmatch(r"20\d{2}|19\d{2}", ano):
        return nome_atual

    tipos_l = {t.lower(): t for t in tipos}
    if tipo.lower() not in tipos_l:
        # match parcial
        hit = next((tipos_l[k] for k in tipos_l if k in tipo.lower() or tipo.lower() in k), None)
        if not hit:
            return nome_atual
        tipo = hit
    else:
        tipo = tipos_l[tipo.lower()]

    if not _evidencia_ok(numero, fonte) and not _evidencia_ok(numero, trecho):
        return nome_atual
    if not _evidencia_ok(ano, fonte) and not _evidencia_ok(ano, trecho):
        return nome_atual

    novo = "{0} Nº{1}/{2}".format(tipo, numero.zfill(3), ano)
    if novo != nome_atual:
        print("    [IA]      {0} → {1}".format(nome_atual[:60], novo))
    return novo
