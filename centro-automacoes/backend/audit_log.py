"""Registro de auditoria append-only (admin / segurança)."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "data" / "audit"
AUDIT_FILE = AUDIT_DIR / "actions.jsonl"

_lock = threading.Lock()


def _ensure() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        AUDIT_DIR.chmod(0o750)
    except OSError:
        pass


def log(action: str, *, user: str | None = None, **extra: Any) -> None:
    """Grava linha JSONL — falha silenciosa se disco indisponível."""
    entry: dict[str, Any] = {
        "t": time.time(),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "action": action,
    }
    if user:
        entry["user"] = user
    for k, v in extra.items():
        if v is not None:
            entry[k] = v
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    try:
        _ensure()
        with _lock:
            with open(AUDIT_FILE, "a", encoding="utf-8") as fh:
                fh.write(line)
        try:
            AUDIT_FILE.chmod(0o640)
        except OSError:
            pass
    except OSError:
        pass


def tail(limit: int = 50) -> list[dict[str, Any]]:
    if not AUDIT_FILE.is_file():
        return []
    try:
        lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for raw in lines[-limit:]:
        try:
            row = json.loads(raw)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out
