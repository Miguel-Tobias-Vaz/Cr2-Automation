"""Rotas da automação Publicação Dic/Est/Ter."""

from __future__ import annotations

import asyncio
import json
import queue
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DIC_EST_TER = PROJECT_ROOT / "automacoes" / "dic-est-ter"

if str(DIC_EST_TER) not in sys.path:
    sys.path.insert(0, str(DIC_EST_TER))

import servidor_front as mf  # noqa: E402

from backend import auth  # noqa: E402
from backend.deps import require_user  # noqa: E402
from backend.jobs import JobStatus, QueueFullError  # noqa: E402
from backend.runners import dispatch  # noqa: E402
from backend.state import jobs  # noqa: E402

router = APIRouter(tags=["dic_est_ter"])


def _user_is_admin(user) -> bool:
    return user.role == "admin" or auth.is_panel_admin(user)


def _sees_all_jobs(user) -> bool:
    return auth.is_panel_admin(user)


def _owners_match(owner: str | None, username: str | None) -> bool:
    if not owner or not username:
        return False
    return owner.strip().lower() == username.strip().lower()


def _assert_can_access_dic_job(job, user) -> None:
    if not auth.is_enabled():
        return
    if _sees_all_jobs(user):
        return
    if _owners_match(job.owner, user.username):
        return
    raise HTTPException(403, "Sem permissão para acessar este processo.")


def _active_dic_job():
    """Job dic_est_ter pending/running mais recente."""
    with jobs._lock:
        alive = [
            j
            for j in jobs._jobs.values()
            if j.service_id == "dic_est_ter"
            and j.status in (JobStatus.PENDING, JobStatus.RUNNING)
        ]
    if not alive:
        return None
    return max(alive, key=lambda j: j.created_at)


def _active_dic_job_for_user(user):
    gjob = _active_dic_job()
    if gjob is None:
        return None
    if not auth.is_enabled():
        return gjob
    if _sees_all_jobs(user) or _owners_match(gjob.owner, user.username):
        return gjob
    return None


def _idle_status() -> dict:
    return {
        "running": False,
        "pending": False,
        "global_job_id": None,
        "job_id": None,
        "logs": [],
        "resumo": None,
        "progresso": {},
        "log_path": None,
        "cancel_requested": False,
    }


def _status_from_global(job) -> dict:
    d = job.to_dict(jobs)
    prog = d.get("progress") or {}
    progresso = {
        "total": prog.get("total") or 0,
        "publicadas": prog.get("done") or 0,
        "chunk_atual": prog.get("done") or 0,
        "chunk_total": prog.get("total") or 0,
        "fase": "pending" if job.status == JobStatus.PENDING else "publicando",
        "msg": prog.get("label") or "",
    }
    running = job.status == JobStatus.RUNNING
    pending = job.status == JobStatus.PENDING
    return {
        "running": running,
        "pending": pending,
        "global_job_id": job.id,
        "job_id": job.id,
        "status": job.status.value,
        "queue": d.get("queue"),
        "logs": job.logs[-200:],
        "resumo": job.result if not running and not pending else None,
        "progresso": progresso,
        "cancel_requested": job.cancel_requested,
        "log_path": str(job.dir / "job.log"),
    }


@router.get("/api/status")
def milagre_status(user=Depends(require_user)):
    gjob = _active_dic_job_for_user(user)
    if gjob is not None:
        return _status_from_global(gjob)

    if auth.is_enabled() and not _user_is_admin(user):
        idle = _idle_status()
        idle["status"] = "idle"
        return idle

    with mf._job_lock:
        snap = {
            "running": mf._job["running"],
            "job_id": mf._job.get("job_id"),
            "logs": mf._job["logs"][-200:],
            "resumo": mf._job["resumo"],
            "progresso": dict(mf._job.get("progresso") or {}),
            "log_path": mf._job.get("log_path"),
        }
    snap["global_job_id"] = None
    snap["pending"] = False
    return snap


@router.get("/api/defaults")
def milagre_defaults(user=Depends(require_user)):
    pub = mf.pub
    return {
        "usuario": (pub.PORTAL_USUARIO or "").strip(),
        "portal_estagiario": (pub.URL_PORTAL_ESTAGIARIO or "").strip(),
        "portal_terceirizado": (pub.URL_PORTAL_TERCEIRIZADO or "").strip(),
        "portal_divida": (pub.URL_PORTAL_DIVIDA or "").strip(),
        "estagiario": (pub.PLANILHA_DRIVE_ESTAGIARIO or "").strip(),
        "terceirizado": (pub.PLANILHA_DRIVE_TERCEIRIZADO or "").strip(),
        "divida": (pub.PLANILHA_DRIVE_DIVIDA or "").strip(),
        "modo_publicacao": "criar_publicacao_1a1",
    }


@router.post("/api/validar")
def milagre_validar(body: dict, user=Depends(require_user)):
    try:
        return mf.validar_pedido(body)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/api/publicar")
def milagre_publicar(body: dict, user=Depends(require_user)):
    val = mf.validar_pedido(body)
    if not val.get("ok"):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "validacao": val,
                "erro": "Validação falhou antes de enfileirar.",
            },
        )
    owner = user.username if auth.is_enabled() else None
    try:
        job = jobs.enqueue("dic_est_ter", body, dispatch, owner=owner)
    except QueueFullError as exc:
        raise HTTPException(503, str(exc)) from exc

    meta = jobs.queue_meta(job)
    return {
        "ok": True,
        "started": job.status == JobStatus.RUNNING,
        "job_id": job.id,
        "global_job_id": job.id,
        "status": job.status.value,
        "queue": meta,
    }


@router.post("/api/cancelar")
@router.get("/api/cancelar")
@router.post("/api/parar")
@router.get("/api/parar")
def milagre_cancelar(user=Depends(require_user)):
    gjob = _active_dic_job_for_user(user)
    if gjob is None and auth.is_enabled() and not _user_is_admin(user):
        gjob_other = _active_dic_job()
        if gjob_other is not None:
            raise HTTPException(403, "Sem permissão para cancelar este processo.")
    if gjob is None:
        gjob = _active_dic_job()
    if gjob is not None:
        if not auth.can_cancel_job(user, gjob.owner):
            raise HTTPException(403, "Sem permissão para cancelar este processo.")
        jobs.cancel(gjob.id)
        mf._liberar_publicacao()
        estava = gjob.status in (JobStatus.RUNNING, JobStatus.PENDING)
        return {
            "ok": True,
            "estava_rodando": estava,
            "job_id": gjob.id,
            "msg": (
                "Cancelamento solicitado — a fila deste processo sera interrompida."
                if estava
                else "Nenhuma fila ativa (estado liberado)."
            ),
        }
    estava = mf._liberar_publicacao()
    return {
        "ok": True,
        "estava_rodando": estava,
        "msg": (
            "Cancelamento solicitado — a fila deste processo sera interrompida."
            if estava
            else "Nenhuma fila ativa (estado liberado)."
        ),
    }


@router.get("/api/download/nao-publicadas")
def milagre_download_nao_publicadas(user=Depends(require_user)):
    gjob = _active_dic_job_for_user(user)
    if gjob is None:
        gjob = _active_dic_job()
    if gjob:
        _assert_can_access_dic_job(gjob, user)
    elif auth.is_enabled() and not _user_is_admin(user):
        raise HTTPException(404, "Nenhuma planilha de correcao disponivel.")

    caminho = None
    if gjob and gjob.result:
        caminho = gjob.result.get("arquivo_nao_publicadas")
    if not caminho:
        if auth.is_enabled() and not _user_is_admin(user):
            raise HTTPException(404, "Nenhuma planilha de correcao disponivel.")
        with mf._job_lock:
            caminho = mf._job.get("arquivo_nao_publicadas")
            if not caminho and mf._job.get("resumo"):
                caminho = (mf._job["resumo"] or {}).get("arquivo_nao_publicadas")
    if not caminho:
        raise HTTPException(404, "Nenhuma planilha de correcao disponivel.")
    path = Path(caminho)
    if not path.is_file():
        raise HTTPException(404, "Arquivo nao encontrado no disco.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


@router.get("/api/logs")
async def milagre_logs_stream(user=Depends(require_user)):
    gjob = _active_dic_job_for_user(user)
    if gjob is None and auth.is_enabled() and not _user_is_admin(user):
        active = _active_dic_job()
        if active is not None:
            raise HTTPException(403, "Sem permissão para acessar este processo.")
        gjob = None

    async def gen_global():
        q = gjob.subscribe()
        while True:
            try:
                entry = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: q.get(timeout=25)
                )
                payload = dict(entry)
                if gjob.status == JobStatus.RUNNING:
                    prog = gjob.to_dict(jobs).get("progress") or {}
                    payload["progresso"] = {
                        "total": prog.get("total") or 0,
                        "publicadas": prog.get("done") or 0,
                        "chunk_atual": prog.get("done") or 0,
                        "chunk_total": prog.get("total") or 0,
                        "fase": "publicando",
                        "msg": prog.get("label") or "",
                    }
                yield "data: {0}\n\n".format(json.dumps(payload, ensure_ascii=False))
            except Exception:
                if gjob.status in (
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                ):
                    break
                yield ": ping\n\n"

    if gjob is not None:
        return StreamingResponse(
            gen_global(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    if auth.is_enabled() and not _user_is_admin(user):
        raise HTTPException(403, "Sem permissão para acessar este processo.")

    q: queue.Queue = queue.Queue()
    with mf._job_lock:
        mf._job["subscribers"].append(q)
        for entry in mf._job["logs"][-200:]:
            q.put(entry)

    async def gen_legacy():
        try:
            while True:
                try:
                    entry = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: q.get(timeout=15)
                    )
                    yield "data: {0}\n\n".format(json.dumps(entry, ensure_ascii=False))
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            with mf._job_lock:
                try:
                    mf._job["subscribers"].remove(q)
                except ValueError:
                    pass

    return StreamingResponse(
        gen_legacy(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
