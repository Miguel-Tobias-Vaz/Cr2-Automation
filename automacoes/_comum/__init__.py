# -*- coding: utf-8 -*-
"""Helpers compartilhados entre automações (credenciais, IA local)."""

from __future__ import annotations

import os

from .ia_nome import nome_fraco, refinar_nome_documento
from .ia_ollama import MODELO_PADRAO, OLLAMA_URL_PADRAO, ollama_disponivel
from .ocr_multi import (
    motores_disponiveis,
    ocr_pdf,
    obter_texto_de_bytes,
    obter_texto_pdf,
)


def env_limpo(*nomes: str, padrao: str = "") -> str:
    """Primeiro valor não vazio entre nomes de variáveis de ambiente."""
    for nome in nomes:
        valor = (os.environ.get(nome) or "").strip()
        if valor:
            return valor
    return padrao


__all__ = [
    "MODELO_PADRAO",
    "OLLAMA_URL_PADRAO",
    "env_limpo",
    "motores_disponiveis",
    "nome_fraco",
    "ocr_pdf",
    "obter_texto_de_bytes",
    "obter_texto_pdf",
    "ollama_disponivel",
    "refinar_nome_documento",
]
