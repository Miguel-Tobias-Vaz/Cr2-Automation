"""Configuração central da automação de coleta de contratos/aditivos."""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos do projeto
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DADOS_DIR = BASE_DIR / "dados"
CONTRATOS_DIR = BASE_DIR / "contratos"
LOGS_DIR = BASE_DIR / "logs"
CHECKPOINT_DIR = BASE_DIR / "checkpoint"
CHECKPOINT_PATH = CHECKPOINT_DIR / "checkpoint.json"
PLANILHA_PATH = DADOS_DIR / "Relacao de contratos e aditivos.xlsx"

# ---------------------------------------------------------------------------
# URL da listagem (parâmetros confirmados no portal)
# ---------------------------------------------------------------------------
BASE_URL = "https://www.governotransparente.com.br"
ORGAO_ID = "43559588"
LISTAGEM_PATH = f"/acessoinfo/{ORGAO_ID}/consultarcontratoaditivo"

LISTAGEM_PARAMS = {
    "inicio": "01/01/2023",
    "fim": "31/12/2023",
    "contr": "",
    "ano": "6",
    "credor": "-1",
    "clean": "false",
    "datainfo": "MTIwMjQwNTExMTcwMFBQUA==",
}

REGISTROS_POR_PAGINA = 10

# ---------------------------------------------------------------------------
# Playwright / rede
# ---------------------------------------------------------------------------
HEADLESS = True
NAVIGATION_TIMEOUT_MS = 30_000
DOWNLOAD_TIMEOUT_MS = 60_000
RETRY_ATTEMPTS = 3
RETRY_DELAYS_SEC = (2, 5, 10)
DELAY_ENTRE_REQUISICOES_SEC = 0.8

# ---------------------------------------------------------------------------
# Downloads / nomes de arquivo
# ---------------------------------------------------------------------------
MAX_NOME_ARQUIVO = 150
CHARS_INVALIDOS = r'<>:"/\|?*'

# ---------------------------------------------------------------------------
# CLI defaults
# ---------------------------------------------------------------------------
RETRY_ERROS_DEFAULT = True


def aplicar_pasta_saida(pasta: str | Path) -> None:
    """Redireciona dados, PDFs, logs e checkpoint para a pasta informada."""
    global DADOS_DIR, CONTRATOS_DIR, LOGS_DIR, CHECKPOINT_DIR, CHECKPOINT_PATH, PLANILHA_PATH
    base = Path(pasta).expanduser().resolve()
    DADOS_DIR = base / "dados"
    CONTRATOS_DIR = base / "contratos"
    LOGS_DIR = base / "logs"
    CHECKPOINT_DIR = base / "checkpoint"
    CHECKPOINT_PATH = CHECKPOINT_DIR / "checkpoint.json"
    PLANILHA_PATH = DADOS_DIR / "Relacao de contratos e aditivos.xlsx"


def aplicar_orgao(orgao_id: str) -> None:
    global ORGAO_ID, LISTAGEM_PATH
    ORGAO_ID = (orgao_id or "").strip()
    LISTAGEM_PATH = f"/acessoinfo/{ORGAO_ID}/consultarcontratoaditivo"


def aplicar_periodo(inicio: str | None = None, fim: str | None = None, ano: str | None = None) -> None:
    if inicio:
        LISTAGEM_PARAMS["inicio"] = inicio.strip()
    if fim:
        LISTAGEM_PARAMS["fim"] = fim.strip()
    if ano is not None and str(ano).strip() != "":
        LISTAGEM_PARAMS["ano"] = str(ano).strip()


def aplicar_datainfo(datainfo: str | None) -> None:
    if datainfo and datainfo.strip():
        LISTAGEM_PARAMS["datainfo"] = datainfo.strip()
