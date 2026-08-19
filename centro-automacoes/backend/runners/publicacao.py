from __future__ import annotations

import sys
from pathlib import Path

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs
from backend.user_storage import is_local_mode, path_belongs_to_user

SCRIPT = SCRIPTS["publicacao"]

_URL_PASTA = (
    ("url_portal_rgf", "pasta_rgf", "RGF"),
    ("url_portal_rreo", "pasta_rreo", "RREO"),
    ("url_portal_balancete", "pasta_balancete", "Balancete"),
    ("url_portal_balanco", "pasta_balanco", "Balanço"),
)


def _validate_pastas(cfg: dict, owner: str | None) -> None:
    if is_local_mode():
        return
    for url_key, pasta_key, label in _URL_PASTA:
        url = (cfg.get(url_key) or "").strip()
        pasta = (cfg.get(pasta_key) or "").strip()
        if not url:
            continue
        if not pasta:
            raise ValueError(
                "URL {0} informada, mas falta a pasta. Envie um ZIP ou escolha em Meus arquivos.".format(
                    label
                )
            )
        if owner and not path_belongs_to_user(pasta, owner):
            raise ValueError("Pasta {0} fora do seu workspace no servidor.".format(label))


def run(job) -> None:
    cfg = job.config
    usuario = (cfg.get("usuario") or "").strip()
    senha = (cfg.get("senha") or "").strip()
    if not usuario or not senha:
        raise ValueError("Usuário e senha do portal CR2 são obrigatórios.")

    _validate_pastas(cfg, getattr(job, "owner", None))

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
