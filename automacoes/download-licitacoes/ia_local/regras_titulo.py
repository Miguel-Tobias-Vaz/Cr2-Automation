# -*- coding: utf-8 -*-
"""Siglas e formatação de número (Front)."""

from __future__ import annotations

import re
import unicodedata

from gestor_regras.config_front import SIGLAS


def normaliza(txt: str) -> str:
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


SITUACOES_FRONT = {
    "Aberto", "Anulado", "Cancelado", "Deserto", "Em andamento",
    "Finalizado", "Fracassado", "Publicada", "Revogado", "Suspenso",
}

_RE_TEM_NUMERO = re.compile(r"\d+\s*/\s*\d{4}")

# Só estes trechos finais são "categoria" (trocar pela sigla Front).
# NÃO inclui códigos de entidade (CMVX, CMXV, CPL, etc.).
_ALIASES_CATEGORIA = {
    "SRP", "RP", "RPE", "RPP", "SRPE", "SRPP", "SRPEC", "SRPPC",
    "DISP", "INEX", "TOMADA", "CONVITE", "PREGAO", "CREDENCIAMENTO",
}
_CATEGORIAS = {s.upper() for s in SIGLAS.values()} | _ALIASES_CATEGORIA


def _eh_categoria(trecho: str) -> bool:
    t = (trecho or "").strip().upper()
    if not t or not re.fullmatch(r"[A-Z]{1,8}", t):
        return False
    return t in _CATEGORIAS


def numero_sem_categoria(numero: str) -> str:
    """Remove só a categoria final (SRP, PE, RPPP…), preservando o resto."""
    bruto = (numero or "").strip()
    if not bruto:
        return ""
    partes = bruto.rsplit("-", 1)
    if len(partes) == 2 and _eh_categoria(partes[1]):
        return partes[0].rstrip()
    return bruto


def numero_com_sigla(numero: str, modalidade: str) -> str:
    """
    Mantém o número intacto; só padroniza a categoria (sigla Front).

    Ex.: 9/2023-007-CMVX-SRP + RPPP → 9/2023-007-CMVX-RPPP
         2/2023-001 + TP             → 2/2023-001-TP
         009/2023 + RPPP             → 009/2023-RPPP
    """
    bruto = (numero or "").strip()
    if not bruto:
        return ""
    if not _RE_TEM_NUMERO.search(bruto):
        return bruto

    sigla = SIGLAS.get((modalidade or "").strip(), "")
    if not sigla:
        return bruto

    partes = bruto.rsplit("-", 1)
    if len(partes) == 2 and _eh_categoria(partes[1]):
        return "%s-%s" % (partes[0], sigla)

    if bruto.upper().endswith("-" + sigla.upper()):
        return bruto
    return "%s-%s" % (bruto, sigla)


def numero_pos_confirmacao(candidato: str, numero_atual: str, modalidade: str) -> str:
    """
    Depois da IA/regras: não encurta códigos do portal (CMVX, 007…).
    Só troca/acrescenta a sigla da modalidade.
    """
    cand = (candidato or "").strip()
    atual = (numero_atual or "").strip()
    if not cand:
        return numero_com_sigla(atual, modalidade) if atual else ""
    cand_base = numero_sem_categoria(cand) or cand
    atual_base = numero_sem_categoria(atual) or atual
    if atual_base and len(atual_base) > len(cand_base):
        m = re.search(r"(?<!\d)(\d{1,10})\s*/\s*(\d{4})", cand_base)
        if m:
            seq, ano = m.group(1), m.group(2)
            for seq_try in (seq, seq.lstrip("0") or "0", seq.zfill(3)):
                if re.search(
                    r"(?<!\d)%s\s*/\s*%s\b" % (re.escape(seq_try), re.escape(ano)),
                    atual_base,
                ):
                    cand_base = atual_base
                    break
    return numero_com_sigla(cand_base, modalidade)
