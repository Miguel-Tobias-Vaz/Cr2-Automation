"""Runner do arrumador/conferidor de migracao de licitacoes."""

from __future__ import annotations

from pathlib import Path

from backend.runners.base import load_module


def run(job) -> None:
    modulo = load_module(
        "arrumador_licitacoes",
        Path(__file__).with_name("arrumador_licitacoes.py"),
    )
    modulo.run(job)
