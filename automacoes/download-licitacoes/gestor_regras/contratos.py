# -*- coding: utf-8 -*-
"""Separa contratos e termos aditivos das pastas de licitação.

  Contratos/<licitação>/  — contrato assinado, extrato, portaria de fiscal
  Aditivos/<licitação>/   — termo aditivo / apostilamento
"""

from __future__ import annotations

import os
import re
import shutil
from typing import Any

# Aditivo NÃO é contrato (regra 13 do Gestor) — vai para Aditivos/.
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
    r"portaria.*designa|"
    # Cumaru do Norte: "Termo Fiscal 236-2023.pdf" / "Termo de Designação.pdf"
    r"termo\s+(?:de\s+)?(?:fiscal|designa)|"
    r"termo\s+fiscal|"
    r"\bfiscal\b(?=\s*[\d\-_.]|$)",
    re.I,
)

PASTA_CONTRATOS = "Contratos"
PASTA_ADITIVOS = "Aditivos"


def eh_arquivo_aditivo(nome: str) -> bool:
    """True se o nome parece termo aditivo / apostilamento."""
    base = os.path.splitext(os.path.basename(nome or ""))[0]
    if not base:
        return False
    return bool(_RE_ADITIVO.search(base))


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
    Subpasta em Contratos/ e Aditivos/: espelha a pasta da licitação (001 - nome…).
    """
    pasta_nome = (lf.get("_pasta_nome") or "").strip()
    if pasta_nome:
        return _limpar(pasta_nome)

    ordem = lf.get("_ordem")
    titulo = (lf.get("_titulo") or "").strip()
    if ordem and titulo:
        return _limpar("%03d - %s" % (int(ordem), titulo))

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


def _eh_artefato_temporario(nome: str) -> bool:
    nlow = (nome or "").lower()
    return (
        nlow.endswith(".ocr.pdf")
        or nlow.endswith(".ocr.txt")
        or nlow.endswith(".ocr")
        or ".ocr." in nlow
        or nlow.endswith(".part")
    )


def _mover_filtrados(
    pasta_licitacao: str,
    dest_dir: str,
    aceita,
) -> list[str]:
    """Move arquivos da pasta da licitação que passam em `aceita(nome)`."""
    pasta_licitacao = os.path.abspath(pasta_licitacao) if pasta_licitacao else ""
    if not pasta_licitacao or not os.path.isdir(pasta_licitacao):
        return []

    movidos: list[str] = []
    try:
        nomes = os.listdir(pasta_licitacao)
    except OSError:
        return []

    for nome in nomes:
        origem = os.path.join(pasta_licitacao, nome)
        if not os.path.isfile(origem):
            continue
        if _eh_artefato_temporario(nome):
            continue
        if not aceita(nome):
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
    sub = nome_pasta_contrato(lf)
    dest_dir = os.path.join(os.path.abspath(pasta_saida), PASTA_CONTRATOS, sub)
    return _mover_filtrados(pasta_licitacao, dest_dir, eh_arquivo_relevante_contrato)


def separar_aditivos_da_pasta(
    pasta_licitacao: str,
    pasta_saida: str,
    lf: dict[str, Any],
) -> list[str]:
    """
    Move termos aditivos / apostilamentos para:
        <pasta_saida>/Aditivos/<mesma pasta da licitação>/

    Só cria a subpasta se houver ao menos um arquivo. Retorna destinos.
    """
    sub = nome_pasta_contrato(lf)
    dest_dir = os.path.join(os.path.abspath(pasta_saida), PASTA_ADITIVOS, sub)
    return _mover_filtrados(pasta_licitacao, dest_dir, eh_arquivo_aditivo)
