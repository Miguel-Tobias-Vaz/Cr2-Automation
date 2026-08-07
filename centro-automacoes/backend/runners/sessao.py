from __future__ import annotations

import sys
from pathlib import Path

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs

SCRIPT = SCRIPTS["sessao"]


def run(job) -> None:
    cfg = job.config
    usuario = (cfg.get("usuario") or "").strip()
    senha = (cfg.get("senha") or "").strip()
    url = (cfg.get("url_portal_sessao") or "").strip()
    pasta = (cfg.get("pasta_sessoes") or "").strip()
    if not usuario or not senha:
        raise ValueError("Usuário e senha do portal CR2 são obrigatórios.")
    if not url:
        raise ValueError("URL do portal de Sessão é obrigatória.")
    if not pasta:
        raise ValueError(
            "Pasta de sessões é obrigatória "
            "(ex.: C:\\Users\\...\\sessoes_2021)."
        )

    mod = load_module("publicacao_sessao", SCRIPT)

    registro = None
    # Sessao avulsa pelo painel (opcional; sobrescreve a pasta)
    if any(str(cfg.get(k) or "").strip() for k in ("tipo", "data", "numero")):
        registro = {
            "tipo": (cfg.get("tipo") or "").strip(),
            "data": (cfg.get("data") or "").strip(),
            "numero": (cfg.get("numero") or "").strip(),
            "pauta": (cfg.get("pauta") or "").strip(),
            "ata": (cfg.get("ata") or "").strip(),
            "presenca": (cfg.get("presenca") or "").strip(),
            "votacoes_arquivo": (cfg.get("votacoes_arquivo") or "").strip(),
            "votacoes_link": (cfg.get("votacoes_link") or "").strip(),
        }

    patch = {
        "PORTAL_USUARIO": usuario,
        "PORTAL_SENHA": senha,
        "URL_PORTAL_SESSAO": url,
        "PASTA_SESSOES": Path(pasta),
        "HEADLESS": bool(cfg.get("headless")),
        "MODO_TESTE": bool(cfg.get("modo_teste")),
        "REGISTRO_UNICO": registro,
        "REFINAR_IA_DECLARACAO": bool(cfg.get("refinar_ia_declaracao", True)),
        "MODELO_IA": (cfg.get("modelo_ia") or "llama3.2:3b").strip() or "llama3.2:3b",
        "OLLAMA_URL": (cfg.get("ollama_url") or "http://127.0.0.1:11434").strip()
        or "http://127.0.0.1:11434",
    }
    csv_path = (cfg.get("csv_fila") or "").strip()
    if csv_path:
        patch["CSV_FILA"] = Path(csv_path)
    apply_globals(mod, patch)
    if patch["REFINAR_IA_DECLARACAO"]:
        job.emit(
            "info",
            "Declaracoes: IA local {0} @ {1} (mes de referencia do PDF)".format(
                patch["MODELO_IA"], patch["OLLAMA_URL"]
            ),
        )
    else:
        job.emit("info", "Declaracoes: IA desligada (heuristica no nome/texto)")

    argv = [str(SCRIPT)]
    if cfg.get("modo_teste"):
        argv.append("--test")
    if cfg.get("auto_confirm"):
        argv.append("--yes")
    if cfg.get("headless"):
        argv.append("--headless")
    if pasta and not registro:
        argv.extend(["--pasta", pasta])
    if csv_path and not registro and not pasta:
        argv.extend(["--csv", csv_path])

    old_argv = sys.argv
    sys.argv = argv
    try:
        job.emit("info", "Iniciando publicação de Sessão (pasta)...")
        run_main_with_logs(job, mod)
    finally:
        sys.argv = old_argv

    job.result["mensagem"] = "Publicação de Sessão concluída."
