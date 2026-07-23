from __future__ import annotations

import builtins
import sys
from pathlib import Path

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs

SCRIPT = SCRIPTS["publicacao"]


def run(job) -> None:
    cfg = job.config
    usuario = (cfg.get("usuario") or "").strip()
    senha = (cfg.get("senha") or "").strip()
    if not usuario or not senha:
        raise ValueError("Usuário e senha do portal CR2 são obrigatórios.")

    mod = load_module("publicador_cr2", SCRIPT)
    patch = {
        "PORTAL_USUARIO": usuario,
        "PORTAL_SENHA": senha,
        "URL_PORTAL_RGF": (cfg.get("url_portal_rgf") or "").strip(),
        "URL_PORTAL_RREO": (cfg.get("url_portal_rreo") or "").strip(),
        "URL_PORTAL_BALANCETE": (cfg.get("url_portal_balancete") or "").strip(),
        "URL_PORTAL_BALANCO_REL_ANUAIS": (cfg.get("url_portal_balanco") or "").strip(),
        "HEADLESS": bool(cfg.get("headless")),
        "MODO_TESTE": bool(cfg.get("modo_teste")),
    }
    apply_globals(mod, patch)

    if cfg.get("pasta_rgf"):
        mod.PASTA_RGF = Path(cfg["pasta_rgf"])
    if cfg.get("pasta_rreo"):
        mod.PASTA_RREO = Path(cfg["pasta_rreo"])
    if cfg.get("pasta_balancete"):
        mod.PASTA_BALANCETE = Path(cfg["pasta_balancete"])
    if cfg.get("pasta_balanco"):
        mod.PASTA_BALANCO_REL_ANUAIS = Path(cfg["pasta_balanco"])

    argv = [str(SCRIPT)]
    if cfg.get("modo_teste"):
        argv.append("--test")
    if cfg.get("auto_confirm"):
        argv.append("--yes")
    if cfg.get("so_rgf"):
        argv.append("--so-rgf")
    if cfg.get("so_rreo"):
        argv.append("--so-rreo")
    if cfg.get("so_balancete"):
        argv.append("--so-balancete")
    if cfg.get("so_balanco"):
        argv.append("--so-balanco-rel")
    ano = (cfg.get("ano") or "").strip()
    if ano:
        argv.extend(["--ano", ano])

    old_argv = sys.argv
    sys.argv = argv
    try:
        job.emit("info", "Iniciando publicador (Playwright)...")
        run_main_with_logs(job, mod)
    finally:
        sys.argv = old_argv

    job.result["mensagem"] = "Publicação concluída."
