from __future__ import annotations

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs


def run(job) -> None:
    cfg = job.config
    url = (cfg.get("url_categoria") or "").strip()
    site = (cfg.get("site") or "").strip()
    if not url or not site:
        raise ValueError("URL da categoria e Site são obrigatórios.")

    pasta = cfg.get("pasta_base") or r"C:\Downloads"
    mod = load_module("download_categorias", SCRIPTS["categorias"])
    apply_globals(mod, {
        "PASTA_BASE": pasta,
        "URL_CATEGORIA": url,
        "SITE": site,
    })
    run_main_with_logs(job, mod)
    job.result["pasta"] = pasta
    job.result["mensagem"] = "Downloads por categoria concluídos."
