"""Scanner de migracao: compara licitacoes publicadas com uma pasta local."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from openpyxl import Workbook
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

_NUMERO_RE = re.compile(r"(?<!\d)(\d{1,6})\s*[/_-]\s*(20\d{2})(?!\d)")
_STATUS_RE = re.compile(
    r"\b(aberto|anulado|cancelado|deserto|em andamento|finalizado|"
    r"fracassado|publicada|revogado|suspenso)\b",
    re.I,
)


def _normalizar_numero(texto: str) -> str:
    match = _NUMERO_RE.search(texto or "")
    if not match:
        return ""
    return "%03d/%s" % (int(match.group(1)), match.group(2))


def _arquivos_locais(pasta: Path) -> list[dict[str, str]]:
    arquivos = []
    for caminho in sorted(p for p in pasta.rglob("*") if p.is_file()):
        relativo = str(caminho.relative_to(pasta))
        identificador = _normalizar_numero(relativo)
        arquivos.append(
            {
                "arquivo": relativo,
                "numero": identificador,
                "tipo": _tipo_documento(relativo),
            }
        )
    return arquivos


def _tipo_documento(nome: str) -> str:
    base = nome.lower()
    if re.search(r"contrat|aditiv|apostil", base):
        return "Contrato/aditivo"
    if re.search(r"edital|aviso|termo.?refer|projeto.?basico", base):
        return "Edital/termo"
    if re.search(r"ata|homolog|adjudic|resultado", base):
        return "Ata/homologacao"
    return "Outro"


def _linhas_publicadas(page) -> list[dict[str, str]]:
    linhas = []
    for texto in page.locator(".group-item").all_inner_texts():
        texto = texto.strip()
        numero = _normalizar_numero(texto)
        if not numero or "Detalhes" not in texto:
            continue
        partes = [p.strip() for p in texto.splitlines() if p.strip()]
        linhas.append(
            {
                "numero": numero,
                "modalidade": partes[1] if len(partes) > 1 else "",
                "objeto": partes[3] if len(partes) > 3 else "",
                "situacao": (_STATUS_RE.search(texto).group(1) if _STATUS_RE.search(texto) else ""),
            }
        )
    vistos = set()
    return [r for r in linhas if not (r["numero"] in vistos or vistos.add(r["numero"]))]


def _ler_publicadas(url: str, job) -> list[dict[str, str]]:
    publicadas: list[dict[str, str]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2_000)
            paginas_vistas = set()
            for pagina in range(1, 101):
                job.emit("info", "Lendo pagina %d..." % pagina)
                atuais = _linhas_publicadas(page)
                novos = [r for r in atuais if r["numero"] not in {x["numero"] for x in publicadas}]
                publicadas.extend(novos)
                if not atuais or not novos:
                    break
                paginas_vistas.add(tuple(r["numero"] for r in atuais))
                proxima = page.get_by_text(str(pagina + 1), exact=True).last
                if proxima.count() == 0:
                    break
                try:
                    proxima.click()
                    page.wait_for_timeout(1_000)
                except (PlaywrightTimeoutError, Exception):
                    break
        finally:
            browser.close()
    return publicadas


def _salvar_relatorio(saida: Path, publicadas: list[dict[str, str]], arquivos: list[dict[str, str]]) -> tuple[Path, Path]:
    saida.mkdir(parents=True, exist_ok=True)
    por_numero: dict[str, list[dict[str, str]]] = {}
    for arquivo in arquivos:
        if arquivo["numero"]:
            por_numero.setdefault(arquivo["numero"], []).append(arquivo)

    wb = Workbook()
    ws = wb.active
    ws.title = "Conferencia"
    ws.append(["Numero", "Modalidade", "Situacao", "Publicado", "Arquivos locais", "Status"])
    for item in publicadas:
        encontrados = por_numero.get(item["numero"], [])
        ws.append([
            item["numero"], item["modalidade"], item["situacao"], "Sim",
            len(encontrados), "Encontrado" if encontrados else "Sem arquivo local",
        ])
    publicados = {item["numero"] for item in publicadas}
    for numero, itens in sorted(por_numero.items()):
        if numero not in publicados:
            ws.append([numero, "", "", "Nao", len(itens), "Arquivo sem licitacao publicada"])
    for coluna, largura in zip("ABCDEF", [16, 28, 18, 12, 18, 34]):
        ws.column_dimensions[coluna].width = largura

    excel = saida / "relatorio_arrumador.xlsx"
    wb.save(excel)
    txt = saida / "relatorio_arrumador.txt"
    faltantes = [item for item in publicadas if item["numero"] not in por_numero]
    extras = [numero for numero in por_numero if numero not in publicados]
    txt.write_text(
        "ARRUMADOR DE LICITACOES\n\n"
        "Licitacoes publicadas: %d\n"
        "Licitacoes com arquivos locais: %d\n"
        "Licitacoes sem arquivo local: %d\n"
        "Numeros locais sem publicacao correspondente: %d\n\n"
        "PENDENTES:\n%s\n\n"
        "SEM CORRESPONDENCIA NO PORTAL:\n%s\n" % (
            len(publicadas), len(publicadas) - len(faltantes), len(faltantes), len(extras),
            "\n".join("- " + x["numero"] for x in faltantes) or "(nenhuma)",
            "\n".join("- " + x for x in extras) or "(nenhum)",
        ),
        encoding="utf-8",
    )
    return excel, txt


def run(job) -> None:
    cfg: dict[str, Any] = job.config or {}
    url = str(cfg.get("url_entidade") or "").strip()
    pasta = Path(str(cfg.get("pasta_local") or "").strip()).expanduser()
    saida = Path(str(cfg.get("pasta_saida") or (pasta / "_arrumador")).strip()).expanduser()
    if not url:
        raise ValueError("Informe a URL publica da entidade.")
    if not pasta.is_dir():
        raise ValueError("A pasta local nao existe ou nao e uma pasta: %s" % pasta)
    if not url.startswith(("http://", "https://")):
        raise ValueError("A URL da entidade deve comecar por http:// ou https://.")

    job.emit("info", "Entidade: %s" % url)
    job.emit("info", "Pasta local: %s" % pasta)
    publicadas = _ler_publicadas(url, job)
    arquivos = _arquivos_locais(pasta)
    excel, txt = _salvar_relatorio(saida, publicadas, arquivos)
    faltantes = [x for x in publicadas if x["numero"] not in {a["numero"] for a in arquivos}]
    job.result.update({
        "pasta": str(saida),
        "planilha": str(excel),
        "relatorio": str(txt),
        "publicadas": len(publicadas),
        "arquivos_locais": len(arquivos),
        "pendentes": len(faltantes),
        "mensagem": "Conferencia concluida: %d pendencia(s)." % len(faltantes),
    })
    job.emit("info", "Publicadas: %d | Arquivos locais: %d | Pendentes: %d" % (len(publicadas), len(arquivos), len(faltantes)))
