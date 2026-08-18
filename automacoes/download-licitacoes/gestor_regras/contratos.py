# -*- coding: utf-8 -*-
"""Separa contratos da pasta da licitação para Contratos/<número-modalidade>/."""

from __future__ import annotations

import os
import re
import shutil
from typing import Any

# Aditivo NÃO é contrato (regra 13 do Gestor) — fica na pasta da licitação.
_RE_ADITIVO = re.compile(
    r"termo\s*aditivo|\baditivo\b|apostilamento",
    re.I,
)
# Nome do arquivo indica contrato assinado / termo / extrato de contrato.
_RE_CONTRATO = re.compile(
    r"(?:^|[\s_\-.(])(?:"
    r"contrato\s+administrativo|"
    r"termo\s+(?:de\s+)?contrato|"
    r"extrato\s+(?:de\s+)?contrato|"
    r"contrato"
    r")(?:$|[\s_\-.)\d])",
    re.I,
)
# Portaria de designação / nomeação de fiscal (ou gestor) do contrato.
_RE_PORTARIA_FISCAL = re.compile(
    r"portaria.{0,40}(?:fiscal|gestor)|"
    r"(?:fiscal|gestor).{0,40}portaria|"
    r"designa(?:cao|ção)?\s+(?:d[oe]\s+)?fiscal|"
    r"nomea(?:cao|ção)?\s+(?:d[oe]\s+)?fiscal|"
    r"fiscal\s+d[oe]\s+contrato|"
    r"portaria.*designa",
    re.I,
)


def eh_arquivo_contrato(nome: str) -> bool:
    """True se o nome do arquivo parece um contrato (não aditivo/minuta)."""
    base = os.path.splitext(os.path.basename(nome or ""))[0]
    if not base:
        return False
    if _RE_ADITIVO.search(base):
        return False
    if re.search(r"minuta|contrato\s*social|modelo\s+de\s+contrato", base, re.I):
        return False
    return bool(_RE_CONTRATO.search(base))


def eh_arquivo_portaria_fiscal(nome: str) -> bool:
    """True se o nome parece portaria de fiscal/gestor do contrato."""
    base = os.path.splitext(os.path.basename(nome or ""))[0]
    if not base:
        return False
    if _RE_ADITIVO.search(base):
        return False
    return bool(_RE_PORTARIA_FISCAL.search(base))


def eh_arquivo_relevante_contrato(nome: str) -> bool:
    """Contrato assinado/extrato ou portaria de fiscal — o que entra na extração."""
    return eh_arquivo_contrato(nome) or eh_arquivo_portaria_fiscal(nome)


def nome_pasta_contrato(lf: dict[str, Any]) -> str:
    """
    Subpasta em Contratos/: número + modalidade (via sigla).
    Ex.: 003/2025-RPPE -> 003-2025-RPPE
    """
    numero = (lf.get("numero") or "").strip()
    modalidade = (lf.get("modalidade") or "").strip()
    if numero:
        pasta = numero.replace("/", "-")
    else:
        pasta = "SEM-NUMERO"
    # Se o número já traz sigla (ex. RPPE), basta; senão acrescenta trecho da modalidade
    if "-" in pasta and re.search(r"-[A-Za-z]{2,6}$", pasta):
        return _limpar(pasta)
    if modalidade:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", modalidade).strip("-")
        slug = slug[:40].strip("-") or "MOD"
        pasta = "%s-%s" % (pasta, slug)
    return _limpar(pasta) or "SEM-NUMERO"


def _limpar(nome: str) -> str:
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", nome)
    nome = re.sub(r"\s+", " ", nome).strip(" .")
    return nome[:120].strip(" .") or "SEM-NUMERO"


def _destino_livre(pasta: str, nome_arquivo: str) -> str:
    destino = os.path.join(pasta, nome_arquivo)
    if not os.path.exists(destino):
        return destino
    raiz, ext = os.path.splitext(nome_arquivo)
    n = 2
    while True:
        cand = os.path.join(pasta, "%s (%d)%s" % (raiz, n, ext))
        if not os.path.exists(cand):
            return cand
        n += 1


def separar_contratos_da_pasta(
    pasta_licitacao: str,
    pasta_saida: str,
    lf: dict[str, Any],
) -> list[str]:
    """
    Move arquivos de contrato e portaria de fiscal de pasta_licitacao para:
        <pasta_saida>/Contratos/<003-2025-RPPE>/

    Só cria Contratos/<licitação>/ se houver ao menos um arquivo a mover.
    Retorna lista de caminhos de destino (vazia se nada movido).
    """
    pasta_licitacao = os.path.abspath(pasta_licitacao) if pasta_licitacao else ""
    if not pasta_licitacao or not os.path.isdir(pasta_licitacao):
        return []

    sub = nome_pasta_contrato(lf)
    dest_dir = os.path.join(os.path.abspath(pasta_saida), "Contratos", sub)

    movidos: list[str] = []
    try:
        nomes = os.listdir(pasta_licitacao)
    except OSError:
        return []

    for nome in nomes:
        origem = os.path.join(pasta_licitacao, nome)
        if not os.path.isfile(origem):
            continue
        if not eh_arquivo_relevante_contrato(nome):
            continue
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except OSError:
            return movidos
        destino = _destino_livre(dest_dir, nome)
        try:
            shutil.move(origem, destino)
            movidos.append(destino)
        except OSError:
            continue
    return movidos
