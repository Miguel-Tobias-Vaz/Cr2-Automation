"""Logging em console e arquivo."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import config


def configurar_logging() -> logging.Logger:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = config.LOGS_DIR / f"execucao_{stamp}.log"

    logger = logging.getLogger("contratos")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.info("Log gravado em %s", log_path)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("contratos")
