# -*- coding: utf-8 -*-
"""
Etapas do pipeline de licitações (ponto único de documentação no código).

O orquestrador continua em script.py; as regras oficiais e a IA ficam em
gestor_regras/ e ia_local/. Novas mudanças preferem esses pacotes a inchar
script.py.
"""

from __future__ import annotations

ETAPAS = (
    "coletar",      # API WP / HTML
    "baixar",       # anexos por pasta
    "ler_docs",     # texto nativo + OCR
    "regras",       # valores / situacao / numero
    "ia_local",     # Ollama opcional
    "planilhas",    # subir*.xlsx + PENDENTES
)
