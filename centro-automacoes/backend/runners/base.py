"""Utilitários para executar scripts da pasta automacoes/."""

from __future__ import annotations

import importlib.util
import io
import sys
import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
AUTOMACOES = PROJECT_ROOT / "automacoes"

SCRIPTS = {
    "documentos": AUTOMACOES / "download-documentos" / "script.py",
    "categorias": AUTOMACOES / "download-categorias" / "script.py",
    "normas": AUTOMACOES / "download-normas" / "script.py",
    "publicacao": AUTOMACOES / "publicacao-cr2" / "script.py",
    "mapa": AUTOMACOES / "mapa-site" / "script.py",
}


class _Tee(io.TextIOBase):
    def __init__(self, original, callback):
        self._original = original
        self._callback = callback
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._original.write(s)
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._callback(line)
        return len(s)

    def flush(self) -> None:
        self._original.flush()
        if self._buf.strip():
            self._callback(self._buf.rstrip())
            self._buf = ""


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("Não foi possível carregar: {0}".format(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def apply_globals(mod: ModuleType, mapping: dict) -> None:
    for key, val in mapping.items():
        if val is not None:
            setattr(mod, key, val)


def run_main_with_logs(job, mod: ModuleType, fn_name: str = "main") -> None:
    fn = getattr(mod, fn_name, None)
    if not fn:
        raise AttributeError("Função {0} não encontrada".format(fn_name))

    def on_line(line: str) -> None:
        low = line.lower()
        # "Erros: 0" no resumo não é falha
        if "erros:" in low and "erros: 0" in low:
            job.emit("info", line)
        elif "[erro]" in low or low.startswith("erro") or " error" in low:
            job.emit("error", line)
        elif "pulado" in low or "aviso" in low:
            job.emit("warn", line)
        elif "[ok]" in low or "conclu" in low:
            job.emit("ok", line)
        else:
            job.emit("info", line)

    tee_out = _Tee(sys.stdout, on_line)
    tee_err = _Tee(sys.stderr, on_line)
    with redirect_stdout(tee_out), redirect_stderr(tee_err):
        fn()
    tee_out.flush()
    tee_err.flush()
