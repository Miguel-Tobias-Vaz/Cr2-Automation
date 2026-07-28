from __future__ import annotations

import sys

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs


def _resolver_modo(cfg: dict) -> tuple[str, bool, bool]:
    """Retorna (modo, so_planilha, sem_extracao)."""
    modo = (cfg.get("modo") or "").strip().lower()
    if modo in ("completo", "so_baixar", "so_planilha"):
        return (
            modo,
            modo == "so_planilha",
            modo == "so_baixar",
        )

    # Compatibilidade com configs antigas (checkboxes)
    so_planilha = bool(cfg.get("so_planilha", False))
    sem_extracao = bool(cfg.get("sem_extracao", False))
    if so_planilha and sem_extracao:
        # Conflito: não extrai e também não baixa — força completo
        return "completo", False, False
    if sem_extracao:
        return "so_baixar", False, True
    if so_planilha:
        return "so_planilha", True, False
    return "completo", False, False


def run(job) -> None:
    cfg = job.config
    listagem = (cfg.get("listagem") or "").strip()
    if not listagem:
        raise ValueError("Informe a URL da listagem de licitações.")

    saida = (cfg.get("pasta_saida") or r"C:\Downloads\Licitacoes").strip()
    anos = (cfg.get("anos") or "").strip()
    planilha_modelo = (cfg.get("planilha_modelo") or "").strip()
    planilha_saida = (cfg.get("planilha_saida") or "").strip()
    ocr = bool(cfg.get("ocr", False))
    incluir_sub = bool(cfg.get("incluir_subcategorias", False))
    so_html = bool(cfg.get("so_html", False))
    ignorar_ssl = bool(cfg.get("ignorar_ssl", False))
    sem_renomear = bool(cfg.get("sem_renomear", False))
    motor_ocr = (cfg.get("motor_ocr") or "").strip()

    modo, so_planilha, sem_extracao = _resolver_modo(cfg)
    labels = {
        "completo": "Completo (baixar + extrair + planilha)",
        "so_baixar": "Só baixar (sem extrair / sem planilha)",
        "so_planilha": "Só planilha (sem rebaixar anexos)",
    }
    job.emit("info", "Modo: {0}".format(labels.get(modo, modo)))
    if ocr:
        job.emit("info", "OCR: ligado")
    if incluir_sub:
        job.emit("info", "Subcategorias fracassadas/desertas: ligadas")

    argv = [
        "download_licitacoes",
        "--listagem",
        listagem,
        "--saida",
        saida,
    ]
    if planilha_modelo:
        argv += ["--planilha-modelo", planilha_modelo]
    else:
        argv += ["--planilha-modelo", ""]
    if planilha_saida:
        argv += ["--planilha-saida", planilha_saida]
    if anos:
        argv += ["--anos", anos]
    if ocr:
        argv.append("--ocr")
    if motor_ocr:
        argv += ["--motor-ocr", motor_ocr]
    if incluir_sub:
        argv.append("--incluir-subcategorias")
    if so_planilha:
        argv.append("--so-planilha")
    if sem_extracao:
        argv.append("--sem-extracao")
    if so_html:
        argv.append("--so-html")
    if ignorar_ssl:
        argv.append("--ignorar-ssl")
    if sem_renomear:
        argv.append("--sem-renomear")

    mod = load_module("download_licitacoes", SCRIPTS["licitacoes"])
    mapping = {}
    # Painel: anos vazio = todos (não usa o ANOS_FILTRO hardcoded do script)
    if not anos:
        mapping["ANOS_FILTRO"] = []
    apply_globals(mod, mapping)

    old_argv = sys.argv
    sys.argv = argv
    try:
        run_main_with_logs(job, mod)
    finally:
        sys.argv = old_argv

    job.result["pasta"] = saida
    if modo == "so_baixar":
        job.result["mensagem"] = "Anexos baixados em {0} (sem planilha).".format(saida)
    elif modo == "so_planilha":
        job.result["mensagem"] = "Planilha atualizada a partir de {0}.".format(saida)
    else:
        job.result["mensagem"] = "Licitações processadas em {0}".format(saida)
