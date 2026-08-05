"""Checkpoint para retomada segura entre execuções."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from src.logger import get_logger

logger = get_logger()


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def checkpoint_vazio() -> dict[str, Any]:
    return {
        "registros": {},
        "arquivos_por_fileid": {},
        "paginas_processadas": [],
        "total_esperado": None,
        "atualizado_em": None,
    }


def carregar_checkpoint(path: Path | None = None) -> dict[str, Any]:
    path = path or config.CHECKPOINT_PATH
    if not path.exists():
        return checkpoint_vazio()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, default in checkpoint_vazio().items():
            data.setdefault(key, default)
        logger.info(
            "Checkpoint carregado: %d registro(s), %d arquivo(s) indexados",
            len(data.get("registros", {})),
            len(data.get("arquivos_por_fileid", {})),
        )
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Checkpoint inválido (%s); iniciando vazio", exc)
        return checkpoint_vazio()


def salvar_checkpoint(data: dict[str, Any], path: Path | None = None) -> None:
    path = path or config.CHECKPOINT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data["atualizado_em"] = _agora()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def marcar_registro(
    checkpoint: dict[str, Any],
    id_registro: str,
    *,
    status: str,
    numero_contrato: str = "",
    mensagem_erro: str = "",
    snapshot: dict[str, Any] | None = None,
    arquivos: list[dict[str, Any]] | None = None,
) -> None:
    entrada: dict[str, Any] = {
        "status": status,
        "numero_contrato": numero_contrato,
        "mensagem_erro": mensagem_erro,
        "timestamp": _agora(),
    }
    if snapshot is not None:
        entrada["snapshot"] = snapshot
    if arquivos is not None:
        entrada["arquivos"] = arquivos
    checkpoint["registros"][id_registro] = entrada
    salvar_checkpoint(checkpoint)


def registrar_arquivo(
    checkpoint: dict[str, Any],
    file_id: str,
    caminho_local: str,
) -> None:
    checkpoint["arquivos_por_fileid"][str(file_id)] = caminho_local
    salvar_checkpoint(checkpoint)


def deve_processar(
    checkpoint: dict[str, Any],
    id_registro: str,
    *,
    retry_erros: bool = True,
) -> bool:
    info = checkpoint.get("registros", {}).get(id_registro)
    if info is None:
        return True
    if info.get("status") == "ok":
        return False
    if info.get("status") == "erro":
        return retry_erros
    return True


def resetar_checkpoint(path: Path | None = None) -> dict[str, Any]:
    data = checkpoint_vazio()
    salvar_checkpoint(data, path)
    logger.info("Checkpoint resetado")
    return data
