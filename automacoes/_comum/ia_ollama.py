# -*- coding: utf-8 -*-
"""Cliente mínimo Ollama (JSON) compartilhado entre automações."""

from __future__ import annotations

import json
import re
from typing import Any

import requests

OLLAMA_URL_PADRAO = "http://127.0.0.1:11434"
MODELO_PADRAO = "llama3.2:3b"


class ErroOllama(Exception):
    pass


def ollama_disponivel(base_url: str = OLLAMA_URL_PADRAO) -> bool:
    try:
        r = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _extrair_json(texto: str) -> dict[str, Any]:
    texto = (texto or "").strip()
    if not texto:
        raise ErroOllama("Resposta vazia do modelo.")
    try:
        dados = json.loads(texto)
        if isinstance(dados, dict):
            return dados
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", texto)
    if not m:
        raise ErroOllama("Modelo não devolveu JSON.")
    dados = json.loads(m.group(0))
    if not isinstance(dados, dict):
        raise ErroOllama("JSON inválido.")
    return dados


def chamar_json(
    prompt: str,
    *,
    modelo: str = MODELO_PADRAO,
    base_url: str = OLLAMA_URL_PADRAO,
    temperatura: float = 0.1,
    timeout: int = 180,
) -> dict[str, Any]:
    if not ollama_disponivel(base_url):
        raise ErroOllama(
            "Ollama offline em {0}. Abra o app ou rode: ollama serve".format(base_url)
        )
    url = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model": modelo,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": temperatura},
    }
    try:
        r = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise ErroOllama("Falha ao falar com Ollama: {0}".format(exc)) from exc
    if r.status_code == 404:
        raise ErroOllama(
            "Modelo '{0}' não encontrado. Baixe com: ollama pull {0}".format(modelo)
        )
    if r.status_code >= 400:
        raise ErroOllama("Ollama HTTP {0}: {1}".format(r.status_code, r.text[:300]))
    body = r.json()
    return _extrair_json(body.get("response") or "")
