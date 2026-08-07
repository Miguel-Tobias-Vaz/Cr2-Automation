from __future__ import annotations

import sys
from pathlib import Path

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs


def run(job) -> None:
    cfg = job.config
    url = (cfg.get("url_planilha") or cfg.get("urls") or "").strip()
    # aceita uma URL (primeira linha se colarem várias)
    url = next(
        (ln.strip() for ln in url.splitlines() if ln.strip()),
        "",
    )
    if not url:
        raise ValueError(
            "Informe o link da planilha (Google Sheets/Drive) ou o caminho de um .xlsx."
        )

    pasta = cfg.get("pasta_base") or r"C:\Downloads"
    anos_raw = (cfg.get("anos") or "").strip()
    # Aceita: 2023 | 2023,2024 | 2023;2024 | 2023 2024
    anos_filtro = []
    if anos_raw:
        import re as _re

        anos_filtro = _re.findall(r"(?:19|20)\d{2}", anos_raw)
        # remove duplicados preservando ordem
        anos_filtro = list(dict.fromkeys(anos_filtro))
    usar_ocr = bool(cfg.get("usar_ocr", True))
    refinar_ia = bool(cfg.get("refinar_ia", True))
    motor_ocr = (cfg.get("motor_ocr") or "auto").strip().lower() or "auto"
    if motor_ocr in ("docling", "surya", "easyocr"):
        motor_ocr = "auto"

    # Evita cache de job anterior (extrair_repasses / download_repasses)
    for key in list(sys.modules):
        if "repasses" in key or key.endswith("extrair_repasses"):
            sys.modules.pop(key, None)

    mod = load_module("download_repasses", SCRIPTS["repasses"])
    apply_globals(
        mod,
        {
            "PASTA_BASE": pasta,
            "URL_PLANILHA": url,
            "USAR_OCR": usar_ocr,
            "REFINAR_IA": refinar_ia,
            "MOTOR_OCR": motor_ocr,
            "MODELO_IA": (cfg.get("modelo_ia") or "llama3.2:3b").strip() or "llama3.2:3b",
            "OLLAMA_URL": (cfg.get("ollama_url") or "http://127.0.0.1:11434").strip()
            or "http://127.0.0.1:11434",
            "ANOS_FILTRO": anos_filtro,
        },
    )
    job.emit("info", "Planilha: {0}".format(url[:120]))
    if anos_filtro:
        job.emit("info", "Filtro de anos: {0}".format(", ".join(anos_filtro)))
    else:
        job.emit("info", "Filtro de anos: todos")
    job.emit("info", "OCR: {0}".format("ligado" if usar_ocr else "desligado"))
    if usar_ocr:
        job.emit(
            "info",
            "Motor OCR: {0} (tesseract → paddle se precisar)".format(
                motor_ocr
            ),
        )
    job.emit(
        "info",
        "IA: {0}".format(
            "ligada (mes/ano, data, valores, descricao)"
            if refinar_ia
            else "desligada"
        ),
    )
    run_main_with_logs(job, mod)
    job.result["pasta"] = pasta
    job.result["mensagem"] = (
        "Repasses.xlsx + PDFs em {0}\\Repasses".format(pasta)
    )
