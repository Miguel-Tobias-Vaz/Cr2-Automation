"""Opto Automações — API."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import auth  # noqa: E402
from backend.config import JOB_TIMEOUT_S  # noqa: E402
from backend.deps import get_optional_user, require_admin, require_user  # noqa: E402
from backend.jobs import JobManager, JobStatus, QueueFullError  # noqa: E402
from backend.job_output import build_download_zip  # noqa: E402
from backend import cleanup  # noqa: E402
from backend.milagre_routes import router as milagre_router  # noqa: E402
from backend.runners import dispatch  # noqa: E402
from backend.state import jobs  # noqa: E402
from backend.user_storage import apply_user_defaults, is_local_mode, save_upload, workspace_info  # noqa: E402

FRONT = ROOT / "front"

app = FastAPI(title="Opto Automações", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(milagre_router)

if FRONT.is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONT)), name="assets")

SERVICES = {
    "documentos": {
        "id": "documentos",
        "nome": "Download de Documentos",
        "descricao": "Baixa PDFs de páginas de transparência e organiza por tipo e ano.",
        "pagina": "/documentos.html",
        "icone": "01",
    },
    "categorias": {
        "id": "categorias",
        "nome": "Download por Categoria",
        "descricao": "Varre categorias WordPress e baixa PDFs de cada post.",
        "pagina": "/categorias.html",
        "icone": "02",
    },
    "normas": {
        "id": "normas",
        "nome": "Extração Pro",
        "descricao": "Leis, atos, matérias e documentos — Prefeitura ou Câmara, com nomeação automática.",
        "pagina": "/normas.html",
        "icone": "03",
    },
    "licitacoes": {
        "id": "licitacoes",
        "nome": "Licitações",
        "descricao": "Baixa anexos de licitações CR2, extrai valores e preenche planilha.",
        "pagina": "/licitacoes.html",
        "icone": "04",
    },
    "repasses": {
        "id": "repasses",
        "nome": "Repasses",
        "descricao": "Planilha com links → baixa documentos, OCR e gera Repasses.xlsx.",
        "pagina": "/repasses.html",
        "icone": "10",
    },
    "contratos": {
        "id": "contratos",
        "nome": "Contratos / Aditivos",
        "descricao": "Coleta contratos e aditivos do Governo Transparente, baixa PDFs e gera planilha.",
        "pagina": "/contratos.html",
        "icone": "09",
    },
    "publicacao": {
        "id": "publicacao",
        "nome": "Publicação CR2",
        "descricao": "RGF, RREO, Balancete e Balanço no portal Bubble (Playwright).",
        "pagina": "/publicacao.html",
        "icone": "05",
    },
    "sessao": {
        "id": "sessao",
        "nome": "Publicação Sessão",
        "descricao": "Tipo, Data, Número, Pauta, Ata, Presença e Votações no portal CR2.",
        "pagina": "/sessao.html",
        "icone": "06",
    },
    "pub_repasses": {
        "id": "pub_repasses",
        "nome": "Publicação Repasses",
        "descricao": "Publica Repasses.xlsx no portal CR2 (Mês/Ano, Data, valores, arquivo).",
        "pagina": "/pub-repasses.html",
        "icone": "11",
    },
    "mapa": {
        "id": "mapa",
        "nome": "Mapa do Site",
        "descricao": "Cria páginas WordPress e atualiza o mapa do site.",
        "pagina": "/mapa.html",
        "icone": "07",
    },
    "dic_est_ter": {
        "id": "dic_est_ter",
        "nome": "Publicação Dic/Est/Ter",
        "descricao": "Dívida ativa, estagiários e terceirizados — planilhas Drive no portal CR2.",
        "pagina": "/dic-est-ter.html",
        "icone": "08",
    },
}


# Ocultos no hub (código permanece; não entram na API de jobs do painel).
# Quando prontos para o time: retire o id deste conjunto e inclua em HUBS no front.
SERVICES_OCULTOS = frozenset({"contratos", "dic_est_ter"})


class JobCreate(BaseModel):
    service_id: str
    config: dict = {}


class LoginBody(BaseModel):
    username: str
    password: str


class QueueReorderBody(BaseModel):
    order: list[str]


class CleanupBody(BaseModel):
    job_dirs: bool = True
    job_days: int = 0
    screenshots: bool = True
    ia_cache: bool = True
    upload_temp: bool = False
    upload_days: int = 7


SERVICE_LABELS = {
    "documentos": "Documentos",
    "categorias": "Categorias",
    "normas": "Extração Pro",
    "licitacoes": "Licitações",
    "repasses": "Extração Repasses",
    "contratos": "Contratos",
    "publicacao": "Publicação",
    "sessao": "Sessão",
    "pub_repasses": "Pub. Repasses",
    "mapa": "Mapa",
    "dic_est_ter": "Dic/Est/Ter",
}


def _job_summary(job) -> dict:
    d = job.to_dict(jobs)
    prog = d.get("progress") or {}
    return {
        "id": d["id"],
        "service_id": d["service_id"],
        "nome": SERVICE_LABELS.get(d["service_id"], d["service_id"]),
        "status": d["status"],
        "cancel_requested": d.get("cancel_requested"),
        "done": prog.get("done") or 0,
        "total": prog.get("total") or 0,
        "percent": prog.get("percent"),
        "label": prog.get("label") or "",
        "queue": d.get("queue"),
        "owner": d.get("owner"),
    }


def _assert_can_cancel(job, user) -> None:
    if not auth.can_cancel_job(user, job.owner):
        raise HTTPException(403, "Sem permissão para cancelar este processo.")


@app.get("/api/auth/config")
def auth_config():
    """Modo de login para o front (Supabase ou local)."""
    from backend import supabase_auth

    if supabase_auth.is_configured():
        return {
            "mode": "supabase",
            "supabase_url": supabase_auth.supabase_url(),
            "supabase_anon_key": supabase_auth.supabase_anon_key(),
        }
    if auth.is_enabled():
        return {"mode": "local"}
    return {"mode": "off"}


@app.get("/api/auth/me")
def auth_me(user=Depends(get_optional_user)):
    if not auth.is_enabled():
        return {"auth_required": False, "user": None}
    if not user:
        return {"auth_required": True, "user": None}
    pub = user.to_public()
    pub["panel_admin"] = auth.is_panel_admin(user)
    return {
        "auth_required": True,
        "user": pub,
    }


@app.post("/api/auth/login")
def auth_login(body: LoginBody):
    if not auth.is_enabled():
        raise HTTPException(400, "Autenticação não configurada neste servidor.")
    if auth.is_supabase():
        raise HTTPException(
            400,
            "Este servidor usa login Supabase (e-mail). Use a tela de login.",
        )
    sess = auth.login(body.username.strip(), body.password)
    if not sess:
        raise HTTPException(401, "Usuário ou senha inválidos.")
    return {
        "ok": True,
        "token": sess.token,
        "user": {"username": sess.username, "role": sess.role},
    }


@app.post("/api/auth/logout")
def auth_logout(authorization: str | None = None):
    auth.logout(auth.bearer_token(authorization))
    return {"ok": True}


@app.get("/api/health")
def health(user=Depends(get_optional_user)):
    """Saúde do servidor + fila (pill Online)."""
    snap = jobs.queue_snapshot()
    ativo = jobs.job_ativo()
    payload = {
        "ok": True,
        "auth_required": auth.is_enabled(),
        "local_mode": is_local_mode(),
        "user": (
            user.to_public() if user else None
        ),
        "job_timeout_s": JOB_TIMEOUT_S,
        "ativos": jobs.ativos(),
        "running": snap["running"],
        "pending": snap["pending"],
        "max_concurrent": snap["max_concurrent"],
        "max_queue": snap["max_queue"],
        "queue": snap,
        "ativo": None,
        "running_jobs": [
            _job_summary(j) for j in jobs.running_jobs()
        ],
    }
    if ativo is not None:
        payload["ativo"] = _job_summary(ativo)
    if user:
        my_jobs: list[dict] = []
        for mine in jobs.user_jobs_for_owner(user.username):
            summary = _job_summary(mine)
            summary["status"] = mine.status.value
            if mine.status.value == "pending":
                summary["queue_position"] = jobs.queue_position(mine.id)
            my_jobs.append(summary)
        payload["my_jobs"] = my_jobs
        payload["my_job"] = my_jobs[0] if my_jobs else None
    return payload


@app.get("/api/services")
def list_services():
    return [s for s in SERVICES.values() if s["id"] not in SERVICES_OCULTOS]


@app.get("/api/jobs")
def list_jobs():
    return jobs.list_jobs()


@app.get("/api/jobs/downloads-ready")
def jobs_downloads_ready(user=Depends(require_user)):
    """ZIPs prontos para download (mesmo se o usuário saiu da página do job)."""
    admin = auth.is_panel_admin(user) if auth.is_enabled() else True
    owner = user.username if auth.is_enabled() else None
    items = jobs.list_downloads_ready(owner, admin=admin)
    labels = SERVICE_LABELS
    return {
        "downloads": [
            {
                **row,
                "nome": labels.get(row["service_id"], row["service_id"]),
            }
            for row in items
        ]
    }


@app.get("/api/queue")
def get_queue():
    return jobs.queue_snapshot()


@app.post("/api/jobs/cancel-active")
def cancel_active_job(user=Depends(require_user)):
    """Cancela processo em andamento (do usuário ou qualquer se admin)."""
    with jobs._lock:
        alive = [
            j
            for j in jobs._jobs.values()
            if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
        ]
    if auth.is_enabled() and user.role != "admin" and not auth.is_panel_admin(user):
        alive = [j for j in alive if j.owner in (None, user.username)]
    alive.sort(key=lambda j: j.started_at or j.created_at, reverse=True)
    job = alive[0] if alive else None
    if not job:
        return {
            "ok": True,
            "estava_rodando": False,
            "msg": "Nenhuma fila ativa (estado liberado).",
        }
    _assert_can_cancel(job, user)
    jobs.cancel(job.id)
    return {
        "ok": True,
        "estava_rodando": True,
        "job_id": job.id,
        "status": job.status.value,
        "cancel_requested": job.cancel_requested,
        "msg": "Cancelamento solicitado — a fila deste processo sera interrompida.",
    }


@app.post("/api/jobs/cancel-all-pending")
def cancel_all_pending(_admin=Depends(require_admin)):
    n = jobs.cancel_all_pending()
    return {"ok": True, "cancelados": n, "msg": "{0} job(s) removido(s) da fila.".format(n)}


@app.post("/api/queue/reorder")
def reorder_queue(body: QueueReorderBody, _admin=Depends(require_admin)):
    if not body.order:
        raise HTTPException(400, "Informe a ordem dos jobs.")
    final = jobs.reorder_pending(body.order)
    return {"ok": True, "order": final, "queue": jobs.queue_snapshot()}


@app.on_event("startup")
def _startup_resume_queue():
    auth.reload_users()
    restored = jobs.restore_from_disk()
    jobs.resume_queue(dispatch)
    if restored:
        import logging

        logging.getLogger("uvicorn.error").info(
            "Fila restaurada: %s job(s) pending após reinício.", restored
        )


def _assert_can_access_job(job, user) -> None:
    if not auth.is_enabled():
        return
    if user.role == "admin" or auth.is_panel_admin(user):
        return
    if job.owner not in (None, user.username):
        raise HTTPException(403, "Sem permissão para acessar este processo.")


@app.get("/api/workspace")
def get_workspace(user=Depends(require_user)):
    """Pastas do usuário (uploads + saída padrão). Modo local: pastas Windows."""
    owner = user.username if auth.is_enabled() else None
    if is_local_mode():
        return {
            "ok": True,
            "local_mode": True,
            "username": "local",
            "output_dir": r"C:\Downloads",
            "uploads_dir": "",
            "root_dir": "",
        }
    return {"ok": True, "local_mode": False, **workspace_info(owner)}


@app.post("/api/uploads")
async def upload_file(
    user=Depends(require_user),
    file: UploadFile = File(...),
    extract: str = Form("false"),
):
    """Recebe planilha ou ZIP; opcionalmente extrai ZIP na pasta do usuário."""
    owner = user.username if auth.is_enabled() else None
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Arquivo vazio.")
    do_extract = str(extract).strip().lower() in ("1", "true", "yes", "on")
    try:
        meta = save_upload(
            owner,
            file.filename or "arquivo",
            raw,
            extract=do_extract,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, **meta}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user=Depends(require_user)):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Processo não encontrado")
    _assert_can_access_job(job, user)
    return {**job.to_dict(jobs), "logs": job.logs[-200:]}


@app.post("/api/jobs")
def create_job(body: JobCreate, user=Depends(require_user)):
    if body.service_id not in SERVICES or body.service_id in SERVICES_OCULTOS:
        raise HTTPException(400, "Serviço inválido")
    owner = user.username if auth.is_enabled() else None
    config = apply_user_defaults(body.config, owner)
    try:
        job = jobs.enqueue(body.service_id, config, dispatch, owner=owner)
    except QueueFullError as exc:
        raise HTTPException(503, str(exc)) from exc
    meta = jobs.queue_meta(job)
    return {
        "job_id": job.id,
        "status": job.status.value,
        "queue": meta,
        "owner": job.owner,
    }


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user=Depends(require_user)):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Processo não encontrado")
    _assert_can_cancel(job, user)
    job = jobs.cancel(job_id)
    return {
        "ok": True,
        "job_id": job.id,
        "status": job.status.value,
        "cancel_requested": job.cancel_requested,
        "msg": "Cancelamento solicitado — a fila deste processo sera interrompida.",
    }


@app.get("/api/jobs/{job_id}/logs/stream")
async def stream_logs(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Processo não encontrado")


    async def gen():
        q = job.subscribe()
        while True:
            try:
                entry = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: q.get(timeout=25)
                )
                yield "data: {0}\n\n".format(json.dumps(entry, ensure_ascii=False))
            except Exception:
                if job.status in (
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                ):
                    yield "data: {0}\n\n".format(json.dumps({"level": "done", "msg": "— fim —"}))
                    break
                yield ": keepalive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str, user=Depends(require_user)):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Processo não encontrado")
    _assert_can_access_job(job, user)

    zip_path = job.result.get("zip")
    if not zip_path or not Path(zip_path).is_file():
        build_download_zip(job)
        zip_path = job.result.get("zip")
    if zip_path and Path(zip_path).is_file():
        svc = SERVICE_LABELS.get(job.service_id, job.service_id)
        fname = "opto-{0}-{1}.zip".format(svc.replace(" ", "-").lower(), job_id)
        return FileResponse(
            zip_path,
            filename=fname,
            media_type="application/zip",
        )
    raise HTTPException(404, "Nenhum arquivo para download")


def _page(name: str):
    path = FRONT / name
    if path.is_file():
        return FileResponse(path, media_type="text/html; charset=utf-8")
    raise HTTPException(404)


@app.get("/")
def index():
    return _page("index.html")


@app.get("/extrair.html")
def page_extrair():
    return _page("extrair.html")


@app.get("/publicar.html")
def page_publicar():
    return _page("publicar.html")


@app.get("/documentos.html")
def page_documentos():
    return _page("documentos.html")


@app.get("/categorias.html")
def page_categorias():
    return _page("categorias.html")


@app.get("/normas.html")
def page_normas():
    return _page("normas.html")


@app.get("/licitacoes.html")
def page_licitacoes():
    return _page("licitacoes.html")


@app.get("/repasses.html")
def page_repasses():
    return _page("repasses.html")


@app.get("/contratos.html")
def page_contratos():
    return _page("contratos.html")


@app.get("/publicacao.html")
def page_publicacao():
    return _page("publicacao.html")


@app.get("/sessao.html")
def page_sessao():
    return _page("sessao.html")


@app.get("/pub-repasses.html")
def page_pub_repasses():
    return _page("pub-repasses.html")


@app.get("/mapa.html")
def page_mapa():
    return _page("mapa.html")


@app.get("/dic-est-ter.html")
def page_dic_est_ter():
    return _page("dic-est-ter.html")


@app.get("/api/admin/overview")
def admin_overview(_admin=Depends(require_admin)):
    """Dados agregados para o painel admin."""
    snap = jobs.admin_snapshot()
    ativo = jobs.job_ativo()
    queue = jobs.queue_snapshot()
    payload = {
        "ok": True,
        "version": app.version,
        "max_ativos": jobs.MAX_ATIVOS,
        "max_queue": jobs.MAX_QUEUE,
        "job_timeout_s": JOB_TIMEOUT_S,
        "auth_required": auth.is_enabled(),
        "ativos": jobs.ativos(),
        "running": jobs.running_count(),
        "pending": jobs.pending_count(),
        "queue": queue,
        "stats": snap,
        "service_labels": SERVICE_LABELS,
        "disk": jobs.disk_usage_jobs(),
        "services": list(SERVICES.values()),
        "services_ocultos": sorted(SERVICES_OCULTOS),
        "ativo": None,
        "running_jobs": [_job_summary(j) for j in jobs.running_jobs()],
    }
    if ativo is not None:
        payload["ativo"] = _job_summary(ativo)
    payload["cleanup_preview"] = cleanup.preview(jobs)
    return payload


@app.get("/api/admin/cleanup/preview")
def admin_cleanup_preview(
    job_days: int = 0,
    upload_days: int = 7,
    _admin=Depends(require_admin),
):
    return cleanup.preview(jobs, job_days=job_days, upload_days=upload_days)


@app.post("/api/admin/cleanup")
def admin_cleanup_run(body: CleanupBody, _admin=Depends(require_admin)):
    """Remove jobs antigos, screenshots, cache IA, etc."""
    result = cleanup.run_cleanup(
        jobs,
        job_dirs=body.job_dirs,
        job_days=body.job_days,
        screenshots=body.screenshots,
        ia_cache=body.ia_cache,
        upload_temp=body.upload_temp,
        upload_days=body.upload_days,
    )
    result["disk"] = jobs.disk_usage_jobs()
    result["cleanup_preview"] = cleanup.preview(
        jobs, job_days=body.job_days, upload_days=body.upload_days
    )
    return result


@app.get("/login.html")
def page_login():
    return _page("login.html")


@app.get("/login")
def redirect_login():
    return RedirectResponse(url="/login.html", status_code=302)


@app.get("/admin")
def redirect_admin():
    return RedirectResponse(url="/admin.html", status_code=302)


@app.get("/admin.html")
def page_admin():
    return _page("admin.html")




if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8765, reload=True)
