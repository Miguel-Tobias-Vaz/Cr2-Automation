from __future__ import annotations

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs


def run(job) -> None:
    cfg = job.config
    pasta = (cfg.get("pasta_base") or r"C:\Downloads\Inhangapi").strip()
    site = (cfg.get("site") or "").strip()
    fontes_raw = (cfg.get("fontes") or "").strip()
    ler_pdf = bool(cfg.get("ler_pdf", True))
    limite = int(cfg.get("limite_posts") or 0)
    anos_raw = (cfg.get("anos") or "").strip()
    anos_filtro = [a.strip() for a in anos_raw.split(",") if a.strip()] if anos_raw else []

    fontes = None
    if fontes_raw:
        fontes = []
        for linha in fontes_raw.splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            # Formato: url | modo | pasta
            partes = [p.strip() for p in linha.split("|")]
            if len(partes) < 1:
                continue
            item = {"url": partes[0], "modo": "categoria", "pasta": "Documentos"}
            if len(partes) >= 2 and partes[1]:
                item["modo"] = partes[1]
            if len(partes) >= 3 and partes[2]:
                item["pasta"] = partes[2]
            fontes.append(item)
        if not fontes:
            raise ValueError("Nenhuma fonte válida informada.")

    if not site and not fontes:
        raise ValueError("Informe o site (domínio) ou as fontes.")

    mod = load_module("download_normas", SCRIPTS["normas"])
    mapping = {
        "PASTA_BASE": pasta,
        "LER_PDF": ler_pdf,
        "LIMITE_POSTS": limite,
        "ANOS_FILTRO": anos_filtro,
    }
    if site:
        mapping["SITE"] = site.rstrip("/")
    if fontes is not None:
        mapping["FONTES"] = fontes
    apply_globals(mod, mapping)
    if anos_filtro:
        job.emit("info", "Filtro de anos: {0}".format(", ".join(anos_filtro)))
    else:
        job.emit("info", "Filtro de anos: todos")
    run_main_with_logs(job, mod)
    job.result["pasta"] = pasta
    job.result["mensagem"] = "Download de normas concluído."
