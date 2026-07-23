"""Rotas da automação Publicação Dic/Est/Ter."""

from __future__ import annotations

import asyncio
import json
import queue
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DIC_EST_TER = PROJECT_ROOT / "automacoes" / "dic-est-ter"

if str(DIC_EST_TER) not in sys.path:
    sys.path.insert(0, str(DIC_EST_TER))

import servidor_front as mf  # noqa: E402

router = APIRouter(tags=["dic_est_ter"])


@router.get("/api/status")
def milagre_status():
    with mf._job_lock:
        return {
            "running": mf._job["running"],
            "job_id": mf._job.get("job_id"),
            "logs": mf._job["logs"][-200:],
            "resumo": mf._job["resumo"],
            "progresso": dict(mf._job.get("progresso") or {}),
            "log_path": mf._job.get("log_path"),
        }


@router.get("/api/defaults")
def milagre_defaults():
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
def milagre_validar(body: dict):
    try:
        return mf.validar_pedido(body)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/api/publicar")
def milagre_publicar(body: dict):
    with mf._job_lock:
        if mf._job["running"]:
            return JSONResponse(
                status_code=409,
                content={
                    "ok": False,
                    "erro": (
                        "Ja existe uma publicacao em andamento. "
                        "Aguarde terminar ou use Parar / Liberar."
                    ),
                    "running": True,
                },
            )
    threading.Thread(target=mf._rodar_publicacao, args=(body,), daemon=True).start()
    return {"ok": True, "started": True}


@router.post("/api/cancelar")
@router.get("/api/cancelar")
@router.post("/api/parar")
@router.get("/api/parar")
def milagre_cancelar():
    estava = mf._liberar_publicacao()
    return {
        "ok": True,
        "estava_rodando": estava,
        "msg": "Fila liberada. Pode publicar de novo.",
    }


@router.get("/api/download/nao-publicadas")
def milagre_download_nao_publicadas():
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
async def milagre_logs_stream():
    q: queue.Queue = queue.Queue()
    with mf._job_lock:
        mf._job["subscribers"].append(q)
        for entry in mf._job["logs"][-200:]:
            q.put(entry)

    async def gen():
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
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
