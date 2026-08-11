"""Leitura de logs/meta de jobs no disco (histórico além da memória)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from backend.job_paths import find_job_dir, iter_all_job_dirs

_LOG_LINE_RE = re.compile(
    r"^(?P<t>\d{1,2}:\d{2}:\d{2})\s+\[(?P<level>[^\]]+)\]\s+(?P<msg>.*)$"
)


def owner_from_job_dir(job_dir: Path) -> str | None:
    """Extrai o username da pasta data/users/{owner}/jobs/{id}."""
    try:
        parts = Path(job_dir).resolve().parts
        for i, part in enumerate(parts):
            if part == "users" and i + 2 < len(parts) and parts[i + 2] == "jobs":
                return parts[i + 1]
    except (OSError, ValueError):
        pass
    return None


def read_job_log_entries(job_dir: Path | None, *, limit: int = 400) -> list[dict[str, str]]:
    """Lê job.log do disco (escrito por Job.emit)."""
    if not job_dir:
        return []
    path = Path(job_dir) / "job.log"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    out: list[dict[str, str]] = []
    for line in lines[-limit:]:
        m = _LOG_LINE_RE.match(line.strip())
        if m:
            out.append(
                {
                    "t": m.group("t"),
                    "level": m.group("level").strip(),
                    "msg": m.group("msg"),
                }
            )
        else:
            out.append({"t": "", "level": "info", "msg": line})
    return out


def read_job_meta(job_dir: Path | None) -> dict[str, Any]:
    """Lê meta.json se existir (status/result após conclusão)."""
    if not job_dir:
        return {}
    path = Path(job_dir) / "meta.json"
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_job_meta(job) -> None:
    """Persiste resumo do job para histórico após restart."""
    try:
        path = Path(job.dir) / "meta.json"
        payload = {
            "id": job.id,
            "service_id": job.service_id,
            "owner": job.owner,
            "status": job.status.value if hasattr(job.status, "value") else str(job.status),
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "error": job.error,
            "result": {
                k: v
                for k, v in (job.result or {}).items()
                if k not in ("zip",) and not str(k).startswith("_")
            },
            "cancel_requested": bool(job.cancel_requested),
            "progress": {
                "done": getattr(job, "progress_done", 0),
                "total": getattr(job, "progress_total", 0),
                "label": getattr(job, "progress_label", "") or "",
            },
            "saved_at": time.time(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def disk_job_payload(job_id: str, owner: str | None = None) -> dict[str, Any] | None:
    """Monta payload de job a partir do disco (meta + logs)."""
    job_dir = find_job_dir(job_id, owner)
    if not job_dir:
        return None
    meta = read_job_meta(job_dir)
    disk_owner = owner or meta.get("owner") or owner_from_job_dir(job_dir)
    logs = read_job_log_entries(job_dir)
    status = meta.get("status") or ("completed" if logs else "unknown")
    return {
        "id": job_id,
        "service_id": meta.get("service_id") or "unknown",
        "status": status,
        "created_at": meta.get("created_at"),
        "started_at": meta.get("started_at"),
        "finished_at": meta.get("finished_at"),
        "error": meta.get("error"),
        "result": meta.get("result") or {},
        "has_download": bool((job_dir / "download.zip").is_file()),
        "cancel_requested": bool(meta.get("cancel_requested")),
        "owner": disk_owner,
        "progress": meta.get("progress") or {},
        "from_disk": True,
        "logs": logs,
    }


def list_recent_disk_jobs(*, limit: int = 40) -> list[dict[str, Any]]:
    """Lista jobs recentes só do disco (para admin quando memória está vazia)."""
    items: list[dict[str, Any]] = []
    for job_dir in iter_all_job_dirs():
        meta = read_job_meta(job_dir)
        mtime = 0.0
        try:
            mtime = job_dir.stat().st_mtime
        except OSError:
            pass
        finished = float(meta.get("finished_at") or meta.get("saved_at") or mtime or 0)
        items.append(
            {
                "id": job_dir.name,
                "service_id": meta.get("service_id") or "unknown",
                "status": meta.get("status") or "unknown",
                "created_at": meta.get("created_at") or finished,
                "finished_at": meta.get("finished_at") or finished,
                "owner": meta.get("owner") or owner_from_job_dir(job_dir),
                "error": meta.get("error"),
                "result": meta.get("result") or {},
                "progress": meta.get("progress") or {},
                "from_disk": True,
            }
        )
    items.sort(key=lambda x: float(x.get("finished_at") or x.get("created_at") or 0), reverse=True)
    return items[:limit]
