from __future__ import annotations

import sys
from pathlib import Path

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs

SCRIPT = SCRIPTS["pub_repasses"]


def run(job) -> None:
    cfg = job.config
    usuario = (cfg.get("usuario") or "").strip()
    senha = (cfg.get("senha") or "").strip()
    url = (cfg.get("url_portal_repasse") or "").strip()
    pasta = (cfg.get("pasta_base") or "").strip()
    if not usuario or not senha:
        raise ValueError("Usuário e senha do portal CR2 são obrigatórios.")
    if not url:
        raise ValueError("URL do portal de Repasse é obrigatória.")
    if not pasta:
        raise ValueError(
            "Pasta base é obrigatória (onde está Repasses.xlsx, "
            "ex.: C:\\Downloads\\repasses)."
        )

    mod = load_module("publicacao_repasses", SCRIPT)

    registro = None
    if any(
        str(cfg.get(k) or "").strip()
        for k in (
            "mes_ano",
            "data",
            "valor_previsto",
            "valor_realizado",
            "descricao",
            "arquivo",
        )
    ):
        registro = {
            "link": (cfg.get("link") or "").strip(),
            "mes_ano": (cfg.get("mes_ano") or "").strip(),
            "data": (cfg.get("data") or "").strip(),
            "valor_previsto": (cfg.get("valor_previsto") or "").strip(),
            "valor_realizado": (cfg.get("valor_realizado") or "").strip(),
            "descricao": (cfg.get("descricao") or "").strip(),
            "arquivo": (cfg.get("arquivo") or "").strip(),
        }

    patch = {
        "PORTAL_USUARIO": usuario,
        "PORTAL_SENHA": senha,
        "URL_PORTAL_REPASSE": url,
        "PASTA_BASE": Path(pasta),
        "HEADLESS": bool(cfg.get("headless")),
        "MODO_TESTE": bool(cfg.get("modo_teste")),
        "REGISTRO_UNICO": registro,
    }
    apply_globals(mod, patch)

    argv = [str(SCRIPT)]
    if cfg.get("modo_teste"):
        argv.append("--test")
    if cfg.get("auto_confirm"):
        argv.append("--yes")
    if cfg.get("headless"):
        argv.append("--headless")
    if pasta and not registro:
        argv.extend(["--pasta", pasta])

    old_argv = sys.argv
    sys.argv = argv
    try:
        job.emit("info", "Iniciando publicação de Repasses...")
        job.emit("info", "Pasta: {0}".format(pasta))
        run_main_with_logs(job, mod)
    finally:
        sys.argv = old_argv

    job.result["mensagem"] = "Publicação de Repasses concluída."
