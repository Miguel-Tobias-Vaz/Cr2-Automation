"""Opto Automações — API."""

from __future__ import annotations

import asyncio
import json
import os
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
from backend.job_output import ZIP_LOGIC_VERSION, build_download_zip  # noqa: E402
from backend import cleanup  # noqa: E402
from backend import audit_log  # noqa: E402
from backend.milagre_routes import router as milagre_router  # noqa: E402
from backend.runners import dispatch  # noqa: E402
from backend.state import jobs  # noqa: E402
from backend.user_storage import (
    apply_user_defaults,
    delete_workspace_path,
    is_local_mode,
    list_workspace_files,
    mkdir_workspace,
    output_publicacao_hints,
    save_upload,
    workspace_info,
)

FRONT = ROOT / "front"


def _cors_origins() -> list[str]:
    raw = os.getenv("OPTO_CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    if is_local_mode():
        return ["*"]
    return []


app = FastAPI(title="Opto Automações", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)
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


def _owner_short_name(owner: str | None) -> str:
    """Nome curto do usuário para rótulos de download (ex.: admin2)."""
    raw = (owner or "local").strip()
    if "@" in raw:
        raw = raw.split("@", 1)[0].strip()
    return raw or "local"


def _owners_match(owner: str | None, username: str | None) -> bool:
    if not owner or not username:
        return False
    return owner.strip().lower() == username.strip().lower()


def _service_download_base(service_id: str) -> str:
    label = SERVICE_LABELS.get(service_id, service_id)
    if label.lower().startswith("baixar "):
        return label
    return "Baixar {0}".format(label)


def download_display_name(service_id: str, owner: str | None = None) -> str:
    """Ex.: 'Baixar Extração Pro - admin2'."""
    return "{0} - {1}".format(
        _service_download_base(service_id),
        _owner_short_name(owner),
    )


def download_filename(service_id: str, owner: str | None, job_id: str) -> str:
    """Nome do arquivo ZIP baixado, com o usuário no nome."""
    import re

    base = download_display_name(service_id, owner)
    safe = re.sub(r'[<>:"/\\|?*]', "", base).strip() or "download"
    # Evita nomes absurdamente longos; job_id curto só como fallback de unicidade
    if len(safe) > 120:
        safe = "{0}-{1}".format(safe[:100].rstrip(), (job_id or "")[:8])
    return "{0}.zip".format(safe)


def _job_summary(job) -> dict:
    d = job.to_dict(jobs)
    prog = d.get("progress") or {}
    owner = d.get("owner")
    return {
        "id": d["id"],
        "service_id": d["service_id"],
        "nome": download_display_name(d["service_id"], owner),
        "status": d["status"],
        "cancel_requested": d.get("cancel_requested"),
        "done": prog.get("done") or 0,
        "total": prog.get("total") or 0,
        "percent": prog.get("percent"),
        "label": prog.get("label") or "",
        "queue": d.get("queue"),
        "owner": owner,
    }


def _user_is_admin(user) -> bool:
    return user.role == "admin" or auth.is_panel_admin(user)


def _sees_all_jobs(user) -> bool:
    """Só o admin principal do painel vê processos de outros usuários."""
    return auth.is_panel_admin(user)


def _health_payload(user) -> dict:
    """Saúde + fila — anônimo só vê mínimo quando auth está ativa."""
    if auth.is_enabled() and not user:
        return {
            "ok": True,
            "auth_required": True,
            "local_mode": is_local_mode(),
            "user": None,
        }

    sees_all = bool(user and _sees_all_jobs(user))
    username = user.username if user else "local"
    if auth.is_enabled() and user:
        snap = jobs.queue_snapshot_for_user(username, is_admin=sees_all)
    else:
        snap = jobs.queue_snapshot()

    # Nunca expor o "ativo" de outro usuário no painel pessoal (nem para role admin).
    ativo = jobs.job_ativo()
    if auth.is_enabled() and user and ativo:
        if not _owners_match(ativo.owner, user.username):
            own = jobs.user_job_for_owner(user.username)
            ativo = own if own and own.status in (
                JobStatus.RUNNING,
                JobStatus.PENDING,
            ) else None

    payload: dict = {
        "ok": True,
        "auth_required": auth.is_enabled(),
        "local_mode": is_local_mode(),
        "user": user.to_public() if user else None,
        "job_timeout_s": JOB_TIMEOUT_S,
        "ativos": snap["running"] + snap["pending"],
        "running": snap["running"],
        "pending": snap["pending"],
        "max_concurrent": snap["max_concurrent"],
        "max_queue": snap["max_queue"],
        "queue": snap,
        "ativo": None,
        "running_jobs": [],
    }

    if auth.is_enabled() and user:
        visible_running = jobs.running_jobs()
        if not sees_all:
            visible_running = [
                j for j in visible_running if _owners_match(j.owner, user.username)
            ]
        payload["running_jobs"] = [_job_summary(j) for j in visible_running]
    elif not auth.is_enabled():
        payload["running_jobs"] = [_job_summary(j) for j in jobs.running_jobs()]

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
    audit_log.log("auth.login", user=sess.username)
    return {
        "ok": True,
        "token": sess.token,
        "user": {"username": sess.username, "role": sess.role},
    }


@app.post("/api/auth/logout")
def auth_logout(authorization: str | None = None):
    auth.logout(auth.bearer_token(authorization))
    return {"ok": True}


def _assert_can_cancel(job, user) -> None:
    if not auth.can_cancel_job(user, job.owner):
        raise HTTPException(403, "Sem permissão para cancelar este processo.")


@app.get("/api/health")
def health(user=Depends(get_optional_user)):
    """Saúde do servidor + fila (pill Online)."""
    return _health_payload(user)


@app.get("/api/services")
def list_services():
    return [s for s in SERVICES.values() if s["id"] not in SERVICES_OCULTOS]


@app.get("/api/jobs")
def list_jobs(user=Depends(require_user)):
    return jobs.list_jobs_for_user(
        user.username, is_admin=_sees_all_jobs(user)
    )


@app.get("/api/jobs/downloads-ready")
def jobs_downloads_ready(user=Depends(require_user)):
    """ZIPs prontos para download — apenas jobs do usuário logado."""
    owner = user.username if auth.is_enabled() else None
    items = jobs.list_downloads_ready(owner)
    return {
        "downloads": [
            {
                **row,
                "nome": download_display_name(row["service_id"], row.get("owner") or owner),
                "arquivo": download_filename(
                    row["service_id"], row.get("owner") or owner, row["id"]
                ),
            }
            for row in items
        ]
    }


@app.get("/api/queue")
def get_queue(user=Depends(require_user)):
    return jobs.queue_snapshot_for_user(
        user.username, is_admin=_sees_all_jobs(user)
    )


@app.post("/api/jobs/cancel-active")
def cancel_active_job(user=Depends(require_user)):
    """Cancela todos os processos em andamento/na fila (do usuário; admin principal: todos)."""
    with jobs._lock:
        alive = [
            j
            for j in jobs._jobs.values()
            if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
        ]
    if auth.is_enabled() and not _sees_all_jobs(user):
        alive = [j for j in alive if _owners_match(j.owner, user.username)]
    if not alive:
        return {
            "ok": True,
            "estava_rodando": False,
            "cancelados": 0,
            "msg": "Nenhuma fila ativa (estado liberado).",
        }
    cancelled: list[str] = []
    for job in alive:
        _assert_can_cancel(job, user)
        jobs.cancel(job.id)
        cancelled.append(job.id)
    return {
        "ok": True,
        "estava_rodando": True,
        "cancelados": len(cancelled),
        "job_ids": cancelled,
        "msg": "Cancelamento solicitado em {0} processo(s).".format(len(cancelled)),
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
    if _sees_all_jobs(user):
        return
    if _owners_match(job.owner, user.username):
        return
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


@app.get("/api/workspace/files")
def get_workspace_files(path: str = "", user=Depends(require_user)):
    """Lista arquivos e pastas do workspace do usuário."""
    if is_local_mode():
        raise HTTPException(400, "Explorador de arquivos disponível apenas na VPS.")
    owner = user.username if auth.is_enabled() else None
    try:
        payload = list_workspace_files(owner, path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, **payload}


@app.get("/api/workspace/output-hints")
def get_output_hints(user=Depends(require_user)):
    """Pastas RGF/RREO/etc. detectadas em output/ (extrações anteriores)."""
    if is_local_mode():
        return {"ok": True, "local_mode": True, "hints": {}}
    owner = user.username if auth.is_enabled() else None
    hints = output_publicacao_hints(owner)
    return {"ok": True, "hints": hints}


class WorkspaceMkdirBody(BaseModel):
    path: str


@app.post("/api/workspace/mkdir")
def post_workspace_mkdir(body: WorkspaceMkdirBody, user=Depends(require_user)):
    if is_local_mode():
        raise HTTPException(400, "Disponível apenas na VPS.")
    owner = user.username if auth.is_enabled() else None
    try:
        meta = mkdir_workspace(owner, body.path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, **meta}


@app.delete("/api/workspace/files")
def delete_workspace_file(path: str, user=Depends(require_user)):
    if is_local_mode():
        raise HTTPException(400, "Disponível apenas na VPS.")
    owner = user.username if auth.is_enabled() else None
    try:
        delete_workspace_path(owner, path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


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
    from backend.job_log import disk_job_payload, read_job_log_entries

    job = jobs.get(job_id)
    if job:
        _assert_can_access_job(job, user)
        logs = list(job.logs[-200:])
        if len(logs) < 5:
            disk_logs = read_job_log_entries(job.dir, limit=400)
            if len(disk_logs) > len(logs):
                logs = disk_logs[-400:]
        payload = {**job.to_dict(jobs), "logs": logs}
        if job.error and not any(
            (e.get("level") == "error" and job.error in str(e.get("msg") or ""))
            for e in logs[-20:]
        ):
            payload["logs"] = logs + [
                {"t": "", "level": "error", "msg": "Erro: {0}".format(job.error)}
            ]
        return payload

    # Job saiu da memória (restart) — tenta disco
    disk = disk_job_payload(job_id)
    if not disk:
        raise HTTPException(404, "Processo não encontrado")

    class _DiskJob:
        owner = disk.get("owner")

    _assert_can_access_job(_DiskJob(), user)
    return disk


@app.post("/api/jobs")
def create_job(body: JobCreate, user=Depends(require_user)):
    if body.service_id not in SERVICES or body.service_id in SERVICES_OCULTOS:
        raise HTTPException(400, "Serviço inválido")
    owner = user.username if auth.is_enabled() else None
    config = apply_user_defaults(body.config, owner, service_id=body.service_id)
    try:
        job = jobs.enqueue(body.service_id, config, dispatch, owner=owner)
    except QueueFullError as exc:
        raise HTTPException(503, str(exc)) from exc
    meta = jobs.queue_meta(job)
    audit_log.log(
        "job.create",
        user=user.username,
        job_id=job.id,
        service_id=body.service_id,
    )
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
    audit_log.log("job.cancel", user=user.username, job_id=job_id)
    return {
        "ok": True,
        "job_id": job.id,
        "status": job.status.value,
        "cancel_requested": job.cancel_requested,
        "msg": "Cancelamento solicitado — a fila deste processo sera interrompida.",
    }


@app.get("/api/jobs/{job_id}/logs/stream")
async def stream_logs(job_id: str, user=Depends(require_user)):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Processo não encontrado")
    _assert_can_access_job(job, user)


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
    if (
        not zip_path
        or not Path(zip_path).is_file()
        or job.result.get("_zip_v") != ZIP_LOGIC_VERSION
    ):
        build_download_zip(job)
        zip_path = job.result.get("zip")
    if zip_path and Path(zip_path).is_file():
        fname = download_filename(job.service_id, job.owner, job_id)
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


@app.get("/arquivos.html")
def page_arquivos():
    return _page("arquivos.html")


@app.get("/dic-est-ter.html")
def page_dic_est_ter():
    return _page("dic-est-ter.html")


@app.get("/api/admin/overview")
def admin_overview(_admin=Depends(require_admin)):
    """Dados agregados para o painel admin."""
    from backend.job_log import list_recent_disk_jobs

    snap = jobs.admin_snapshot()
    ativo = jobs.job_ativo()
    queue = jobs.queue_snapshot()
    # Junta histórico em memória com meta no disco (após restart)
    mem_ids = {j.get("id") for j in (snap.get("recent") or []) if j.get("id")}
    disk_recent = []
    for row in list_recent_disk_jobs(limit=40):
        if row["id"] in mem_ids:
            continue
        disk_recent.append(row)
    if disk_recent:
        combined = list(snap.get("recent") or []) + disk_recent
        combined.sort(
            key=lambda x: float(x.get("finished_at") or x.get("created_at") or 0),
            reverse=True,
        )
        snap = {**snap, "recent": combined[:40]}
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
    audit_log.log(
        "admin.cleanup",
        user=_admin.username,
        job_dirs=body.job_dirs,
        upload_temp=body.upload_temp,
    )
    return result


def _process_memory_mb() -> float | None:
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return None


@app.get("/api/admin/health-detail")
def admin_health_detail(_admin=Depends(require_admin)):
    """RAM, fila, disco e últimas ações (admin)."""
    disk = jobs.disk_usage_jobs()
    last_failed = None
    with jobs._lock:
        for j in jobs._jobs.values():
            if j.status == JobStatus.FAILED:
                if last_failed is None or (j.finished_at or 0) > (
                    last_failed.get("finished_at") or 0
                ):
                    last_failed = {
                        "id": j.id,
                        "service_id": j.service_id,
                        "error": j.error,
                        "finished_at": j.finished_at,
                        "owner": j.owner,
                    }
    return {
        "ok": True,
        "memory_mb": _process_memory_mb(),
        "running": jobs.running_count(),
        "pending": jobs.pending_count(),
        "max_concurrent": jobs.MAX_ATIVOS,
        "max_queue": jobs.MAX_QUEUE,
        "disk": disk,
        "last_failed_job": last_failed,
        "audit_tail": audit_log.tail(30),
    }


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
