# =====================================================================
#  Runtime de jobs — cache CSV, progresso, log em arquivo, estado em disco
#  (o worker do servidor usa isto; o browser so observa)
# =====================================================================

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

PASTA = Path(__file__).resolve().parent
PASTA_CACHE = PASTA / "data" / "cache"
PASTA_JOBS = PASTA / "runtime" / "jobs"
PASTA_LOGS = PASTA / "runtime" / "logs"

PROGRESSO_A_CADA_LINHAS = 5000
LOG_MEMORIA_MAX = 400
CACHE_CSV_MAX_IDADE_S = 6 * 3600  # 6h


_lock = threading.RLock()
_estado = {
    "running": False,
    "cancel_requested": False,
    "job_id": None,
    "logs": [],  # ultimas linhas para SSE
    "subscribers": [],
    "resumo": None,
    "arquivo_nao_publicadas": None,
    "log_path": None,
    "progresso": {
        "total": 0,
        "publicadas": 0,
        "erros": 0,
        "retries": 0,
        "chunk_atual": 0,
        "chunk_total": 0,
        "fase": "parado",
        "iniciado_em": None,
        "eta_s": None,
        "linhas_processadas": 0,
        "msg": "",
    },
}


def _garantir_pastas():
    PASTA_CACHE.mkdir(parents=True, exist_ok=True)
    PASTA_JOBS.mkdir(parents=True, exist_ok=True)
    PASTA_LOGS.mkdir(parents=True, exist_ok=True)


def snapshot():
    with _lock:
        return {
            "running": _estado["running"],
            "job_id": _estado["job_id"],
            "logs": list(_estado["logs"][-LOG_MEMORIA_MAX:]),
            "resumo": _estado["resumo"],
            "arquivo_nao_publicadas": _estado["arquivo_nao_publicadas"],
            "progresso": dict(_estado["progresso"]),
            "cancel_requested": _estado["cancel_requested"],
        }


def pedido_cancelado():
    with _lock:
        return bool(_estado["cancel_requested"])


def liberar(motivo="Cancelar fila"):
    """Pede cancelamento da fila em andamento (o worker para no proximo item)."""
    with _lock:
        estava = _estado["running"]
        _estado["cancel_requested"] = True
        if _estado["resumo"] is None:
            _estado["resumo"] = {"ok": False, "cancelado": True}
        prog = _estado["progresso"]
        if estava:
            prog["fase"] = "cancelando"
            prog["msg"] = motivo
        else:
            # Nada ativo: limpa estado residual (desbloqueio)
            _estado["running"] = False
            prog["fase"] = "cancelado"
            prog["msg"] = motivo
        _persistir_unlocked()
    if estava:
        emit("warn", "{} — parando a fila deste processo...".format(motivo))
    else:
        emit("warn", "{} — nenhuma fila ativa (estado liberado).".format(motivo))
        emit("info", "— fim —")
    return estava


def iniciar_job(body_meta=None):
    _garantir_pastas()
    job_id = time.strftime("%Y%m%d_%H%M%S")
    log_path = PASTA_LOGS / "job_{}.log".format(job_id)
    with _lock:
        if _estado["running"]:
            return False
        _estado["running"] = True
        _estado["cancel_requested"] = False
        _estado["job_id"] = job_id
        _estado["logs"] = []
        _estado["resumo"] = None
        _estado["arquivo_nao_publicadas"] = None
        _estado["log_path"] = str(log_path)
        _estado["progresso"] = {
            "total": 0,
            "publicadas": 0,
            "erros": 0,
            "retries": 0,
            "chunk_atual": 0,
            "chunk_total": 0,
            "fase": "iniciando",
            "iniciado_em": time.time(),
            "eta_s": None,
            "linhas_processadas": 0,
            "msg": "Job {} iniciado".format(job_id),
            "meta": body_meta or {},
        }
        _persistir_unlocked()
    emit("info", "Worker job {} — continua mesmo se fechar o navegador.".format(job_id))
    return True


def finalizar(resumo=None):
    with _lock:
        _estado["running"] = False
        _estado["cancel_requested"] = False
        if resumo is not None:
            _estado["resumo"] = resumo
        prog = _estado["progresso"]
        if prog.get("fase") not in ("cancelado", "erro"):
            prog["fase"] = "concluido"
        prog["eta_s"] = 0
        prog["msg"] = "Concluido"
        _persistir_unlocked()
    emit("info", "— fim —")


def set_arquivo_nao_publicadas(path):
    with _lock:
        _estado["arquivo_nao_publicadas"] = str(path) if path else None
        _persistir_unlocked()


def atualizar_progresso(**kwargs):
    with _lock:
        prog = _estado["progresso"]
        prog.update({k: v for k, v in kwargs.items() if v is not None})
        # ETA simples: baseado em chunks ou linhas
        iniciado = prog.get("iniciado_em") or time.time()
        elapsed = max(0.1, time.time() - iniciado)
        ca, ct = prog.get("chunk_atual") or 0, prog.get("chunk_total") or 0
        lp, tot = prog.get("linhas_processadas") or 0, prog.get("total") or 0
        eta = None
        if ct > 0 and ca > 0 and ca < ct:
            por_chunk = elapsed / ca
            eta = int(por_chunk * (ct - ca))
        elif tot > 0 and lp > 0 and lp < tot:
            taxa = lp / elapsed
            if taxa > 0:
                eta = int((tot - lp) / taxa)
        prog["eta_s"] = eta
        _persistir_unlocked()
        # avisa subscribers so do progresso (leve)
        entry = {
            "t": time.strftime("%H:%M:%S"),
            "level": "progress",
            "msg": _fmt_progresso(prog),
            "progresso": dict(prog),
        }
        for q in list(_estado["subscribers"]):
            try:
                q.put_nowait(entry)
            except Exception:
                pass


def _fmt_progresso(p):
    return (
        "total={total} pub={publicadas} err={erros} retry={retries} "
        "chunk={chunk_atual}/{chunk_total} fase={fase}".format(**{
            "total": p.get("total") or 0,
            "publicadas": p.get("publicadas") or 0,
            "erros": p.get("erros") or 0,
            "retries": p.get("retries") or 0,
            "chunk_atual": p.get("chunk_atual") or 0,
            "chunk_total": p.get("chunk_total") or 0,
            "fase": p.get("fase") or "?",
        })
    )


def emit(level, msg, para_sse=True):
    """Log em arquivo sempre; memoria/SSE so se para_sse."""
    entry = {
        "t": time.strftime("%H:%M:%S"),
        "level": level,
        "msg": str(msg),
    }
    with _lock:
        log_path = _estado.get("log_path")
        if log_path:
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(
                        "{t} [{level}] {msg}\n".format(**entry)
                    )
            except Exception:
                pass
        if para_sse:
            _estado["logs"].append(entry)
            if len(_estado["logs"]) > LOG_MEMORIA_MAX:
                _estado["logs"] = _estado["logs"][-LOG_MEMORIA_MAX :]
            dead = []
            for q in _estado["subscribers"]:
                try:
                    q.put_nowait(entry)
                except Exception:
                    dead.append(q)
            for q in dead:
                try:
                    _estado["subscribers"].remove(q)
                except ValueError:
                    pass


def emit_progresso_linhas(processadas, total=None, a_cada=None):
    a_cada = a_cada or PROGRESSO_A_CADA_LINHAS
    if processadas and processadas % a_cada == 0:
        atualizar_progresso(
            linhas_processadas=processadas,
            total=total if total is not None else None,
            fase="validando",
            msg="{} linhas analisadas".format(processadas),
        )
        emit(
            "info",
            "{} linhas analisadas...".format(processadas),
            para_sse=True,
        )


def add_subscriber(q):
    with _lock:
        _estado["subscribers"].append(q)
        for entry in _estado["logs"][-200:]:
            try:
                q.put_nowait(entry)
            except Exception:
                pass
        # manda progresso atual
        try:
            q.put_nowait(
                {
                    "t": time.strftime("%H:%M:%S"),
                    "level": "progress",
                    "msg": _fmt_progresso(_estado["progresso"]),
                    "progresso": dict(_estado["progresso"]),
                }
            )
        except Exception:
            pass


def remove_subscriber(q):
    with _lock:
        try:
            _estado["subscribers"].remove(q)
        except ValueError:
            pass


def _persistir_unlocked():
    _garantir_pastas()
    job_id = _estado.get("job_id") or "atual"
    path = PASTA_JOBS / "job_atual.json"
    data = {
        "job_id": job_id,
        "running": _estado["running"],
        "progresso": _estado["progresso"],
        "resumo": _estado["resumo"],
        "arquivo_nao_publicadas": _estado["arquivo_nao_publicadas"],
        "log_path": _estado["log_path"],
        "atualizado_em": time.time(),
    }
    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def restaurar_ao_subir():
    """Se o servidor reiniciou no meio do job, marca como interrompido."""
    _garantir_pastas()
    path = PASTA_JOBS / "job_atual.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if data.get("running"):
        data["running"] = False
        prog = data.get("progresso") or {}
        prog["fase"] = "interrompido"
        prog["msg"] = "Servidor reiniciou — use Publicar de novo"
        data["progresso"] = prog
        data["resumo"] = {"ok": False, "interrompido": True}
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        with _lock:
            _estado["running"] = False
            _estado["progresso"] = prog
            _estado["resumo"] = data["resumo"]
            _estado["job_id"] = data.get("job_id")
            _estado["arquivo_nao_publicadas"] = data.get(
                "arquivo_nao_publicadas"
            )
            _estado["log_path"] = data.get("log_path")


def cache_key_drive(url_ou_id):
    raw = (url_ou_id or "").strip().encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def caminho_cache_csv(file_id_ou_url):
    _garantir_pastas()
    key = cache_key_drive(file_id_ou_url)
    return PASTA_CACHE / "{}.csv".format(key), PASTA_CACHE / "{}.meta.json".format(key)


def obter_csv_cache(url, file_id, max_idade_s=None):
    """Retorna Path do CSV em cache se ainda valido."""
    if max_idade_s is None:
        max_idade_s = CACHE_CSV_MAX_IDADE_S
    csv_path, meta_path = caminho_cache_csv(file_id or url)
    if not csv_path.is_file():
        return None
    idade = time.time() - csv_path.stat().st_mtime
    if idade > max_idade_s:
        return None
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("url") and url and meta["url"] != url:
                # mesma key improvavel; aceita
                pass
        except Exception:
            pass
    return csv_path


def salvar_csv_cache(url, file_id, data_bytes):
    csv_path, meta_path = caminho_cache_csv(file_id or url)
    csv_path.write_bytes(data_bytes)
    meta_path.write_text(
        json.dumps(
            {
                "url": url,
                "file_id": file_id,
                "salvo_em": time.time(),
                "bytes": len(data_bytes),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return csv_path


def formatar_eta(segundos):
    if segundos is None:
        return "—"
    s = int(max(0, segundos))
    if s < 60:
        return "{} s".format(s)
    m, s = divmod(s, 60)
    if m < 60:
        return "{} min".format(m + (1 if s >= 30 else 0))
    h, m = divmod(m, 60)
    return "{} h {} min".format(h, m)


# ---------------------------------------------------------------------
#  Checkpoint — retoma de onde parou (por tipo + linha da planilha)
# ---------------------------------------------------------------------


def caminho_checkpoint():
    return PASTA_JOBS / "checkpoint_publicacao.json"


def carregar_checkpoint():
    path = caminho_checkpoint()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def salvar_checkpoint_linha(kind, linha, publicadas_total=None):
    """Marca a ultima linha publicada com sucesso deste tipo."""
    _garantir_pastas()
    data = carregar_checkpoint()
    kinds = data.setdefault("kinds", {})
    kinds[str(kind)] = {
        "ultima_linha_ok": int(linha),
        "atualizado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if publicadas_total is not None:
        data["publicadas_total"] = int(publicadas_total)
    data["atualizado_em"] = time.strftime("%Y-%m-%d %H:%M:%S")
    caminho_checkpoint().write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def limpar_checkpoint():
    path = caminho_checkpoint()
    if path.is_file():
        try:
            path.unlink()
        except Exception:
            pass


def filtrar_fila_apos_checkpoint(itens, kind):
    """Remove itens com linha <= ultima publicada (retomada)."""
    if not itens:
        return itens
    info = (carregar_checkpoint().get("kinds") or {}).get(str(kind)) or {}
    ultima = info.get("ultima_linha_ok")
    if ultima is None:
        return itens
    ultima = int(ultima)
    return [it for it in itens if int(it.get("linha") or 0) > ultima]
