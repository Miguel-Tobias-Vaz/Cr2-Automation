"""Configuração do painel (variáveis de ambiente)."""

from __future__ import annotations

import os

# Slots simultâneos (jobs em execução)
MAX_CONCURRENT = max(1, int(os.getenv("OPTO_MAX_JOBS", "4")))

# Limite de jobs pending + running na memória
MAX_QUEUE = max(MAX_CONCURRENT, int(os.getenv("OPTO_MAX_QUEUE", "20")))

# Serviços com Playwright — rodam em subprocesso isolado
BROWSER_SERVICES = frozenset(
    {
        "publicacao",
        "sessao",
        "pub_repasses",
        "contratos",
        "dic_est_ter",
    }
)

# Desligar subprocesso (debug): OPTO_SUBPROCESS=0
USE_SUBPROCESS = os.getenv("OPTO_SUBPROCESS", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)

# Timeout automático por job running (0 = desligado). Ex.: 21600 = 6 h
JOB_TIMEOUT_S = max(0, int(os.getenv("OPTO_JOB_TIMEOUT_S", "0")))

# Downloads HTTP paralelos nos scripts de extração (documentos, etc.)
DOWNLOAD_WORKERS = max(1, min(12, int(os.getenv("OPTO_DOWNLOAD_WORKERS", "4"))))

