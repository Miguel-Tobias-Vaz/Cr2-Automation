"""Runner: Publicação Dic/Est/Ter (planilhas Drive → portal CR2)."""

from __future__ import annotations

import sys
from pathlib import Path

from backend.jobs import JobCancelled
from backend.runners.base import PROJECT_ROOT

DIC_EST_TER = PROJECT_ROOT / "automacoes" / "dic-est-ter"
if str(DIC_EST_TER) not in sys.path:
    sys.path.insert(0, str(DIC_EST_TER))

import job_runtime as jobrt  # noqa: E402
import servidor_front as mf  # noqa: E402


def _init_jobrt_for_global(job) -> None:
    jobrt._garantir_pastas()
    with jobrt._lock:
        jobrt._estado["running"] = True
        jobrt._estado["cancel_requested"] = False
        jobrt._estado["job_id"] = job.id
        jobrt._estado["logs"] = []
        jobrt._estado["resumo"] = None
        jobrt._estado["arquivo_nao_publicadas"] = None
        jobrt._estado["log_path"] = str(jobrt.PASTA_LOGS / "job_{}.log".format(job.id))
        jobrt._estado["progresso"] = {
            "total": 0,
            "publicadas": 0,
            "erros": 0,
            "retries": 0,
            "chunk_atual": 0,
            "chunk_total": 0,
            "fase": "iniciando",
            "iniciado_em": job.started_at,
            "eta_s": None,
            "linhas_processadas": 0,
            "msg": "Job {} na fila global".format(job.id),
            "meta": mf._meta_resumida(job.config),
        }


def _sync_progress_to_job(job, prog: dict) -> None:
    total = int(prog.get("chunk_total") or prog.get("total") or 0)
    done = int(prog.get("chunk_atual") or prog.get("publicadas") or 0)
    label = str(prog.get("msg") or prog.get("fase") or "").strip()
    if total > 0:
        job.set_progress(done=done, total=total, label=label[:80] if label else None)


def _install_bridge(job) -> tuple:
    orig_emit = jobrt.emit
    orig_pedido = jobrt.pedido_cancelado
    orig_progresso = jobrt.atualizar_progresso

    def bridged_emit(level, msg, para_sse=True):
        orig_emit(level, msg, para_sse=para_sse)
        if level == "progress":
            return
        job.emit(str(level), str(msg))

    def bridged_pedido():
        if job.cancel_requested:
            with jobrt._lock:
                jobrt._estado["cancel_requested"] = True
            return True
        return orig_pedido()

    def bridged_progresso(**kwargs):
        orig_progresso(**kwargs)
        with jobrt._lock:
            _sync_progress_to_job(job, dict(jobrt._estado.get("progresso") or {}))

    jobrt.emit = bridged_emit
    jobrt.pedido_cancelado = bridged_pedido
    jobrt.atualizar_progresso = bridged_progresso
    return orig_emit, orig_pedido, orig_progresso


def _restore_bridge(orig):
    jobrt.emit, jobrt.pedido_cancelado, jobrt.atualizar_progresso = orig


def run(job) -> None:
    body = job.config or {}
    val = mf.validar_pedido(body)
    if not val.get("ok"):
        msgs = list(val.get("erros_gerais") or [])
        for tipo, fx in (val.get("fluxos") or {}).items():
            for err in fx.get("erros") or []:
                if err.get("level") != "warn":
                    msgs.append(
                        "{} L{}: {}".format(
                            mf.LABELS_FLUXO.get(tipo, tipo),
                            err.get("linha"),
                            err.get("msg"),
                        )
                    )
        raise ValueError(msgs[0] if msgs else "Validação falhou.")

    _init_jobrt_for_global(job)
    bridge = _install_bridge(job)
    job.emit("info", "Dic/Est/Ter — publicação via fila global")

    try:
        mf._executar_publicacao(body)
    finally:
        _restore_bridge(bridge)

    snap = jobrt.snapshot()
    resumo = snap.get("resumo") or {}
    if resumo:
        job.result.update(resumo)
    if snap.get("arquivo_nao_publicadas"):
        job.result["arquivo_nao_publicadas"] = snap["arquivo_nao_publicadas"]
        job.result["download_nao_publicadas"] = "/api/download/nao-publicadas"

    if snap.get("cancel_requested") or resumo.get("cancelado"):
        job.cancel_requested = True
        raise JobCancelled()

    if resumo.get("validacao") and not resumo.get("ok"):
        raise ValueError(str(resumo.get("erro") or "Validação falhou na publicação."))

    if resumo.get("ok") is False and resumo.get("erro"):
        raise RuntimeError(str(resumo.get("erro")))

    pub_count = int(resumo.get("publicadas") or 0)
    job.result.setdefault(
        "mensagem",
        "Publicação Dic/Est/Ter concluída — {0} linha(s).".format(pub_count),
    )

    with jobrt._lock:
        jobrt._estado["running"] = False
        jobrt._estado["cancel_requested"] = False
