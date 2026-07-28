from __future__ import annotations

from pathlib import Path

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs


def run(job) -> None:
    cfg = job.config
    urls_raw = (cfg.get("urls") or "").strip()
    urls = [u.strip() for u in urls_raw.splitlines() if u.strip().startswith("http")]
    if not urls:
        raise ValueError("Informe ao menos uma URL (http/https).")

    pasta = cfg.get("pasta_base") or r"C:\Downloads"
    anos_raw = (cfg.get("anos") or "").strip()
    anos_filtro = [a.strip() for a in anos_raw.split(",") if a.strip()] if anos_raw else []

    mod = load_module("download_documentos", SCRIPTS["documentos"])
    apply_globals(mod, {
        "PASTA_BASE": pasta,
        "TIPO_DOCUMENTO": (cfg.get("tipo_documento") or "").strip(),
        "URLS_PAGINAS": urls,
        "ANOS_FILTRO": anos_filtro,
    })
    if anos_filtro:
        job.emit("info", "Filtro de anos: {0}".format(", ".join(anos_filtro)))
    else:
        job.emit("info", "Filtro de anos: todos")
    run_main_with_logs(job, mod)
    job.result["pasta"] = pasta
    job.result["mensagem"] = "Downloads concluídos em {0}".format(pasta)
