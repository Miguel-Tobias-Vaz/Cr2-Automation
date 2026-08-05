"""Varredura da listagem de contratos/aditivos."""

from __future__ import annotations

import math
import re
import time
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from playwright.sync_api import Page

import config
from src.browser import com_retry
from src.logger import get_logger
from src.storage import slug_contrato

logger = get_logger()

RE_TOTAL = re.compile(
    r"Mostrando\s+de\s+(\d+)\s+at[eé]\s+(\d+)\s+de\s+(\d+)\s+registros",
    re.IGNORECASE,
)
RE_DETALHES = re.compile(
    r"/consultarcontratoaditivo/resultado/detalhes/(\d+)/(\d+)",
)


def montar_url_listagem(pagina: int = 1) -> str:
    params = dict(config.LISTAGEM_PARAMS)
    if pagina > 1:
        params["page"] = str(pagina)
    query = urlencode(params, safe="/=")
    return f"{config.BASE_URL}{config.LISTAGEM_PATH}?{query}"


def obter_total_registros(page: Page) -> int:
    textos = page.locator("p.text-gray-500").all_inner_texts()
    for texto in textos:
        m = RE_TOTAL.search(texto)
        if m:
            total = int(m.group(3))
            logger.info("Total de registros na listagem: %d", total)
            return total
    # fallback: corpo da página
    body = page.locator("body").inner_text()
    m = RE_TOTAL.search(body)
    if m:
        total = int(m.group(3))
        logger.info("Total de registros (fallback): %d", total)
        return total
    raise RuntimeError("Não foi possível ler o total de registros da listagem")


def _texto_celula(td) -> str:
    return (td.inner_text() or "").strip()


def _credor_de(td) -> tuple[str, str]:
    doc = ""
    nome = ""
    strong = td.locator("strong.credor-doc")
    if strong.count():
        doc = (strong.first.inner_text() or "").strip()
    sec = td.locator("p.cell-secondary")
    if sec.count():
        nome = (sec.first.inner_text() or "").strip()
    if not doc and not nome:
        raw = _texto_celula(td)
        partes = [p.strip() for p in raw.split("\n") if p.strip()]
        if partes:
            doc = partes[0]
            nome = " ".join(partes[1:]) if len(partes) > 1 else ""
    return doc, nome


def extrair_linhas_tabela(page: Page, pagina: int) -> list[dict[str, Any]]:
    rows = page.locator("table#data-table tbody tr")
    n = rows.count()
    registros: list[dict[str, Any]] = []

    for i in range(n):
        tr = rows.nth(i)
        tds = tr.locator("td")
        if tds.count() < 11:
            logger.warning("Página %d linha %d: menos de 11 colunas — ignorada", pagina, i + 1)
            continue

        data = _texto_celula(tds.nth(0))
        numero = _texto_celula(tds.nth(1))
        inicio = _texto_celula(tds.nth(2))
        fim = _texto_celula(tds.nth(3))
        tipo = _texto_celula(tds.nth(4))
        rotulo_aditivo = _texto_celula(tds.nth(5))
        cnpj, contratada = _credor_de(tds.nth(6))
        fiscal_doc, fiscal_nome = _credor_de(tds.nth(7))
        fiscal = " ".join(x for x in (fiscal_doc, fiscal_nome) if x).strip() or "N/A"
        valor = _texto_celula(tds.nth(8))
        n_anexos = _texto_celula(tds.nth(9))

        link = tds.nth(10).locator("a.btn")
        if not link.count():
            link = tds.nth(10).locator("a")
        if not link.count():
            logger.warning("Página %d linha %d: sem link Detalhes", pagina, i + 1)
            continue

        href = link.first.get_attribute("href") or ""
        url_detalhes = urljoin(config.BASE_URL, href)
        m = RE_DETALHES.search(urlparse(url_detalhes).path)
        if not m:
            logger.warning("URL de detalhes não reconhecida: %s", url_detalhes)
            continue

        contract_id = m.group(1)
        aditivo_index = int(m.group(2))
        id_registro = f"{contract_id}-{aditivo_index}"

        registros.append(
            {
                "id_registro": id_registro,
                "contract_id": contract_id,
                "aditivo_index": aditivo_index,
                "numero_contrato": numero,
                "numero_contrato_slug": slug_contrato(numero),
                "tipo_registro": tipo,
                "rotulo_aditivo": rotulo_aditivo,
                "data_listagem": data,
                "inicio_vigencia_listagem": inicio,
                "fim_vigencia_listagem": fim,
                "cnpj_cpf_contratada": cnpj,
                "contratada_listagem": contratada,
                "fiscal_responsavel": fiscal,
                "valor_listagem": valor,
                "numero_anexos_listagem": n_anexos,
                "url_detalhes": url_detalhes,
                "pagina_listagem": pagina,
            }
        )

    logger.info("Página %d: %d registro(s) extraído(s)", pagina, len(registros))
    return registros


def descobrir_registros(page: Page) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Varre todas as páginas e retorna (lista_registros, meta)."""
    url1 = montar_url_listagem(1)
    logger.info("Acessando listagem página 1: %s", url1)

    def _abrir_pagina1():
        page.goto(url1, wait_until="domcontentloaded")
        page.wait_for_selector("table#data-table", timeout=config.NAVIGATION_TIMEOUT_MS)

    com_retry(_abrir_pagina1, descricao="abrir listagem página 1")
    time.sleep(config.DELAY_ENTRE_REQUISICOES_SEC)

    total = obter_total_registros(page)
    total_paginas = max(1, math.ceil(total / config.REGISTROS_POR_PAGINA))
    logger.info("Páginas a varrer: %d", total_paginas)

    todos: list[dict[str, Any]] = []
    paginas_info: list[dict[str, Any]] = []
    vistos: set[str] = set()
    total_linhas_brutas = 0
    duplicados_listagem: list[str] = []

    for pagina in range(1, total_paginas + 1):
        if pagina > 1:
            url = montar_url_listagem(pagina)
            logger.info("Acessando listagem página %d", pagina)

            def _abrir():
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_selector("table#data-table", timeout=config.NAVIGATION_TIMEOUT_MS)

            com_retry(_abrir, descricao=f"abrir listagem página {pagina}")
            time.sleep(config.DELAY_ENTRE_REQUISICOES_SEC)

        linhas = extrair_linhas_tabela(page, pagina)
        total_linhas_brutas += len(linhas)
        novos = 0
        for reg in linhas:
            if reg["id_registro"] in vistos:
                logger.warning(
                    "Duplicado na listagem (paginação do portal): %s",
                    reg["id_registro"],
                )
                duplicados_listagem.append(reg["id_registro"])
                continue
            vistos.add(reg["id_registro"])
            todos.append(reg)
            novos += 1

        paginas_info.append(
            {
                "pagina": pagina,
                "status": "OK",
                "registros": novos,
            }
        )

    meta = {
        "total_esperado": total,
        "total_paginas": total_paginas,
        "total_linhas_brutas": total_linhas_brutas,
        "total_coletado": len(todos),
        "duplicados_listagem": duplicados_listagem,
        "paginas": paginas_info,
    }

    if duplicados_listagem:
        logger.warning(
            "Portal listou %d linha(s) duplicada(s) entre páginas (%s). "
            "Únicos a processar: %d (rótulo do site: %d)",
            len(duplicados_listagem),
            ", ".join(duplicados_listagem),
            len(todos),
            total,
        )
    elif len(todos) != total:
        logger.warning(
            "Divergência: esperados %d, coletados %d",
            total,
            len(todos),
        )
    else:
        logger.info("Varredura OK: %d registros coletados", len(todos))

    return todos, meta
