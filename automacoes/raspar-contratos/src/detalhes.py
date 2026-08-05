"""Extração da página de detalhe do contrato/aditivo."""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from playwright.sync_api import Page

import config
from src.browser import com_retry
from src.logger import get_logger

logger = get_logger()

RE_FILE_ID = re.compile(r"/download/(\d+)/")
RE_DETALHES = re.compile(r"/detalhes/(\d+)/(\d+)")


def _norm_label(texto: str) -> str:
    t = (texto or "").strip().lower().rstrip(":")
    t = re.sub(r"\s+", " ", t)
    return t


def acessar_detalhes(page: Page, url: str) -> None:
    def _goto():
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("dl.ctr-detail-list, div.ctr-detail-header", timeout=config.NAVIGATION_TIMEOUT_MS)

    com_retry(_goto, descricao=f"abrir detalhes {url}")
    time.sleep(config.DELAY_ENTRE_REQUISICOES_SEC)


def extrair_dados_contrato(page: Page) -> dict[str, str]:
    mapa_rotulos = {
        "origem": "origem",
        "contratante": "contratante",
        "contratada(o)": "contratada",
        "contratada": "contratada",
        "valor": "valor",
        "início da vigência": "inicio_vigencia",
        "inicio da vigencia": "inicio_vigencia",
        "fim da vigência": "fim_vigencia",
        "fim da vigencia": "fim_vigencia",
    }
    dados: dict[str, str] = {
        "origem": "",
        "contratante": "",
        "contratada": "",
        "valor": "",
        "inicio_vigencia": "",
        "fim_vigencia": "",
    }

    rows = page.locator("dl.ctr-detail-list div.ctr-detail-row")
    for i in range(rows.count()):
        row = rows.nth(i)
        dt = row.locator("dt")
        dd = row.locator("dd")
        if not dt.count() or not dd.count():
            continue
        label = _norm_label(dt.first.inner_text())
        valor = (dd.first.inner_text() or "").strip()
        chave = mapa_rotulos.get(label)
        if chave:
            dados[chave] = valor

    return dados


def extrair_objeto(page: Page) -> str:
    callout = page.locator("div.ctr-info-callout")
    if callout.count():
        return (callout.first.inner_text() or "").strip()
    # fallback: seção Objeto
    titles = page.locator("div.ctr-section-title")
    for i in range(titles.count()):
        t = (titles.nth(i).inner_text() or "").strip().lower()
        if "objeto" in t:
            # próximo bloco irmão / seguinte
            parent = titles.nth(i).locator("xpath=..")
            callout2 = parent.locator("div.ctr-info-callout")
            if callout2.count():
                return (callout2.first.inner_text() or "").strip()
    return ""


def extrair_contrato_original_url(page: Page, aditivo_index: int) -> str:
    if aditivo_index <= 0:
        return ""
    links = page.locator("a")
    for i in range(links.count()):
        a = links.nth(i)
        texto = (a.inner_text() or "").strip().lower()
        href = a.get_attribute("href") or ""
        if "contrato original" in texto or "/detalhes/" in href and href.rstrip("/").endswith("/0"):
            # Preferir o bloco explícito
            parent_text = ""
            try:
                parent_text = (a.locator("xpath=ancestor::*[1]").inner_text() or "").lower()
            except Exception:  # noqa: BLE001
                pass
            if "contrato original" in texto or "contrato original" in parent_text:
                if RE_DETALHES.search(href):
                    return urljoin(config.BASE_URL, href)
    # Fallback: derivar da URL atual
    current = page.url
    m = RE_DETALHES.search(current)
    if m:
        return urljoin(config.BASE_URL, current.split("?")[0].rsplit("/", 1)[0] + "/0?clean=false")
    return ""


def extrair_itens(page: Page) -> list[dict[str, str]]:
    itens: list[dict[str, str]] = []
    # Primeira table.ctr-table costuma ser Itens; confirmar pelo thead
    tables = page.locator("table.ctr-table")
    tabela_itens = None
    for i in range(tables.count()):
        ths = tables.nth(i).locator("thead th")
        headers = " ".join((ths.nth(j).inner_text() or "").lower() for j in range(ths.count()))
        if "descrição" in headers or "descricao" in headers:
            if "quantidade" in headers or "valor" in headers:
                tabela_itens = tables.nth(i)
                break
    if tabela_itens is None:
        return itens

    rows = tabela_itens.locator("tbody tr")
    for i in range(rows.count()):
        tds = rows.nth(i).locator("td")
        if tds.count() < 5:
            continue
        itens.append(
            {
                "descricao": (tds.nth(0).inner_text() or "").strip(),
                "quantidade": (tds.nth(1).inner_text() or "").strip(),
                "unidade": (tds.nth(2).inner_text() or "").strip(),
                "valor_unitario": (tds.nth(3).inner_text() or "").strip(),
                "valor_total": (tds.nth(4).inner_text() or "").strip(),
            }
        )
    return itens


def extrair_arquivos(page: Page) -> list[dict[str, str]]:
    arquivos: list[dict[str, str]] = []
    tables = page.locator("table.ctr-table")
    tabela_arq = None
    for i in range(tables.count()):
        ths = tables.nth(i).locator("thead th")
        headers = " ".join((ths.nth(j).inner_text() or "").lower() for j in range(ths.count()))
        if "título do arquivo" in headers or "titulo do arquivo" in headers or "tipo" in headers and "arquivo" in headers:
            tabela_arq = tables.nth(i)
            break
        if "título" in headers and "tipo" in headers:
            tabela_arq = tables.nth(i)
            break

    if tabela_arq is None:
        return arquivos

    rows = tabela_arq.locator("tbody tr")
    for i in range(rows.count()):
        tr = rows.nth(i)
        tds = tr.locator("td")
        if tds.count() < 2:
            continue
        link = tds.nth(0).locator("a")
        if not link.count():
            continue
        titulo = (link.first.inner_text() or "").strip()
        href = link.first.get_attribute("href") or ""
        url_arquivo = urljoin(config.BASE_URL, href)
        tipo_mime = (tds.nth(1).inner_text() or "").strip()

        path = unquote(urlparse(url_arquivo).path)
        nome_original = path.rstrip("/").rsplit("/", 1)[-1] if path else ""
        m = RE_FILE_ID.search(path)
        file_id = m.group(1) if m else ""

        arquivos.append(
            {
                "titulo_exibido": titulo,
                "nome_arquivo_original": nome_original,
                "tipo_mime": tipo_mime,
                "url_arquivo": url_arquivo,
                "file_id": file_id,
            }
        )
    return arquivos


def processar_pagina_detalhe(page: Page, registro: dict[str, Any]) -> dict[str, Any]:
    """Acessa a URL de detalhes e enriquece o registro com dados, itens e arquivos."""
    url = registro["url_detalhes"]
    acessar_detalhes(page, url)

    dados = extrair_dados_contrato(page)
    objeto = extrair_objeto(page)
    itens = extrair_itens(page)
    arquivos = extrair_arquivos(page)
    contrato_original_url = extrair_contrato_original_url(page, registro.get("aditivo_index", 0))

    registro.update(
        {
            "origem": dados.get("origem", ""),
            "contratante": dados.get("contratante", ""),
            "contratada": dados.get("contratada") or registro.get("contratada_listagem", ""),
            "valor": dados.get("valor") or registro.get("valor_listagem", ""),
            "inicio_vigencia": dados.get("inicio_vigencia")
            or registro.get("inicio_vigencia_listagem", ""),
            "fim_vigencia": dados.get("fim_vigencia") or registro.get("fim_vigencia_listagem", ""),
            "objeto": objeto,
            "contrato_original_url": contrato_original_url,
            "itens": itens,
            "arquivos": arquivos,
        }
    )
    logger.info(
        "Detalhe %s (%s): %d item(ns), %d arquivo(s)",
        registro["id_registro"],
        registro.get("numero_contrato"),
        len(itens),
        len(arquivos),
    )
    return registro
