"""Opto Automações — API."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.jobs import JobManager, JobStatus  # noqa: E402
from backend.milagre_routes import router as milagre_router  # noqa: E402
from backend.runners import dispatch  # noqa: E402

FRONT = ROOT / "front"
jobs = JobManager()

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


@app.get("/api/health")
def health():
    """
    Saúde do servidor + processo ativo (para o pill Online).
    """
    ativo = jobs.job_ativo()
    payload = {"ok": True, "ativos": jobs.ativos(), "ativo": None}
    if ativo is not None:
        d = ativo.to_dict()
        labels = {
            "documentos": "Documentos",
            "categorias": "Categorias",
            "normas": "Extração Pro",
            "licitacoes": "Licitações",
            "contratos": "Contratos",
            "publicacao": "Publicação",
            "sessao": "Sessão",
            "mapa": "Mapa",
            "dic_est_ter": "Dic/Est/Ter",
        }
        prog = d.get("progress") or {}
        payload["ativo"] = {
            "id": d["id"],
            "service_id": d["service_id"],
            "nome": labels.get(d["service_id"], d["service_id"]),
            "status": d["status"],
            "cancel_requested": d.get("cancel_requested"),
            "done": prog.get("done") or 0,
            "total": prog.get("total") or 0,
            "percent": prog.get("percent"),
            "label": prog.get("label") or "",
        }
    return payload


@app.get("/api/services")
def list_services():
    return [s for s in SERVICES.values() if s["id"] not in SERVICES_OCULTOS]


@app.get("/api/jobs")
def list_jobs():
    return jobs.list_jobs()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Processo não encontrado")
    return {**job.to_dict(), "logs": job.logs[-200:]}


@app.post("/api/jobs")
def create_job(body: JobCreate):
    if body.service_id not in SERVICES or body.service_id in SERVICES_OCULTOS:
        raise HTTPException(400, "Serviço inválido")
    if jobs.ativos() >= jobs.MAX_ATIVOS:
        raise HTTPException(
            409,
            "Já existe um processo em andamento. Cancele ou aguarde terminar.",
        )
    job = jobs.create(body.service_id, body.config)
    jobs.save_config(job)
    jobs.start(job, dispatch)
    return {"job_id": job.id, "status": job.status.value}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = jobs.cancel(job_id)
    if not job:
        raise HTTPException(404, "Processo não encontrado")

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
def download_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Processo não encontrado")

    zip_path = job.result.get("zip")
    if zip_path and Path(zip_path).is_file():
        return FileResponse(zip_path, filename="cr2-{0}.zip".format(job_id))
    raise HTTPException(404, "Nenhum arquivo para download")


def _page(name: str):
    path = FRONT / name
    if path.is_file():
        return FileResponse(path)
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


@app.get("/contratos.html")
def page_contratos():
    return _page("contratos.html")


@app.get("/publicacao.html")
def page_publicacao():
    return _page("publicacao.html")


@app.get("/sessao.html")
def page_sessao():
    return _page("sessao.html")


@app.get("/mapa.html")
def page_mapa():
    return _page("mapa.html")


@app.get("/dic-est-ter.html")
def page_dic_est_ter():
    return _page("dic-est-ter.html")


@app.get("/transparencia.html")
def redirect_transparencia():
    return RedirectResponse(url="/dic-est-ter.html", status_code=302)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8765, reload=True)
