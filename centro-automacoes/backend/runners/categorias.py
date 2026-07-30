from __future__ import annotations

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs


def run(job) -> None:
    cfg = job.config
    url = (cfg.get("url_categoria") or "").strip()
    site = (cfg.get("site") or "").strip()
    if not url or not site:
        raise ValueError("URL da categoria e Site são obrigatórios.")

    pasta = cfg.get("pasta_base") or r"C:\Downloads"
    anos_raw = (cfg.get("anos") or "").strip()
    anos_filtro = [a.strip() for a in anos_raw.split(",") if a.strip()] if anos_raw else []
    limite = int(cfg.get("limite_posts") or 0)
    ler_pdf = bool(cfg.get("ler_pdf", True))
    mod = load_module("download_categorias", SCRIPTS["categorias"])
    apply_globals(mod, {
        "PASTA_BASE": pasta,
        "URL_CATEGORIA": url,
        "SITE": site.rstrip("/"),
        "ANOS_FILTRO": anos_filtro,
        "LIMITE_POSTS": limite,
        "LER_PDF": ler_pdf,
    })
    if anos_filtro:
        job.emit("info", "Filtro de anos: {0}".format(", ".join(anos_filtro)))
    else:
        job.emit("info", "Filtro de anos: todos")
    job.emit("info", "Leitura PDF para nome: {0}".format("sim" if ler_pdf else "nao"))
    run_main_with_logs(job, mod)
    job.result["pasta"] = pasta
    job.result["mensagem"] = "Downloads por categoria concluídos."
