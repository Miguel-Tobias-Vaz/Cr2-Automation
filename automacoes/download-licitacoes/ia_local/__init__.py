# -*- coding: utf-8 -*-
"""IA local (Ollama) + classificação/valores do protótipo de licitações."""

from .classificar_docs import (
    TIPOS_OBRIGATORIOS_VALORES,
    classificar,
    limites_leitura,
    selecionar_para_leitura,
)
from .ia_refinar import ErroIA, ollama_disponivel, refinar
from .regras_titulo import numero_com_sigla
from .regras_valores import extrair_valores_dos_docs

__all__ = [
    "ErroIA",
    "TIPOS_OBRIGATORIOS_VALORES",
    "classificar",
    "extrair_valores_dos_docs",
    "limites_leitura",
    "numero_com_sigla",
    "ollama_disponivel",
    "refinar",
    "selecionar_para_leitura",
]
