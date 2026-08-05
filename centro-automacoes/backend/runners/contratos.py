"""Runner: coleta de contratos/aditivos (Governo Transparente)."""

from __future__ import annotations

import sys
from pathlib import Path

from backend.runners.base import AUTOMACOES, apply_globals, load_module, run_main_with_logs

CONTRATOS_DIR = AUTOMACOES / "raspar-contratos"


def run(job) -> None:
    cfg = job.config
    orgao = (cfg.get("orgao") or "").strip() or "43559588"
    inicio = (cfg.get("inicio") or "").strip() or "01/01/2023"
    fim = (cfg.get("fim") or "").strip() or "31/12/2023"
    ano = (cfg.get("ano") or "").strip()
    datainfo = (cfg.get("datainfo") or "").strip()
    saida = (cfg.get("pasta_saida") or r"C:\Downloads\Contratos").strip()
    headed = bool(cfg.get("headed", False))
    reset_checkpoint = bool(cfg.get("reset_checkpoint", False))
    sem_retry_erros = bool(cfg.get("sem_retry_erros", False))
    apenas_listagem = bool(cfg.get("apenas_listagem", False))
    limite_raw = cfg.get("limite")
    try:
        limite = int(limite_raw or 0)
    except (TypeError, ValueError):
        limite = 0

    if not orgao:
        raise ValueError("Informe o ID do órgão no portal Governo Transparente.")
    if not inicio or not fim:
        raise ValueError("Informe as datas de início e fim (dd/mm/aaaa).")

    job.emit("info", "Órgão: {0}".format(orgao))
    job.emit("info", "Período: {0} → {1}".format(inicio, fim))
    job.emit("info", "Pasta de saída: {0}".format(saida))
    if headed:
        job.emit("info", "Navegador visível (headed)")
    if apenas_listagem:
        job.emit("info", "Modo: apenas listagem")
    if limite > 0:
        job.emit("info", "Limite de registros: {0}".format(limite))

    if str(CONTRATOS_DIR) not in sys.path:
        sys.path.insert(0, str(CONTRATOS_DIR))

    argv = [
        "raspar_contratos",
        "--orgao",
        orgao,
        "--inicio",
        inicio,
        "--fim",
        fim,
        "--saida",
        saida,
    ]
    if ano:
        argv += ["--ano", ano]
    if datainfo:
        argv += ["--datainfo", datainfo]
    if headed:
        argv.append("--headed")
    if reset_checkpoint:
        argv.append("--reset-checkpoint")
    if sem_retry_erros:
        argv.append("--sem-retry-erros")
    if apenas_listagem:
        argv.append("--apenas-listagem")
    if limite > 0:
        argv += ["--limite", str(limite)]

    mod = load_module("raspar_contratos_main", CONTRATOS_DIR / "main.py")
    apply_globals(mod, {})

    old_argv = sys.argv
    sys.argv = argv
    try:
        run_main_with_logs(job, mod)
    finally:
        sys.argv = old_argv

    job.result["pasta"] = saida
    planilha = Path(saida) / "dados" / "Relacao de contratos e aditivos.xlsx"
    if planilha.is_file():
        job.result["planilha"] = str(planilha)
    if apenas_listagem:
        job.result["mensagem"] = "Listagem concluída — saída em {0}".format(saida)
    else:
        job.result["mensagem"] = "Contratos processados em {0}".format(saida)
