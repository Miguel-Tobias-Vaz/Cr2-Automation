"""Download de arquivos com deduplicação por fileId."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeout

import config
from src import checkpoint as ckpt
from src.logger import get_logger
from src.storage import extensao_de, nome_unico, pasta_contrato, sanitizar_nome

logger = get_logger()


def _caminho_relativo(path: Path) -> str:
    try:
        return str(path.relative_to(config.BASE_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _baixar_via_expect_download(page: Page, link_locator, destino: Path) -> Path:
    with page.expect_download(timeout=config.DOWNLOAD_TIMEOUT_MS) as di:
        link_locator.click()
    download = di.value
    download.save_as(destino)
    return destino


def _baixar_via_nova_aba(context: BrowserContext, page: Page, link_locator, destino: Path) -> Path:
    with context.expect_page(timeout=config.DOWNLOAD_TIMEOUT_MS) as pi:
        link_locator.click()
    nova = pi.value
    try:
        nova.wait_for_load_state("domcontentloaded", timeout=config.DOWNLOAD_TIMEOUT_MS)
        # Se a nova página disparar download
        try:
            with nova.expect_download(timeout=5_000) as di:
                pass
            download = di.value
            download.save_as(destino)
            return destino
        except PlaywrightTimeout:
            # Pode ser visualização inline de PDF — salvar via request API
            url = nova.url
            resp = context.request.get(url, timeout=config.DOWNLOAD_TIMEOUT_MS)
            if not resp.ok:
                raise RuntimeError(f"HTTP {resp.status} ao baixar {url}")
            destino.write_bytes(resp.body())
            return destino
    finally:
        nova.close()


def _baixar_via_request(context: BrowserContext, url: str, destino: Path) -> Path:
    resp = context.request.get(url, timeout=config.DOWNLOAD_TIMEOUT_MS)
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status} ao baixar {url}")
    body = resp.body()
    if not body:
        raise RuntimeError("Resposta vazia no download")
    destino.write_bytes(body)
    return destino


def baixar_arquivo(
    page: Page,
    context: BrowserContext,
    *,
    url_arquivo: str,
    titulo_exibido: str,
    nome_original: str,
    mime: str,
    pasta: Path,
) -> tuple[str, Path, int]:
    """
    Baixa um arquivo para `pasta`.
    Retorna (nome_salvo, caminho_absoluto, tamanho_bytes).
    """
    ext = extensao_de(nome_original, mime)
    base = sanitizar_nome(titulo_exibido)
    if not base.lower().endswith(ext.lower()):
        base = f"{base}{ext}"
    nome_salvo = nome_unico(pasta, base)
    destino = pasta / nome_salvo

    ultimo_erro: Exception | None = None
    for tentativa in range(config.RETRY_ATTEMPTS):
        try:
            # Preferência: request HTTP direto (links estáticos confirmados)
            _baixar_via_request(context, url_arquivo, destino)
            tamanho = destino.stat().st_size
            if tamanho <= 0:
                raise RuntimeError("Arquivo baixado com tamanho 0")
            return nome_salvo, destino, tamanho
        except Exception as exc:  # noqa: BLE001
            ultimo_erro = exc
            delay = config.RETRY_DELAYS_SEC[min(tentativa, len(config.RETRY_DELAYS_SEC) - 1)]
            logger.warning(
                "Download falhou (%s) tentativa %d/%d: %s",
                url_arquivo,
                tentativa + 1,
                config.RETRY_ATTEMPTS,
                exc,
            )
            if destino.exists():
                try:
                    destino.unlink()
                except OSError:
                    pass
            if tentativa < config.RETRY_ATTEMPTS - 1:
                time.sleep(delay)

    # Fallback: clicar no link na página (expect_download / nova aba)
    link = page.locator(f'a[href*="{urlparse(url_arquivo).path}"]')
    if not link.count():
        # href absoluto vs relativo
        path = urlparse(url_arquivo).path
        link = page.locator(f'a[href*="{path.split("/download/")[-1] if "/download/" in path else path}"]')
    if link.count():
        try:
            with page.expect_download(timeout=config.DOWNLOAD_TIMEOUT_MS) as di:
                link.first.click()
            download = di.value
            download.save_as(destino)
            tamanho = destino.stat().st_size
            if tamanho <= 0:
                raise RuntimeError("Arquivo baixado com tamanho 0 (via click)")
            return nome_salvo, destino, tamanho
        except Exception as exc:  # noqa: BLE001
            ultimo_erro = exc
            logger.warning("Fallback click/download falhou: %s", exc)
            try:
                _baixar_via_nova_aba(context, page, link.first, destino)
                tamanho = destino.stat().st_size
                if tamanho <= 0:
                    raise RuntimeError("Arquivo baixado com tamanho 0 (nova aba)")
                return nome_salvo, destino, tamanho
            except Exception as exc2:  # noqa: BLE001
                ultimo_erro = exc2

    raise RuntimeError(f"Falha ao baixar {url_arquivo}: {ultimo_erro}")


def processar_arquivos_registro(
    page: Page,
    context: BrowserContext,
    registro: dict[str, Any],
    checkpoint: dict[str, Any],
) -> list[dict[str, Any]]:
    """Baixa ou reaproveita arquivos do registro; atualiza checkpoint."""
    slug = registro["numero_contrato_slug"]
    pasta = pasta_contrato(slug)
    registro["pasta_local"] = _caminho_relativo(pasta)

    resultados: list[dict[str, Any]] = []
    arquivos = registro.get("arquivos") or []

    for arq in arquivos:
        file_id = str(arq.get("file_id") or "")
        titulo = arq.get("titulo_exibido") or "arquivo"
        nome_orig = arq.get("nome_arquivo_original") or ""
        mime = arq.get("tipo_mime") or ""
        url = arq.get("url_arquivo") or ""

        entrada: dict[str, Any] = {
            "id_registro": registro["id_registro"],
            "numero_contrato": registro.get("numero_contrato", ""),
            "titulo_exibido": titulo,
            "nome_arquivo_original": nome_orig,
            "tipo_mime": mime,
            "url_arquivo": url,
            "file_id": file_id,
            "nome_salvo": "",
            "caminho_local": "",
            "status_download": "nao_aplicavel",
            "tamanho_bytes": 0,
        }

        if file_id and file_id in checkpoint.get("arquivos_por_fileid", {}):
            caminho_existente = checkpoint["arquivos_por_fileid"][file_id]
            abs_path = config.BASE_DIR / caminho_existente
            tamanho = abs_path.stat().st_size if abs_path.exists() else 0
            entrada.update(
                {
                    "nome_salvo": Path(caminho_existente).name,
                    "caminho_local": caminho_existente,
                    "status_download": "reaproveitado",
                    "tamanho_bytes": tamanho,
                }
            )
            logger.info("Arquivo fileId=%s reaproveitado: %s", file_id, caminho_existente)
            resultados.append(entrada)
            continue

        if not url:
            entrada["status_download"] = "falha"
            resultados.append(entrada)
            continue

        try:
            nome_salvo, destino, tamanho = baixar_arquivo(
                page,
                context,
                url_arquivo=url,
                titulo_exibido=titulo,
                nome_original=nome_orig,
                mime=mime,
                pasta=pasta,
            )
            rel = _caminho_relativo(destino)
            entrada.update(
                {
                    "nome_salvo": nome_salvo,
                    "caminho_local": rel,
                    "status_download": "baixado",
                    "tamanho_bytes": tamanho,
                }
            )
            if file_id:
                ckpt.registrar_arquivo(checkpoint, file_id, rel)
            logger.info("Baixado: %s (%d bytes)", rel, tamanho)
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha download %s: %s", url, exc)
            entrada["status_download"] = "falha"
            entrada["mensagem_erro"] = str(exc)

        resultados.append(entrada)
        time.sleep(config.DELAY_ENTRE_REQUISICOES_SEC)

    return resultados
