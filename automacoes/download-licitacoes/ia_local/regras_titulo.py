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


def numero_com_sigla(numero: str, modalidade: str) -> str:
    m = re.match(r"^\s*(\d{1,10})\s*/\s*(\d{4})\s*(?:-\s*[A-Za-z]+)?\s*$", numero or "")
    if not m:
        return (numero or "").strip()
    seq = m.group(1)
    base = "%s/%s" % (seq.zfill(3) if len(seq) <= 3 else seq, m.group(2))
    sigla = SIGLAS.get(modalidade, "")
    return "%s-%s" % (base, sigla) if sigla else base
