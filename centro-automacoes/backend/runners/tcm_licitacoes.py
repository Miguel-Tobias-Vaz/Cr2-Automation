from __future__ import annotations

import os
import re

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs


def _parse_anos(cfg: dict) -> tuple[int | None, int | None]:
    """Interpreta modo_ano + ano_min/ano_max ou campo legado `anos`."""
    modo = (cfg.get("modo_ano") or "").strip().lower()
    if modo == "todos":
        return None, None

    def _int(v) -> int | None:
        if v in (None, ""):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    ano_min = _int(cfg.get("ano_min"))
    ano_max = _int(cfg.get("ano_max"))

    if modo == "unico" and ano_min is not None:
        return ano_min, ano_min
    if modo == "faixa" and (ano_min is not None or ano_max is not None):
        if ano_min is not None and ano_max is not None and ano_min > ano_max:
            ano_min, ano_max = ano_max, ano_min
        return ano_min, ano_max

    anos_raw = (cfg.get("anos") or "").strip()
    if not anos_raw:
        return ano_min, ano_max

    nums = [int(y) for y in re.findall(r"(?:19|20)\d{2}", anos_raw)]
    if not nums:
        return ano_min, ano_max
    if len(nums) == 1:
        return nums[0], nums[0]
    lo, hi = min(nums), max(nums)
    return lo, hi


def run(job) -> None:
    cfg = job.config
    link = (cfg.get("link_mural") or cfg.get("listagem") or "").strip()
    if not link:
        raise ValueError("Informe o link do mural do TCM-PA (com filtro de município).")

    saida = (cfg.get("pasta_saida") or r"C:\Downloads\TCM-Licitacoes").strip()
    entidade = (cfg.get("nome_entidade") or cfg.get("entidade") or "").strip()
    ano_min, ano_max = _parse_anos(cfg)
    ocr = bool(cfg.get("ocr", True))
    so_planilha = bool(cfg.get("so_planilha", False))

    mod = load_module("tcm_licitacoes", SCRIPTS["tcm_licitacoes"])
    apply_globals(
        mod,
        {
            "LINK_MURAL": link,
            "PASTA_SAIDA": saida,
            "NOME_ENTIDADE": entidade,
            "ANO_MINIMO": ano_min,
            "ANO_MAXIMO": ano_max,
            "OCR_ATIVO": ocr,
            "SO_PLANILHA": so_planilha,
        },
    )
    setattr(mod, "ULTIMO_RESULTADO", {})

    if ano_min is None and ano_max is None:
        job.emit("info", "Período: todos os anos")
    elif ano_min == ano_max:
        job.emit("info", "Período: ano {0}".format(ano_min))
    else:
        job.emit("info", "Período: {0} a {1}".format(ano_min, ano_max))
    job.emit("info", "OCR: {0}".format("ligado" if ocr else "desligado"))
    job.emit(
        "info",
        "Modo: {0}".format("somente planilha" if so_planilha else "download completo"),
    )

    try:
        run_main_with_logs(job, mod)
    except Exception as exc:
        if type(exc).__name__ == "Cancelado" or job.cancel_requested:
            job.cancel_requested = True
            upload = getattr(mod, "ULTIMO_RESULTADO", None) or {}
            if upload.get("pasta"):
                job.result["pasta"] = upload["pasta"]
            if upload.get("planilha"):
                job.result["planilha"] = upload["planilha"]
            job.result["mensagem"] = "Interrompido — {0} licitação(ões) processada(s).".format(
                upload.get("licitacoes", "?")
            )
            return
        raise

    upload = getattr(mod, "ULTIMO_RESULTADO", None) or {}
    pasta_final = upload.get("pasta") or saida
    job.result["pasta"] = pasta_final
    if upload.get("planilha"):
        job.result["planilha"] = upload["planilha"]
    if upload.get("licitacoes") is not None:
        job.result["licitacoes"] = upload["licitacoes"]
    if upload.get("contratos") is not None:
        job.result["contratos"] = upload["contratos"]

    if not job.result.get("planilha"):
        pasta = job.result.get("pasta") or saida
        if os.path.isdir(pasta):
            xs = sorted(
                (
                    os.path.join(pasta, f)
                    for f in os.listdir(pasta)
                    if f.lower().endswith(".xlsx") and f.startswith("licitacoes_")
                ),
                key=os.path.getmtime,
                reverse=True,
            )
            if xs:
                job.result["planilha"] = xs[0]

    n_lic = upload.get("licitacoes", "?")
    n_cont = upload.get("contratos", "?")
    job.result["mensagem"] = "TCM-PA: {0} licitações, {1} contratos — {2}".format(
        n_lic, n_cont, pasta_final
    )
