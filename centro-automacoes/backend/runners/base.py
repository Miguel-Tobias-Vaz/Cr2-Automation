"""Utilitários para executar scripts da pasta automacoes/."""

from __future__ import annotations

import importlib.util
import io
import os
import re
import sys
import threading
import warnings
from pathlib import Path
from types import ModuleType

from backend.jobs import JobCancelled

# [3/40]  |  [3/40 · 12%]  |  [-> SESSAO] [3/40]  |  (3/40)  |  item 3/40  |  Total: 40
_RE_PROGRESSO_TOTAL = re.compile(
    r"(?:total|fila)\s*[:=]\s*(\d+)|"
    r"(\d+)\s+licita[cç][aã]o\(ões\)\s+a processar|"
    r"vamos processar\s+(\d+)\s+licita",
    re.I,
)
_RE_PROGRESSO_ITEM = re.compile(
    # [3/40]  ou  [3/40 · 12%]  ou  [3/40 - 12%]
    r"\[\s*(\d+)\s*/\s*(\d+)(?:\s*[·•.\-–—]\s*\d+\s*%?)?\s*\]|"
    r"(?:publicando|baixando|processando|item|sess[aã]o|pdf|licita[cç][aã]o)\s+(\d+)\s*(?:de|/)\s*(\d+)",
    re.I,
)

# Ruído de bibliotecas (torch / HF / transformers / tqdm) — não vai pro painel
_RE_LOG_NOISE = re.compile(
    r"(?:"
    r"UserWarning:|"
    r"FutureWarning:|"
    r"DeprecationWarning:|"
    r"torch\.quantize|"
    r"quantize_per_tensor|"
    r"Triggered internally at|"
    r"huggingface_hub|"
    r"HF Hub|"
    r"HF_TOKEN|"
    r"unauthenticated requests|"
    r"symlinks by default|"
    r"HF_HUB_DISABLE|"
    r"Developer Mode|"
    r"To support symlinks|"
    r"Caching files will still work|"
    r"torch_dtype is deprecated|"
    r"`dtype` instead|"
    r"\[transformers\]|"
    r"Loading weights:|"
    r"site-packages[/\\](?:torch|huggingface|transformers|easyocr|docling)|"
    r"^\s*w_ih\s*=|"
    r"warnings\.warn\(|"
    r"enable-your-device-for-development|"
    r"github\.com/pytorch|"
    r"how-to-cache|"
    r"docs\.microsoft\.com/en-us/windows|"
    r"It is strongly recommended to use|"
    r"torchvision|"
    r"pin_memory|"
    r"CUDA available|"
    r"Using CPU\.|"
    r"libpng warning|"
    r"\[\s*\d+%\s*\||"  # barras tqdm tipo |████|
    r"\|#+\|"
    r")",
    re.I,
)

_RE_TQDM_DONE = re.compile(
    r"Loading weights:\s*100%|"
    r"100%\s*\|",
    re.I,
)

# Mensagens úteis reescritas em português
_REWRITE_LOG = (
    (
        re.compile(r"Downloading detection model", re.I),
        "Baixando modelo OCR de detecção (1ª vez — pode demorar)…",
    ),
    (
        re.compile(r"Downloading recognition model", re.I),
        "Baixando modelo OCR de reconhecimento…",
    ),
    (
        re.compile(r"Downloading.*model.*please wait", re.I),
        "Baixando modelo OCR (1ª vez — pode demorar)…",
    ),
)


def _achar_raiz() -> Path:
    """Pasta que contém automacoes/ e centro-automacoes/ (robusto ao extrair ZIP)."""
    aqui = Path(__file__).resolve().parent
    for pasta in [aqui, *aqui.parents]:
        auto = pasta / "automacoes"
        centro = pasta / "centro-automacoes"
        if (auto / "download-licitacoes" / "script.py").is_file() and centro.is_dir():
            return pasta
        # fallback: só a pasta automacoes com o script
        if (auto / "download-licitacoes" / "script.py").is_file():
            return pasta
    # legado: 4 níveis acima de runners/base.py
    return Path(__file__).resolve().parent.parent.parent.parent


PROJECT_ROOT = _achar_raiz()
AUTOMACOES = PROJECT_ROOT / "automacoes"

SCRIPTS = {
    "documentos": AUTOMACOES / "download-documentos" / "script.py",
    "categorias": AUTOMACOES / "download-categorias" / "script.py",
    "normas": AUTOMACOES / "download-normas" / "script.py",
    "licitacoes": AUTOMACOES / "download-licitacoes" / "script.py",
    "contratos": AUTOMACOES / "raspar-contratos" / "main.py",
    "publicacao": AUTOMACOES / "publicacao-cr2" / "script.py",
    "sessao": AUTOMACOES / "publicacao-sessao" / "script.py",
    "mapa": AUTOMACOES / "mapa-site" / "script.py",
    "repasses": AUTOMACOES / "download-repasses" / "script.py",
    "pub_repasses": AUTOMACOES / "publicacao-repasses" / "script.py",
}


class _Tee(io.TextIOBase):
    def __init__(self, original, callback, *, echo: bool = True):
        self._original = original
        self._callback = callback
        self._echo = echo
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        if self._echo:
            try:
                self._original.write(s)
            except UnicodeEncodeError:
                safe = s.encode("ascii", errors="replace").decode("ascii")
                try:
                    self._original.write(safe)
                except Exception:
                    pass
        # tqdm usa \r — trata como quebra para filtrar progresso sujo
        self._buf += s.replace("\r\n", "\n").replace("\r", "\n")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._callback(line)
        return len(s)

    def flush(self) -> None:
        try:
            self._original.flush()
        except Exception:
            pass
        if self._buf.strip():
            self._callback(self._buf.rstrip())
            self._buf = ""


# Redirecionamento por thread — evita misturar stdout quando 2+ jobs rodam juntos.
_log_tls = threading.local()
_real_stdout = sys.stdout
_real_stderr = sys.stderr
_dispatch_installed = False


class _ThreadDispatchStream(io.TextIOBase):
    """Encaminha prints para o _Tee da thread atual."""

    def __init__(self, *, stderr: bool = False):
        self._stderr = stderr

    def _target(self) -> io.TextIOBase:
        key = "tee_err" if self._stderr else "tee_out"
        stream = getattr(_log_tls, key, None)
        if stream is not None:
            return stream
        return _real_stderr if self._stderr else _real_stdout

    def write(self, s: str) -> int:
        return self._target().write(s)

    def flush(self) -> None:
        self._target().flush()

    def fileno(self) -> int:
        return self._target().fileno()

    def isatty(self) -> bool:
        try:
            return self._target().isatty()
        except Exception:
            return False


def _ensure_thread_dispatch_streams() -> None:
    global _dispatch_installed, _real_stdout, _real_stderr
    if _dispatch_installed:
        return
    _real_stdout = sys.stdout
    _real_stderr = sys.stderr
    sys.stdout = _ThreadDispatchStream(stderr=False)
    sys.stderr = _ThreadDispatchStream(stderr=True)
    _dispatch_installed = True


def _limpar_linha_log(line: str, *, visto: set[str] | None = None) -> str | None:
    """
    Filtra ruído de libs e reescreve mensagens úteis.
    Retorna None para omitir a linha no painel.
    """
    raw = (line or "").strip()
    if not raw:
        return None

    # Barras de progresso intermediárias
    if re.search(r"\d+%\|", raw) or re.search(r"\|\s*\d+/\d+", raw):
        if _RE_TQDM_DONE.search(raw):
            msg = "Modelo OCR carregado."
            if visto is not None:
                if msg in visto:
                    return None
                visto.add(msg)
            return msg
        return None

    if _RE_LOG_NOISE.search(raw):
        return None

    # Stack / caminhos longos de pacotes
    if "site-packages" in raw.replace("\\", "/").lower():
        return None
    if re.match(r"^\s*File \".+\", line \d+", raw):
        return None

    for pat, texto in _REWRITE_LOG:
        if pat.search(raw):
            if visto is not None:
                if texto in visto:
                    return None
                visto.add(texto)
            return texto

    # Encurta caminhos absolutos no meio da mensagem
    cleaned = re.sub(
        r"[A-Za-z]:\\[^\s:]{40,}",
        lambda m: "…" + m.group(0)[-36:].replace("\\", "/"),
        raw,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if len(cleaned) > 420:
        cleaned = cleaned[:400].rstrip() + "…"
    return cleaned or None


def load_module(name: str, path: Path) -> ModuleType:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            "Script nao encontrado:\n  {0}\n\n"
            "Pacote incompleto ou pasta errada.\n"
            "Raiz detectada: {1}\n"
            "Confira se existe automacoes\\download-licitacoes\\script.py "
            "ao lado de centro-automacoes\\.".format(path, PROJECT_ROOT)
        )
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("Não foi possível carregar: {0}".format(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def apply_globals(mod: ModuleType, mapping: dict) -> None:
    for key, val in mapping.items():
        if val is not None:
            setattr(mod, key, val)


def _is_cancel_exc(exc: BaseException) -> bool:
    if isinstance(exc, JobCancelled):
        return True
    return type(exc).__name__ in ("Cancelado", "JobCancelled")


def _atualizar_progresso_do_log(job, line: str) -> None:
    """Extrai done/total de linhas tipo [3/40], [3/40 · 12%] ou Total: 40."""
    if not line or not hasattr(job, "set_progress"):
        return
    m_tot = _RE_PROGRESSO_TOTAL.search(line)
    if m_tot:
        try:
            total = next(int(g) for g in m_tot.groups() if g is not None)
            if total > 0 and (
                job.progress_total <= 0 or total >= job.progress_total
            ):
                job.set_progress(total=total)
        except (ValueError, StopIteration):
            pass

    m = _RE_PROGRESSO_ITEM.search(line)
    if not m:
        return
    grupos = [g for g in m.groups() if g is not None]
    if len(grupos) < 2:
        return
    try:
        done, total = int(grupos[0]), int(grupos[1])
    except ValueError:
        return
    if total <= 0 or done < 0 or done > max(total, 1) * 2:
        return
    # Ignora [1/2] workaround quando o job já tem fila maior (ex. 40 licitações).
    if job.progress_total > 0 and total < job.progress_total:
        return
    job.set_progress(done=done, total=total)


def run_main_with_logs(job, mod: ModuleType, fn_name: str = "main") -> None:
    fn = getattr(mod, fn_name, None)
    if not fn:
        raise AttributeError("Função {0} não encontrada".format(fn_name))

    def pedido_cancelado() -> bool:
        return bool(job.cancel_requested)

    setattr(mod, "pedido_cancelado", pedido_cancelado)

    # Menos ruído de Hugging Face / Transformers no painel
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    visto_msgs: set[str] = set()

    def on_line(line: str) -> None:
        raw = (line or "").strip()
        # Protocolo NDJSON do WorkerJob — não reprocessar (evita loop/aninhamento)
        if raw.startswith("{") and '"op"' in raw:
            return
        limpa = _limpar_linha_log(line, visto=visto_msgs)
        if limpa is None:
            return
        _atualizar_progresso_do_log(job, limpa)
        low = limpa.lower()
        # "Erros: 0" no resumo não é falha
        if "erros:" in low and "erros: 0" in low:
            job.emit("info", limpa)
        elif "[erro]" in low or low.startswith("erro") or " error" in low:
            # Falso positivo do Windows charmap no log
            if "charmap" in low and "codec" in low:
                job.emit("warn", limpa)
            else:
                job.emit("error", limpa)
        elif "pulado" in low or "aviso" in low or "cancelad" in low:
            job.emit("warn", limpa)
        elif "[ok]" in low or "conclu" in low or low.strip().startswith("✓") or " ✓ " in limpa:
            job.emit("ok", limpa)
        elif "etapa:" in low or low.startswith("──"):
            job.emit("info", limpa)
        elif limpa.startswith("Baixando modelo OCR") or limpa.startswith("Modelo OCR"):
            job.emit("info", limpa)
        else:
            job.emit("info", limpa)

    # No subprocesso, o emit já manda NDJSON em __stdout__; ecoar o print cru
    # duplicaria linhas no pai.
    protocol_job = type(job).__name__ == "WorkerJob"
    _ensure_thread_dispatch_streams()
    tee_out = _Tee(_real_stdout, on_line, echo=not protocol_job)
    tee_err = _Tee(_real_stderr, on_line, echo=not protocol_job)
    prev_out = getattr(_log_tls, "tee_out", None)
    prev_err = getattr(_log_tls, "tee_err", None)
    _log_tls.tee_out = tee_out
    _log_tls.tee_err = tee_err
    # Silencia UserWarning das libs enquanto o job roda (ainda filtramos no tee)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        warnings.simplefilter("ignore", FutureWarning)
        try:
            fn()
        except Exception as exc:
            if _is_cancel_exc(exc) or job.cancel_requested:
                job.cancel_requested = True
                return
            raise
        finally:
            tee_out.flush()
            tee_err.flush()
            _log_tls.tee_out = prev_out
            _log_tls.tee_err = prev_err

    if job.cancel_requested:
        return
    if hasattr(job, "set_progress") and job.progress_total > 0:
        if job.progress_done < job.progress_total:
            job.set_progress(label="Finalizando…")