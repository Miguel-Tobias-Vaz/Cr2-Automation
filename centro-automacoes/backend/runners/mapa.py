from __future__ import annotations

import builtins
import json

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs


def run(job) -> None:
    cfg = job.config
    wp = (cfg.get("wp_url") or "").strip().rstrip("/")
    user = (cfg.get("user") or "").strip()
    app_pass = (cfg.get("app_password") or "").strip()
    if not wp or not user or not app_pass:
        raise ValueError("URL WordPress, usuário e senha de aplicativo são obrigatórios.")

    paginas_raw = cfg.get("paginas") or "{}"
    paginas = json.loads(paginas_raw) if isinstance(paginas_raw, str) else paginas_raw

    mod = load_module("mapa_site", SCRIPTS["mapa"])
    apply_globals(mod, {
        "WP_URL": wp,
        "USER": user,
        "APP_PASSWORD": app_pass,
        "SLUG_MAPA_DO_SITE": (cfg.get("slug") or "mapa-do-site").strip(),
        "PAGINAS": paginas,
    })

    old_input = builtins.input
    builtins.input = lambda prompt="": ""
    try:
        run_main_with_logs(job, mod)
    finally:
        builtins.input = old_input

    job.result["mensagem"] = "Mapa do site atualizado em {0}".format(wp)
