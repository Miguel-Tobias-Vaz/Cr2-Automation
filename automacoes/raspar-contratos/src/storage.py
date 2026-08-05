"""Utilitários de pastas e sanitização de nomes de arquivo."""

from __future__ import annotations

import re
from pathlib import Path

import config


def slug_contrato(numero: str) -> str:
    """006/2023 → 006-2023"""
    s = (numero or "").strip()
    s = s.replace("/", "-").replace("\\", "-")
    s = re.sub(r"[^\w.\-]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "sem-numero"


def sanitizar_nome(nome: str, max_len: int | None = None) -> str:
    max_len = max_len or config.MAX_NOME_ARQUIVO
    nome = (nome or "arquivo").strip()
    for ch in config.CHARS_INVALIDOS:
        nome = nome.replace(ch, "-")
    nome = re.sub(r"\s+", " ", nome).strip(" .")
    if not nome:
        nome = "arquivo"
    if len(nome) > max_len:
        stem, dot, ext = nome.rpartition(".")
        if dot and len(ext) <= 10:
            keep = max_len - len(ext) - 1
            nome = f"{stem[:keep].rstrip()}.{ext}"
        else:
            nome = nome[:max_len].rstrip()
    return nome


def extensao_de(nome_ou_mime: str, mime: str = "") -> str:
    nome = (nome_ou_mime or "").strip()
    if "." in nome:
        ext = nome.rsplit(".", 1)[-1].lower()
        if 1 <= len(ext) <= 8 and ext.isalnum():
            return f".{ext}"
    mime = (mime or "").lower()
    mapa = {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    }
    return mapa.get(mime, ".pdf")


def nome_unico(pasta: Path, nome_base: str) -> str:
    """Evita sobrescrita: nome.pdf, nome (2).pdf, ..."""
    pasta.mkdir(parents=True, exist_ok=True)
    candidato = sanitizar_nome(nome_base)
    path = pasta / candidato
    if not path.exists():
        return candidato
    stem, dot, ext = candidato.rpartition(".")
    if not dot:
        stem, ext = candidato, ""
    else:
        ext = f".{ext}"
    n = 2
    while True:
        novo = sanitizar_nome(f"{stem} ({n}){ext}")
        if not (pasta / novo).exists():
            return novo
        n += 1


def pasta_contrato(slug: str) -> Path:
    pasta = config.CONTRATOS_DIR / slug
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def garantir_dirs() -> None:
    for d in (
        config.DADOS_DIR,
        config.CONTRATOS_DIR,
        config.LOGS_DIR,
        config.CHECKPOINT_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
