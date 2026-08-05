"""Gerenciamento do navegador Playwright."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

import config
from src.logger import get_logger

logger = get_logger()

# UA realista: o portal rejeita o User-Agent padrão do Playwright (HTTP 403).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


@contextmanager
def iniciar_navegador(
    *,
    headless: bool | None = None,
) -> Generator[tuple[Playwright, Browser, BrowserContext, Page], None, None]:
    headless = config.HEADLESS if headless is None else headless
    logger.info("Iniciando Chromium (headless=%s)", headless)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            accept_downloads=True,
            locale="pt-BR",
            viewport={"width": 1280, "height": 900},
            user_agent=USER_AGENT,
        )
        context.set_default_navigation_timeout(config.NAVIGATION_TIMEOUT_MS)
        context.set_default_timeout(config.NAVIGATION_TIMEOUT_MS)
        page = context.new_page()
        try:
            yield pw, browser, context, page
        finally:
            context.close()
            browser.close()
            logger.info("Navegador encerrado")


def com_retry(acao, *, descricao: str, tentativas: int | None = None):
    """Executa ação com retries e backoff configurado."""
    import time

    tentativas = tentativas or config.RETRY_ATTEMPTS
    ultimo_erro: Exception | None = None
    for i in range(tentativas):
        try:
            return acao()
        except Exception as exc:  # noqa: BLE001 — capturar e retentar
            ultimo_erro = exc
            delay = config.RETRY_DELAYS_SEC[min(i, len(config.RETRY_DELAYS_SEC) - 1)]
            logger.warning(
                "%s falhou (tentativa %d/%d): %s — aguardando %ss",
                descricao,
                i + 1,
                tentativas,
                exc,
                delay,
            )
            if i < tentativas - 1:
                time.sleep(delay)
    assert ultimo_erro is not None
    raise ultimo_erro
