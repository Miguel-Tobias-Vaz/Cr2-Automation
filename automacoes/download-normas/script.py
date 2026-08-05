"""
Download de normas municipais (Leis, Decretos, Portarias, Demais).

Suporta:
  - categoria WordPress: lista posts → abre cada post → baixa PDFs do corpo
  - hub de anos: página índice (ex.: /decretos/) → páginas por ano → PDFs diretos
  - página direta: PDFs já listados na própria URL

Nomeia arquivos no padrão:
  Portaria Nº010/2025.pdf
  Lei Nº010/2025.pdf
  LDO Nº010/2025.pdf
  LOA Nº010/2025.pdf
  Decreto Nº010/2025.pdf

Quando o link é genérico ("Clique aqui"), lê o texto do PDF (pypdf)
e/ou o título do post para classificar e numerar corretamente.
"""
from __future__ import annotations

import html as html_module
import io
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


class Cancelado(Exception):
    """Fila interrompida pelo usuario (centro-automacoes)."""


def pedido_cancelado() -> bool:
    """Sobrescrito pelo painel quando o job e cancelado."""
    return False


def _abortar_se_cancelado() -> None:
    if pedido_cancelado():
        print("  [AVISO] Fila cancelada pelo usuario.")
        raise Cancelado()


# --- Configuração ---
PASTA_BASE = r"C:\Downloads\Inhangapi"
SITE = "https://inhangapi.pa.gov.br"

# Cada fonte: url, modo (categoria | hub_anos | pagina), pasta opcional
# (se pasta vazia → título da página ou slug da URL)
FONTES = [
    {
        "url": "https://inhangapi.pa.gov.br/c/publicacoes/leis/",
        "modo": "categoria",
        "pasta": "",
    },
    {
        "url": "https://inhangapi.pa.gov.br/decretos/",
        "modo": "hub_anos",
        "pasta": "",
    },
    {
        "url": "https://inhangapi.pa.gov.br/c/publicacoes/portarias/",
        "modo": "categoria",
        "pasta": "",
    },
    {
        "url": "https://inhangapi.pa.gov.br/c/publicacoes/demais/",
        "modo": "categoria",
        "pasta": "",
    },
]

# Lê as primeiras páginas do PDF para refinar o nome (recomendado).
LER_PDF = True
MAX_PAGINAS_PDF = 2
# Páginas extras quando extrai campos de Diárias.
MAX_PAGINAS_DIARIAS = 4
# Limite opcional de posts por fonte (0 = todos). Útil para teste.
LIMITE_POSTS = 0
# Filtro de anos: lista de strings, ex. ["2023"] ou ["2022", "2023"].
# Lista vazia = processa TODOS os anos.
ANOS_FILTRO = []

# Extrai campos quando a fonte/PDF é de Diárias (regra geral — não é opção).
# Ex.: https://camaracachoeiradopiria.pa.gov.br/diarias-ate-2023/
EXTRAI_DIARIAS = True

# IA local (Ollama) — só corrige nome quando regras falham (tipo/número/ano).
REFINAR_IA = False
MODELO_IA = "llama3.2:3b"
OLLAMA_URL = "http://127.0.0.1:11434"
IA_SEMPRE = False

# Acumulador de linhas da planilha de Diárias (preenchido em baixar_e_salvar).
REGISTROS_DIARIAS: list[dict] = []

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


# =============================================================
# Utilitários
# =============================================================

def criar_pasta(caminho: str) -> None:
    os.makedirs(caminho, exist_ok=True)


def limpar_nome_pasta(nome: str) -> str:
    """Remove caracteres inválidos para nome de pasta no Windows."""
    nome = (nome or "").strip()
    for c in '<>:"/\\|?*':
        nome = nome.replace(c, "")
    nome = re.sub(r"\s+", " ", nome).strip(" .")
    return nome


def pasta_da_url(url: str) -> str:
    """
    Deriva nome de pasta do último segmento útil da URL.
    Ex.: /c/publicacoes/leis/ → Leis
         /decretos/ → Decretos
    """
    path = urlparse(url or "").path.strip("/")
    partes = [p for p in path.split("/") if p]
    ignorar = {
        "c", "category", "categoria", "categories", "publicacoes",
        "publicação", "publicacao", "page", "p", "wp", "index.php",
    }
    uteis = [p for p in partes if p.lower() not in ignorar and not p.isdigit()]
    slug = uteis[-1] if uteis else (partes[-1] if partes else "documentos")
    slug = unquote(slug)
    slug = slug.replace("-", " ").replace("_", " ")
    slug = re.sub(r"\s+", " ", slug).strip()
    # Capitaliza palavras simples (leis → Leis)
    if slug and slug.islower():
        slug = slug.title()
    return limpar_nome_pasta(slug) or "Documentos"


def resolver_pasta_hint(fonte: dict, titulo: str = "") -> str:
    """
    Nome da subpasta local:
      1) pasta informada na fonte (override)
      2) título da página (h1/title)
      3) slug da URL
    """
    manual = limpar_nome_pasta((fonte.get("pasta") or "").strip())
    if manual:
        return manual
    auto = limpar_nome_pasta(titulo or "")
    if auto:
        return auto
    return pasta_da_url(fonte.get("url") or "")


def obter_titulo_fonte(url: str) -> str:
    """Abre a URL da fonte e lê o título da página."""
    try:
        resp = _get(url)
        soup = BeautifulSoup(resp.content, "html.parser")
        return titulo_da_pagina(soup)
    except Exception as e:
        print(f"  [AVISO] Não foi possível ler título de {url}: {e}")
        return ""


def limpar_nome_arquivo(nome: str) -> str:
    for c in '<>:"/\\|?*':
        nome = nome.replace(c, "-")
    nome = re.sub(r"\s+", " ", nome).strip()
    # Windows: barra no nome "Nº010/2025" → usar hífen no path real
    # Mantemos o padrão pedido trocando / por - no filesystem.
    return nome


def nome_arquivo_final(nome_logico: str) -> str:
    """
    Nome lógico: 'Lei Nº738/2023'
    Arquivo no disco: 'Lei Nº738-2023.pdf' (barra inválida no Windows)
    """
    base = limpar_nome_arquivo(nome_logico.replace("/", "-"))
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


def _mesmo_dominio(url_a: str, url_b: str) -> bool:
    host_a = urlparse(url_a).netloc.lower().replace("www.", "")
    host_b = urlparse(url_b).netloc.lower().replace("www.", "")
    return bool(host_a) and host_a == host_b


def _absolutizar(base: str, href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return urljoin(base, href)


def _eh_pdf_href(href: str) -> bool:
    if not href:
        return False
    low = href.split("?")[0].split("#")[0].lower()
    return low.endswith(".pdf") or ("wp-content/uploads" in low and ".pdf" in low)


def _normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKC", texto)
    texto = texto.replace("\xa0", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _get(url: str, timeout: int = 45) -> requests.Response:
    resp = _SESSION.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp


# =============================================================
# Classificação / nomenclatura
# =============================================================

_RE_NUM_ANO = re.compile(
    r"(?:"
    r"n[º°o\.º]*\s*[º°]?\s*"
    r"|n[uú]mero\s*"
    r")?"
    r"(\d{1,4})\s*[/\.\-]\s*(20\d{2}|19\d{2})",
    re.I,
)

_RE_TIPO_PRIORIDADE = [
    # Orçamentárias / planos (antes de "Lei")
    ("LDO", re.compile(r"\bLDO\b|lei\s+de\s+diretrizes\s+or[cç]ament[aá]rias?", re.I)),
    ("LOA", re.compile(r"\bLOA\b|lei\s+or[cç]ament[aá]rias?\s+anual", re.I)),
    ("PPA", re.compile(r"\bPPA\b|plano\s+plurianual", re.I)),
    ("PCCR", re.compile(r"\bPCCR\b|plano\s+de\s+cargos", re.I)),
    ("Balancete Financeiro", re.compile(r"balancete\s+financeiro", re.I)),
    ("Balanço Anual", re.compile(r"balan[cç]o\s+anual", re.I)),
    ("Relatório do Controle Interno", re.compile(
        r"relat[oó]rio\s+do\s+controle\s+interno", re.I)),
    ("Relatório de Gestão", re.compile(r"relat[oó]rio\s+de\s+gest[aã]o", re.I)),
    ("Norma de Estrutura Organizacional", re.compile(
        r"norma\s+de\s+estrutura\s+organizacional", re.I)),
    ("Demais Publicações Oficiais", re.compile(
        r"demais\s+publica[cç][oõ]es\s+oficiais?", re.I)),
    ("Demais Publicações", re.compile(r"demais\s+publica[cç][oõ]es?\b", re.I)),
    ("Instrução Normativa", re.compile(r"instru[cç][aã]o(?:es)?\s+normativa", re.I)),
    ("Requerimento de Autoria Técnica", re.compile(
        r"requerimento\s+de\s+autoria\s+t[eé]cnica", re.I)),
    ("Ata de Audiência Pública", re.compile(
        r"ata\s+de\s+audi[eê]ncia\s+p[uú]blica", re.I)),
    ("Ato Legislativo Especial", re.compile(r"ato\s+legislativo\s+especial", re.I)),
    ("Ato de Convocação", re.compile(r"ato\s+de\s+convoca[cç][aã]o", re.I)),
    ("Ato da Presidência", re.compile(r"ato\s+da\s+presid[eê]ncia", re.I)),
    ("Ato da Mesa Diretora", re.compile(r"ato\s+da\s+mesa\s+diretora", re.I)),
    ("Ato do Controle Interno", re.compile(r"ato\s+do\s+controle\s+interno", re.I)),
    ("Memorando", re.compile(r"\bmemorandos?\b", re.I)),
    # Matérias / proposições (específico → genérico)
    ("Projeto de Emenda à Lei Orgânica", re.compile(
        r"projeto\s+de\s+emenda\s+[aà]\s+lei\s+org[aâ]nica", re.I)),
    ("Projeto de Emenda ao Regimento Interno", re.compile(
        r"projeto\s+de\s+emenda\s+ao\s+regimento", re.I)),
    ("Projeto de Decreto Legislativo", re.compile(
        r"projeto\s+de\s+decreto\s+legislativo", re.I)),
    ("Projeto de Lei Complementar", re.compile(
        r"projeto\s+de\s+lei\s+complementar", re.I)),
    ("Projeto de Indicação", re.compile(r"projeto\s+de\s+indica[cç][aã]o", re.I)),
    ("Projeto de Resolução", re.compile(r"projeto\s+de\s+resolu[cç][aã]o", re.I)),
    ("Projeto de Lei", re.compile(r"projeto\s+de\s+lei\b", re.I)),
    ("Anteprojeto de Lei", re.compile(r"anteprojeto\s+de\s+lei", re.I)),
    ("Emenda à Lei Orgânica", re.compile(r"emenda\s+[aà]\s+lei\s+org[aâ]nica", re.I)),
    ("Emendas Impositivas", re.compile(r"emendas?\s+impositivas?", re.I)),
    ("Moção de Reconhecimento", re.compile(r"mo[cç][aã]o\s+de\s+reconhecimento", re.I)),
    ("Moção de Aplauso", re.compile(r"mo[cç][aã]o\s+de\s+aplauso", re.I)),
    ("Moção de Pesar", re.compile(r"mo[cç][aã]o\s+de\s+pesar", re.I)),
    ("Pedido de Providência", re.compile(r"pedido\s+de\s+provid[eê]ncia", re.I)),
    ("Iniciativa Popular", re.compile(r"iniciativa\s+popular", re.I)),
    ("Decreto Legislativo", re.compile(r"decreto\s+legislativo", re.I)),
    ("Lei Complementar", re.compile(r"lei\s+complementar", re.I)),
    ("Lei Orgânica", re.compile(r"lei\s+org[aâ]nica", re.I)),
    ("Atos de Promulgação", re.compile(r"atos?\s+de\s+promulga[cç][aã]o", re.I)),
    ("Legislação de Pessoal", re.compile(r"legisla[cç][aã]o\s+de\s+pessoal", re.I)),
    ("Diário Oficial", re.compile(r"di[aá]rio\s+oficial", re.I)),
    ("Regulamentação de Cotas Parlamentares", re.compile(
        r"regulamenta[cç][aã]o\s+de\s+cotas?\s+parlamentares?", re.I)),
    ("Devolvido ao Executivo", re.compile(r"devolvido\s+ao\s+executivo", re.I)),
    ("Notificações", re.compile(r"\bnotifica[cç][oõ]es?\b", re.I)),
    ("Ofício", re.compile(r"\bof[ií]cios?\b", re.I)),
    ("Indicação", re.compile(r"\bindica[cç][oõ]es?\b", re.I)),
    ("Proposições", re.compile(r"\bproposi[cç][oõ]es?\b", re.I)),
    ("Veto", re.compile(r"\bvetos?\b", re.I)),
    ("Portaria", re.compile(r"\bportarias?\b", re.I)),
    ("Decreto", re.compile(r"\bdecretos?\b", re.I)),
    ("Resolução", re.compile(r"\bresolu[cç][aã]o(?:es)?\b", re.I)),
    ("Edital", re.compile(r"\beditais?\b", re.I)),
    ("Moção", re.compile(r"\bmo[cç][aã]o(?:es)?\b", re.I)),
    ("Requerimento", re.compile(r"\brequerimentos?\b", re.I)),
    ("Lei", re.compile(r"\b(?:lei(?:s)?\s+municipal(?:is)?|leis?)\b", re.I)),
]

_LINK_GENERICO = re.compile(
    r"^(clique\s+aqui(?:\s+para\s+(?:visualizar|baixar|download|ler|abrir))?|"
    r"baixar|download|visualizar|pdf|arquivo|"
    r"veja\s+aqui|acesse(?:\s+aqui)?)[\s\.\!]*$",
    re.I,
)


def _extrair_numero_ano(*textos: str):
    for texto in textos:
        if not texto:
            continue
        m = _RE_NUM_ANO.search(_normalizar_texto(texto))
        if m:
            return int(m.group(1)), int(m.group(2))
    # fallback: Nº 738 de 2023 / 738.2023 no basename
    for texto in textos:
        t = _normalizar_texto(texto)
        m = re.search(
            r"n[º°o\.]*\s*(\d{1,4}).{0,40}?(20\d{2}|19\d{2})",
            t,
            re.I,
        )
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r"(?<!\d)(\d{1,4})[.\-](20\d{2}|19\d{2})(?!\d)", t)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None, None


def _detectar_tipo(*textos: str, pasta_hint: str = "") -> str | None:
    """Detecta o tipo em cada texto na ordem dada (primeiro sinal válido vence)."""
    for texto in textos:
        blob = _normalizar_texto(texto)
        if not blob:
            continue
        # Só o cabeçalho (evita 'revoga a Portaria X' no corpo do decreto)
        cabeca = blob[:320]
        for tipo, rx in _RE_TIPO_PRIORIDADE:
            if rx.search(cabeca):
                return tipo
    hint = limpar_nome_pasta(pasta_hint or "")
    if hint:
        for tipo, rx in _RE_TIPO_PRIORIDADE:
            if rx.search(hint):
                return tipo
        # Fora do catálogo: pasta/título da fonte vira o tipo
        return hint
    # Sem pasta do catálogo: usa o título/item mais descritivo
    for texto in textos:
        if not texto:
            continue
        if _LINK_GENERICO.match((texto or "").strip()):
            continue
        t = limpar_nome_pasta(_normalizar_texto(texto))
        if not t or len(t) < 3:
            continue
        t = re.split(
            r"\s*[-|–]\s*(?:Prefeitura|C[aâ]mara|Portal)\b",
            t,
            maxsplit=1,
            flags=re.I,
        )[0].strip()
        if t:
            return t[:100]
    return None


def _tipos_catalogo() -> list[str]:
    return [nome for nome, _ in _RE_TIPO_PRIORIDADE]


def _aplicar_ia_nome(nome: str, textos: list[str]) -> str:
    """Opcional: corrige tipo/número/ano com Ollama quando as regras falham."""
    if not REFINAR_IA:
        return nome
    auto = Path(__file__).resolve().parents[1]
    if str(auto) not in sys.path:
        sys.path.insert(0, str(auto))
    try:
        from _comum import refinar_nome_documento
    except ImportError as exc:
        print("    [IA]      pacote _comum indisponível ({0})".format(exc))
        return nome
    return refinar_nome_documento(
        nome_regras=nome,
        textos=textos,
        tipos_catalogo=_tipos_catalogo(),
        modelo=MODELO_IA,
        ollama_url=OLLAMA_URL,
        forcar=IA_SEMPRE,
    )


def montar_nome_documento(
    *,
    texto_link: str = "",
    titulo_post: str = "",
    texto_pdf: str = "",
    url_pdf: str = "",
    pasta_hint: str = "",
    ano_fallback: int | None = None,
) -> str:
    """
    Retorna nome lógico sem extensão, ex.: 'Portaria Nº010/2025'
    Se não estiver no catálogo, usa o título/item da página.
    """
    basename = os.path.basename(urlparse(url_pdf).path) if url_pdf else ""
    link_util = ""
    if texto_link and not _LINK_GENERICO.match(texto_link.strip()):
        link_util = texto_link

    tipo = _detectar_tipo(
        link_util,
        titulo_post,
        (texto_pdf or "")[:400],
        basename,
        pasta_hint=pasta_hint,
    )
    num, ano = _extrair_numero_ano(link_util, titulo_post, texto_pdf, basename)

    nomes_catalogo = {nome for nome, _ in _RE_TIPO_PRIORIDADE}
    tipo_catalogo = bool(tipo and tipo in nomes_catalogo)

    if tipo_catalogo and num is not None and ano is not None:
        return f"{tipo} Nº{str(num).zfill(3)}/{ano}"

    if tipo_catalogo and num is not None and ano_fallback:
        return f"{tipo} Nº{str(num).zfill(3)}/{ano_fallback}"

    # Fora do catálogo (ou sem número): nome do item / título
    candidato = link_util or titulo_post or tipo or basename or "Documento"
    candidato = _normalizar_texto(candidato)
    candidato = re.split(
        r"\s*[-|–]\s*(?:Prefeitura|C[aâ]mara|Portal)\b",
        candidato,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    candidato = re.sub(r"\s*\(.*?\)\s*$", "", candidato)
    candidato = limpar_nome_pasta(candidato) or "Documento"
    candidato = candidato[:120].strip(" .-_")
    if not candidato:
        candidato = "Documento"
    if ano_fallback and not re.search(r"20\d{2}|19\d{2}", candidato):
        candidato = f"{candidato} {ano_fallback}"
    return candidato


# =============================================================
# Extração de PDF / HTML
# =============================================================

def ler_texto_pdf_bytes(data: bytes, max_paginas: int = MAX_PAGINAS_PDF) -> str:
    if not data or not PdfReader or data[:4] != b"%PDF":
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        partes = []
        for page in reader.pages[: max(1, max_paginas)]:
            partes.append(page.extract_text() or "")
        return _normalizar_texto("\n".join(partes))
    except Exception:
        return ""


def _carregar_modulo_local(nome: str):
    """Carrega extrair_diarias / ia_diarias do mesmo diretório do script."""
    import importlib.util

    caminho = Path(__file__).resolve().parent / f"{nome}.py"
    spec = importlib.util.spec_from_file_location(nome, caminho)
    if not spec or not spec.loader:
        raise ImportError(nome)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tentar_extrair_diarias(
    data: bytes,
    *,
    texto_pdf: str,
    arquivo: str,
    pasta_hint: str,
    ler_pdf: bool,
    url_fonte: str = "",
) -> None:
    """Regra geral: se a fonte/PDF for de diárias, extrai campos → planilha."""
    if not EXTRAI_DIARIAS:
        return
    try:
        mod_ext = _carregar_modulo_local("extrair_diarias")
        extrair_diarias = mod_ext.extrair_diarias
        parece_diarias = mod_ext.parece_diarias
    except Exception as exc:
        print("    [DIARIAS] módulo indisponível ({0})".format(exc))
        return

    texto = texto_pdf or ""
    # Relê com mais páginas se ainda não há sinal claro de diárias
    if ler_pdf and LER_PDF and (
        not texto
        or not parece_diarias(
            texto, pasta_hint=pasta_hint, nome_arquivo=arquivo, url=url_fonte
        )
    ):
        texto = ler_texto_pdf_bytes(data, max_paginas=MAX_PAGINAS_DIARIAS) or texto

    # Sempre preferir texto mais completo para diárias + IA
    if ler_pdf and LER_PDF and texto:
        texto_largo = ler_texto_pdf_bytes(data, max_paginas=MAX_PAGINAS_DIARIAS)
        if texto_largo and len(texto_largo) > len(texto):
            texto = texto_largo

    reg = extrair_diarias(
        texto, arquivo=arquivo, pasta_hint=pasta_hint, url=url_fonte
    )
    if not reg:
        return

    # IA lê o documento e confirma/corrige os campos (mesmo toggle do Ollama)
    if REFINAR_IA:
        try:
            mod_ia = _carregar_modulo_local("ia_diarias")
            reg = mod_ia.confirmar_diarias_ia(
                reg,
                texto,
                modelo=MODELO_IA,
                ollama_url=OLLAMA_URL,
            )
        except Exception as exc:
            print("    [IA-DIARIAS] erro: {0}".format(str(exc)[:120]))

    # remove meta se sobrou
    reg.pop("_ia_alterou", None)

    REGISTROS_DIARIAS.append(reg)
    preenchidos = sum(1 for k, v in reg.items() if k != "arquivo" and v)
    print(
        "    [DIARIAS]  {0} — {1}/10 campos ({2})".format(
            reg.get("numero_portaria") or "?",
            preenchidos,
            reg.get("nome") or "sem nome",
        )
    )


def _podar_conteudo_relacionado(root) -> None:
    marcadores = re.compile(
        r"conte[uú]do\s+relacionado|posts?\s+relacionados?|"
        r"related\s+posts?|related\s+content|mais\s+leituras",
        re.I,
    )
    while True:
        tag = None
        for t in root.find_all(["h2", "h3", "h4", "div", "p", "strong", "span"]):
            if t.find_parent("aside") or t.find_parent("footer"):
                continue
            if marcadores.search(t.get_text(" ", strip=True)):
                tag = t
                break
        if tag is None:
            break
        pai = tag.parent
        if pai is None:
            tag.decompose()
            continue
        remover = False
        for irmao in list(pai.children):
            if irmao is tag:
                remover = True
            if remover and getattr(irmao, "decompose", None):
                irmao.decompose()


def corpo_principal(soup: BeautifulSoup):
    for sel in (
        "article .post-content",
        ".post-content",
        "article .entry-content",
        ".entry-content",
        "article",
        "main",
    ):
        scope = soup.select_one(sel)
        if scope:
            break
    else:
        scope = soup.body if soup.body else soup
    for aside in scope.find_all("aside"):
        aside.decompose()
    for footer in list(scope.find_all("footer")):
        footer.decompose()
    _podar_conteudo_relacionado(scope)
    return scope


def titulo_da_pagina(soup: BeautifulSoup) -> str:
    for sel in ("h1.post-title", "h1.entry-title", "h1", ".post-title"):
        node = soup.select_one(sel)
        if node:
            return _normalizar_texto(node.get_text(" ", strip=True))
    if soup.title:
        t = soup.title.get_text(" ", strip=True)
        t = re.split(r"\s*[-|–]\s*Prefeitura", t, maxsplit=1)[0]
        return _normalizar_texto(t)
    return ""


def coletar_pdfs_do_soup(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
    """Lista [(texto_link, url_pdf)] únicos, só do domínio do SITE."""
    scope = corpo_principal(soup)
    vistos = set()
    saida = []
    for tag in scope.find_all("a", href=True):
        href = tag["href"].strip()
        if not _eh_pdf_href(href):
            continue
        abs_url = _absolutizar(base_url, href)
        if not _mesmo_dominio(abs_url, SITE):
            continue
        if abs_url in vistos:
            continue
        vistos.add(abs_url)
        texto = _normalizar_texto(tag.get_text(" ", strip=True))
        saida.append((texto, abs_url))
    return saida


def obter_pdfs_do_post(url_post: str) -> tuple[str, list[tuple[str, str]]]:
    resp = _get(url_post)
    soup = BeautifulSoup(resp.content, "html.parser")
    titulo = titulo_da_pagina(soup)
    pdfs = coletar_pdfs_do_soup(soup, resp.url)
    return titulo, pdfs


# =============================================================
# Coleta de posts / hubs
# =============================================================

_IGNORAR_HREF = (
    "/o-municipio",
    "/webmail",
    "/admin",
    "/mapa",
    "/author",
    "facebook",
    "twitter",
    "instagram",
    "youtube",
    "mailto:",
    "/page/",
    "wp-content/uploads",
    "portalcr2",
    "cookie",
    "acessibilidade",
)


def _parece_item_listagem(texto: str, href: str) -> bool:
    path = urlparse(href).path.lower()
    if any(x in href.lower() for x in _IGNORAR_HREF):
        return False
    if path.rstrip("/").endswith(("/leis", "/portarias", "/demais", "/decretos", "/publicacoes")):
        return False
    # datas estilo "jan 01" / "dez 18"
    if re.search(r"\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\s+\d{1,2}\b", texto, re.I):
        return True
    if re.search(
        r"(lei|portaria|decreto|resolu|edital|ata|relat[oó]rio|convoca|"
        r"chamada|projeto-de-lei|demais|pauta|sessao|sessão)",
        path,
        re.I,
    ):
        return True
    if re.search(r"\b(20\d{2}|19\d{2})\b", texto) and len(texto) > 8:
        return True
    return False


def _flatten_form(valor, prefix: str = ""):
    itens = []
    if isinstance(valor, dict):
        for chave, filho in valor.items():
            chave_form = f"{prefix}[{chave}]" if prefix else str(chave)
            itens.extend(_flatten_form(filho, chave_form))
    elif isinstance(valor, (list, tuple)):
        if not valor:
            itens.append((f"{prefix}[]", ""))
        else:
            for i, filho in enumerate(valor):
                itens.extend(_flatten_form(filho, f"{prefix}[{i}]"))
    elif isinstance(valor, bool):
        itens.append((prefix, "1" if valor else "0"))
    elif valor is None:
        itens.append((prefix, ""))
    else:
        itens.append((prefix, str(valor)))
    return itens


def _extrair_bloco_bunyad(soup: BeautifulSoup) -> dict | None:
    for el in soup.select("[data-block]"):
        bruto = el.get("data-block")
        if not bruto:
            continue
        try:
            bloco = json.loads(html_module.unescape(bruto))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(bloco, dict) and bloco.get("id"):
            return bloco
    return None


def _tem_carregar_mais(soup: BeautifulSoup) -> bool:
    return bool(
        soup.select_one(
            ".pagination-more, a.load-button, "
            ".main-pagination[data-type='infinite'], "
            ".main-pagination[data-type='load-more']"
        )
    )


def _ajax_url_wordpress(base_url: str) -> str:
    p = urlparse(base_url)
    return f"{p.scheme}://{p.netloc}/wp-admin/admin-ajax.php"


def _posts_de_soup_categoria(
    soup: BeautifulSoup, base_url: str, url_categoria: str, vistos: set[str]
) -> list[str]:
    novos: list[str] = []
    candidatos: list[tuple[str, str]] = []
    for art in soup.select("article"):
        if art.find_parent("footer") or art.find_parent("nav"):
            continue
        a = art.select_one("a[href]")
        if a:
            candidatos.append((art.get_text(" ", strip=True), a["href"]))
    if not candidatos:
        for li in soup.select("li"):
            if li.find_parent("nav") or li.find_parent("footer"):
                continue
            a = li.find("a", href=True)
            if a:
                candidatos.append((li.get_text(" ", strip=True), a["href"]))

    for texto, href in candidatos:
        abs_url = _absolutizar(base_url, href)
        if not _mesmo_dominio(abs_url, SITE):
            continue
        if abs_url.rstrip("/") == url_categoria.rstrip("/"):
            continue
        if not _parece_item_listagem(texto, abs_url):
            continue
        if abs_url in vistos:
            continue
        vistos.add(abs_url)
        novos.append(abs_url)
    return novos


def coletar_posts_categoria(url_categoria: str) -> list[str]:
    """Coleta URLs únicas de posts.

    Preferência:
      1) AJAX Bunyad (Carregar Mais / infinite) — /page/N/ nesses temas
         costuma repetir os mesmos posts.
      2) Paginação clássica /page/2/, /page/3/...
    """
    posts: list[str] = []
    vistos: set[str] = set()

    try:
        resp0 = _get(url_categoria)
    except Exception as e:
        print(f"  [ERRO] {e}")
        return posts

    soup0 = BeautifulSoup(resp0.content, "html.parser")
    bloco = _extrair_bloco_bunyad(soup0)

    if bloco and _tem_carregar_mais(soup0):
        print("  Detectado 'Carregar Mais' / infinite scroll (Bunyad).")
        print("  Coletando via AJAX bunyad_block...")
        ajax_url = _ajax_url_wordpress(resp0.url or SITE)
        pagina = 1
        while pagina <= 200:
            _abortar_se_cancelado()
            print(f"  Lote AJAX {pagina}: {ajax_url}")
            try:
                payload = _flatten_form(
                    {"action": "bunyad_block", "block": bloco, "paged": pagina}
                )
                headers = dict(HEADERS)
                headers["X-Requested-With"] = "XMLHttpRequest"
                resp = _SESSION.post(ajax_url, data=payload, headers=headers, timeout=45)
            except Exception as e:
                print(f"  [ERRO] {e}")
                break
            corpo = (resp.text or "").strip()
            if resp.status_code != 200 or corpo in ("", "0", "-1"):
                print("  Fim do infinite scroll.")
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            novos = _posts_de_soup_categoria(soup, resp0.url, url_categoria, vistos)
            posts.extend(novos)
            print(f"  {len(novos)} posts novos. Total: {len(vistos)}")
            if not novos:
                print("  Nenhum post novo. Fim.")
                break
            pagina += 1
            time.sleep(0.6)
        return posts

    pagina = 1
    while True:
        _abortar_se_cancelado()
        if pagina == 1:
            url = url_categoria
            soup = soup0
            base = resp0.url
        else:
            url = url_categoria.rstrip("/") + "/page/" + str(pagina) + "/"
            print(f"  Página {pagina}: {url}")
            try:
                resp = _get(url)
            except Exception as e:
                print(f"  [ERRO] {e}")
                break
            if resp.status_code == 404:
                print("  Fim das páginas.")
                break
            soup = BeautifulSoup(resp.content, "html.parser")
            base = resp.url

        if pagina == 1:
            print(f"  Página {pagina}: {url}")

        novos = _posts_de_soup_categoria(soup, base, url_categoria, vistos)
        print(f"  {len(novos)} posts novos. Total: {len(vistos)}")
        posts.extend(novos)
        if not novos:
            print("  Nenhum post novo. Fim.")
            break
        pagina += 1
        if pagina > 80:
            print("  Limite de páginas atingido.")
            break
        time.sleep(0.6)
    return posts


def coletar_paginas_hub_anos(url_hub: str) -> list[tuple[str, str]]:
    """Retorna [(rótulo, url)] das páginas anuais a partir do hub."""
    resp = _get(url_hub)
    soup = BeautifulSoup(resp.content, "html.parser")
    scope = corpo_principal(soup)
    saida = []
    vistos = set()
    for a in scope.find_all("a", href=True):
        texto = _normalizar_texto(a.get_text(" ", strip=True))
        href = _absolutizar(resp.url, a["href"])
        if not _mesmo_dominio(href, SITE):
            continue
        if href in vistos:
            continue
        if not re.search(r"decretos?\s*(20\d{2}|19\d{2})|(20\d{2}|19\d{2})", texto, re.I):
            # também aceita slug /decretos-2023/
            if not re.search(r"decretos?[-_/]?(20\d{2}|19\d{2})", href, re.I):
                continue
        if _eh_pdf_href(href):
            continue
        vistos.add(href)
        saida.append((texto or href, href))
    return saida


def extrair_ano(*textos: str, fallback: int | None = None) -> int | None:
    for t in textos:
        if not t:
            continue
        m = re.search(r"(20\d{2}|19\d{2})", t)
        if m:
            return int(m.group(1))
    return fallback


def _anos_filtro_norm() -> list[str]:
    return [str(a).strip() for a in (ANOS_FILTRO or []) if str(a).strip()]


def ano_permitido(ano) -> bool:
    """True se o ano passa no filtro (vazio = todos). Sem ano conhecido → pula com filtro ativo."""
    filtro = _anos_filtro_norm()
    if not filtro:
        return True
    if ano is None or str(ano) in ("", "sem_ano", "desconhecido"):
        return False
    return str(ano) in filtro


# =============================================================
# Download
# =============================================================

def baixar_e_salvar(
    url_pdf: str,
    pasta: str,
    nome_logico: str,
    *,
    ler_pdf: bool,
    textos_extras: list[str],
    pasta_hint: str,
    ano_fallback: int | None,
    url_fonte: str = "",
) -> str:
    """
    Baixa o PDF, opcionalmente relê o texto para renomear, salva.
    Retorna: ok | pulado | erro
    """
    # URL da página/fonte + hint: detecta Diárias (ex. /diarias-ate-2023/)
    url_ctx = " ".join(
        [
            url_fonte or "",
            url_pdf or "",
            pasta_hint or "",
            textos_extras[1] if len(textos_extras) > 1 else "",
            textos_extras[0] if textos_extras else "",
        ]
    )
    criar_pasta(pasta)
    try:
        resp = _SESSION.get(url_pdf, timeout=60, stream=True)
        resp.raise_for_status()
        chunks = []
        for chunk in resp.iter_content(8192):
            if chunk:
                chunks.append(chunk)
        data = b"".join(chunks)
        if data[:4] != b"%PDF":
            print(f"    [ERRO]    Resposta não é PDF: {url_pdf}")
            return "erro"

        texto_pdf = ""
        if ler_pdf and LER_PDF:
            texto_pdf = ler_texto_pdf_bytes(data)
            if not texto_pdf:
                print("    [AVISO]    PDF sem texto extraivel (escaneado/imagem) — nome pelo titulo/link")

        # Prefere texto do PDF + título/link; cai no nome prévio se nada útil.
        nome = montar_nome_documento(
            texto_link=textos_extras[0] if textos_extras else "",
            titulo_post=textos_extras[1] if len(textos_extras) > 1 else "",
            texto_pdf=texto_pdf,
            url_pdf=url_pdf,
            pasta_hint=pasta_hint,
            ano_fallback=ano_fallback,
        )
        if nome == "Documento" and nome_logico:
            nome = nome_logico

        # Regra geral: Pautas/Atas/Presença/Votações → pasta por sessão
        pasta_destino = pasta
        org = None
        try:
            mod_sess = _carregar_modulo_local("organizar_sessao")
            org = mod_sess.organizar_destino_sessao(
                pasta_base=PASTA_BASE,
                pasta_hint=pasta_hint,
                ano_fallback=ano_fallback,
                textos=[
                    textos_extras[0] if textos_extras else "",
                    textos_extras[1] if len(textos_extras) > 1 else "",
                    (texto_pdf or "")[:4000],
                ],
                url_fonte=url_ctx,
            )
            if org:
                pasta_destino = org["pasta"]
                nome = org["nome_logico"]
                meta = org["meta"]
                if meta.get("doc_tipo") == "declaracao":
                    print(
                        "    [SESSAO]   Declarações → {0}".format(meta.get("doc_nome"))
                    )
                else:
                    rotulo = mod_sess.prefixo_pasta_sessao(
                        meta.get("numero"),
                        meta.get("tipo") or "",
                        meta.get("evento") or "",
                    )
                    print(
                        "    [SESSAO]   {0} ({1}) → {2}".format(
                            rotulo,
                            meta.get("data") or "s/data",
                            meta.get("doc_nome"),
                        )
                    )
        except Exception as exc:
            print("    [SESSAO]   organização indisponível ({0})".format(str(exc)[:80]))
            org = None

        # IA só no nome genérico — não sobrescreve Pauta/Ata da pasta de sessão
        if not org:
            nome = _aplicar_ia_nome(
                nome,
                [
                    textos_extras[0] if textos_extras else "",
                    textos_extras[1] if len(textos_extras) > 1 else "",
                    (texto_pdf or "")[:3500],
                ],
            )

        criar_pasta(pasta_destino)
        arquivo = nome_arquivo_final(nome)
        caminho = os.path.join(pasta_destino, arquivo)

        # colisão: mesmo nome, outro conteúdo → sufixo
        if os.path.exists(caminho):
            if os.path.getsize(caminho) == len(data):
                print(f"    [PULADO]  {arquivo} (já existe)")
                _tentar_extrair_diarias(
                    data,
                    texto_pdf=texto_pdf,
                    arquivo=arquivo,
                    pasta_hint=pasta_hint,
                    ler_pdf=ler_pdf,
                    url_fonte=url_ctx,
                )
                return "pulado"
            stem = arquivo[:-4]
            n = 2
            while True:
                alt = f"{stem} ({n}).pdf"
                alt_path = os.path.join(pasta_destino, alt)
                if not os.path.exists(alt_path):
                    arquivo = alt
                    caminho = alt_path
                    break
                n += 1

        with open(caminho, "wb") as f:
            f.write(data)
        kb = len(data) / 1024
        try:
            print(f"    [OK]      {arquivo} ({round(kb, 1)} KB) <- {nome}")
            if pasta_destino != pasta:
                print(f"             em {pasta_destino}")
        except UnicodeEncodeError:
            print(f"    [OK]      {arquivo} ({round(kb, 1)} KB)")

        _tentar_extrair_diarias(
            data,
            texto_pdf=texto_pdf,
            arquivo=arquivo,
            pasta_hint=pasta_hint,
            ler_pdf=ler_pdf,
            url_fonte=url_ctx,
        )
        return "ok"
    except UnicodeEncodeError:
        # Log/console Windows (cp1252) — nao e falha de download
        return "ok"
    except Exception as e:
        print(f"    [ERRO]    {url_pdf} - {e}")
        return "erro"


# =============================================================
# Processadores por modo
# =============================================================

def processar_categoria(fonte: dict, contadores: dict) -> None:
    url = fonte["url"]
    titulo_fonte = ""
    if not (fonte.get("pasta") or "").strip():
        titulo_fonte = obter_titulo_fonte(url)
    pasta_hint = resolver_pasta_hint(fonte, titulo_fonte)
    print("")
    print("=" * 60)
    print(f"  FONTE (categoria): {url}")
    print(f"  Pasta: {pasta_hint}" + (f" (de: {titulo_fonte})" if titulo_fonte and not (fonte.get("pasta") or "").strip() else ""))
    print("=" * 60)

    posts = coletar_posts_categoria(url)
    if LIMITE_POSTS and LIMITE_POSTS > 0:
        posts = posts[:LIMITE_POSTS]
        print(f"  Limite de teste: {len(posts)} posts")

    total = len(posts)
    for i, url_post in enumerate(posts, 1):
        _abortar_se_cancelado()
        prefix = f"[{str(i).zfill(3)}/{total}]"
        slug = url_post.rstrip("/").split("/")[-1][:60]
        print(f"{prefix} {slug}")
        try:
            titulo, pdfs = obter_pdfs_do_post(url_post)
        except Exception as e:
            print(f"    [ERRO]    abrir post: {e}")
            contadores["erros"] += 1
            continue

        if not pdfs:
            print("    [SEM PDF] Nenhum PDF no corpo do post.")
            contadores["sem_pdf"] += 1
            time.sleep(0.25)
            continue

        ano = extrair_ano(titulo, url_post)
        if not ano_permitido(ano):
            print(f"    [PULADO]  Ano {ano or 'desconhecido'} fora do filtro.")
            contadores["pulado_ano"] = contadores.get("pulado_ano", 0) + 1
            continue
        pasta = os.path.join(PASTA_BASE, pasta_hint, str(ano or "sem_ano"))
        print(f"    {len(pdfs)} PDF(s) | titulo: {titulo[:80]}")

        for texto_link, url_pdf in pdfs:
            _abortar_se_cancelado()
            nome_previo = montar_nome_documento(
                texto_link=texto_link,
                titulo_post=titulo,
                url_pdf=url_pdf,
                pasta_hint=pasta_hint,
                ano_fallback=ano,
            )
            resultado = baixar_e_salvar(
                url_pdf,
                pasta,
                nome_previo,
                ler_pdf=True,
                textos_extras=[texto_link, titulo],
                pasta_hint=pasta_hint,
                ano_fallback=ano,
                url_fonte=url,
            )
            contadores[resultado] = contadores.get(resultado, 0) + 1
        time.sleep(0.35)


def processar_hub_anos(fonte: dict, contadores: dict) -> None:
    url = fonte["url"]
    titulo_fonte = ""
    if not (fonte.get("pasta") or "").strip():
        titulo_fonte = obter_titulo_fonte(url)
    pasta_hint = resolver_pasta_hint(fonte, titulo_fonte)
    print("")
    print("=" * 60)
    print(f"  FONTE (hub anos): {url}")
    print(f"  Pasta: {pasta_hint}" + (f" (de: {titulo_fonte})" if titulo_fonte and not (fonte.get("pasta") or "").strip() else ""))
    print("=" * 60)

    paginas = coletar_paginas_hub_anos(url)
    print(f"  {len(paginas)} página(s) anual(is) encontrada(s).")
    filtro = _anos_filtro_norm()
    if filtro:
        antes = len(paginas)
        paginas = [
            (rotulo, url_ano)
            for rotulo, url_ano in paginas
            if ano_permitido(extrair_ano(rotulo, url_ano))
        ]
        print(f"  Filtro de anos ({', '.join(filtro)}): {len(paginas)}/{antes} página(s).")
    if LIMITE_POSTS and LIMITE_POSTS > 0:
        paginas = paginas[:LIMITE_POSTS]

    for i, (rotulo, url_ano) in enumerate(paginas, 1):
        _abortar_se_cancelado()
        print(f"[{str(i).zfill(2)}/{len(paginas)}] {rotulo} -> {url_ano}")
        try:
            resp = _get(url_ano)
            soup = BeautifulSoup(resp.content, "html.parser")
            titulo = titulo_da_pagina(soup) or rotulo
            pdfs = coletar_pdfs_do_soup(soup, resp.url)
        except Exception as e:
            print(f"    [ERRO]    {e}")
            contadores["erros"] += 1
            continue

        if not pdfs:
            print("    [SEM PDF]")
            contadores["sem_pdf"] += 1
            continue

        ano = extrair_ano(rotulo, titulo, url_ano)
        if not ano_permitido(ano):
            print(f"    [PULADO]  Ano {ano or 'desconhecido'} fora do filtro.")
            contadores["pulado_ano"] = contadores.get("pulado_ano", 0) + 1
            continue
        pasta = os.path.join(PASTA_BASE, pasta_hint, str(ano or "sem_ano"))
        print(f"    {len(pdfs)} PDF(s)")

        for texto_link, url_pdf in pdfs:
            _abortar_se_cancelado()
            nome_previo = montar_nome_documento(
                texto_link=texto_link,
                titulo_post=titulo,
                url_pdf=url_pdf,
                pasta_hint=pasta_hint,
                ano_fallback=ano,
            )
            resultado = baixar_e_salvar(
                url_pdf,
                pasta,
                nome_previo,
                ler_pdf=True,
                textos_extras=[texto_link, titulo],
                pasta_hint=pasta_hint,
                ano_fallback=ano,
                url_fonte=url,
            )
            contadores[resultado] = contadores.get(resultado, 0) + 1
        time.sleep(0.4)


def processar_pagina(fonte: dict, contadores: dict) -> None:
    url = fonte["url"]
    print("")
    print("=" * 60)
    print(f"  FONTE (página): {url}")
    print("=" * 60)
    try:
        resp = _get(url)
        soup = BeautifulSoup(resp.content, "html.parser")
        titulo = titulo_da_pagina(soup)
        pdfs = coletar_pdfs_do_soup(soup, resp.url)
    except Exception as e:
        print(f"  [ERRO] {e}")
        contadores["erros"] += 1
        return

    pasta_hint = resolver_pasta_hint(fonte, titulo)
    print(f"  Pasta: {pasta_hint}")

    ano = extrair_ano(titulo, url)
    if not ano_permitido(ano):
        print(f"  [PULADO] Ano {ano or 'desconhecido'} fora do filtro.")
        contadores["pulado_ano"] = contadores.get("pulado_ano", 0) + 1
        return
    pasta = os.path.join(PASTA_BASE, pasta_hint, str(ano or "sem_ano"))
    print(f"  {len(pdfs)} PDF(s)")
    for texto_link, url_pdf in pdfs:
        _abortar_se_cancelado()
        nome_previo = montar_nome_documento(
            texto_link=texto_link,
            titulo_post=titulo,
            url_pdf=url_pdf,
            pasta_hint=pasta_hint,
            ano_fallback=ano,
        )
        resultado = baixar_e_salvar(
            url_pdf,
            pasta,
            nome_previo,
            ler_pdf=True,
            textos_extras=[texto_link, titulo],
            pasta_hint=pasta_hint,
            ano_fallback=ano,
            url_fonte=url,
        )
        contadores[resultado] = contadores.get(resultado, 0) + 1


# =============================================================
# Main
# =============================================================

def main():
    global REGISTROS_DIARIAS
    REGISTROS_DIARIAS = []

    print("=" * 60)
    print("  DOWNLOAD DE NORMAS MUNICIPAIS")
    print(f"  Site: {urlparse(SITE).netloc}")
    print(f"  Destino: {PASTA_BASE}")
    print(f"  Leitura PDF: {'sim' if LER_PDF and PdfReader else 'não'}")
    print(f"  Diárias → planilha: {'sim' if EXTRAI_DIARIAS else 'não'}")
    print(f"  IA local: {'sim ({0})'.format(MODELO_IA) if REFINAR_IA else 'não'}")
    filtro = _anos_filtro_norm()
    print(f"  Anos: {', '.join(filtro) if filtro else 'todos'}")
    if LER_PDF and not PdfReader:
        print("  [AVISO] pypdf não instalado — nomes só pelo HTML.")
        print("          pip install pypdf")
    print("=" * 60)

    criar_pasta(PASTA_BASE)
    contadores = {"ok": 0, "pulado": 0, "erro": 0, "erros": 0, "sem_pdf": 0, "pulado_ano": 0}
    cancelado = False

    try:
        for fonte in FONTES:
            _abortar_se_cancelado()
            modo = (fonte.get("modo") or "categoria").lower().strip()
            if modo == "categoria":
                processar_categoria(fonte, contadores)
            elif modo == "hub_anos":
                processar_hub_anos(fonte, contadores)
            elif modo == "pagina":
                processar_pagina(fonte, contadores)
            else:
                print(f"[AVISO] Modo desconhecido: {modo} ({fonte.get('url')})")
    except Cancelado:
        cancelado = True

    planilha_diarias = ""
    if EXTRAI_DIARIAS and REGISTROS_DIARIAS:
        try:
            from extrair_diarias import salvar_planilha_diarias
        except ImportError:
            import importlib.util

            caminho = Path(__file__).resolve().parent / "extrair_diarias.py"
            spec = importlib.util.spec_from_file_location("extrair_diarias", caminho)
            salvar_planilha_diarias = None
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                salvar_planilha_diarias = mod.salvar_planilha_diarias
        if salvar_planilha_diarias:
            saida = salvar_planilha_diarias(REGISTROS_DIARIAS, PASTA_BASE)
            if saida:
                planilha_diarias = str(saida)
                print(f"  [DIARIAS] Planilha: {planilha_diarias} ({len(REGISTROS_DIARIAS)} linhas)")

    planilha_sessoes = ""
    try:
        pub_sess = Path(__file__).resolve().parents[1] / "publicacao-sessao" / "script.py"
        if pub_sess.is_file():
            import importlib.util

            spec = importlib.util.spec_from_file_location("publicacao_sessao_planilha", pub_sess)
            if spec and spec.loader:
                mod_ps = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod_ps)
                saida_s = mod_ps.gerar_planilha_da_pasta(PASTA_BASE)
                if saida_s:
                    planilha_sessoes = str(saida_s)
                    print(f"  [SESSAO] Planilha publicação: {planilha_sessoes}")
    except Exception as exc:
        print("  [SESSAO] Planilha não gerada ({0})".format(str(exc)[:80]))

    print("")
    print("=" * 60)
    print("  RESUMO FINAL" + (" (CANCELADO)" if cancelado else ""))
    print("=" * 60)
    print(f"  PDFs OK                    : {contadores.get('ok', 0)}")
    print(f"  PDFs pulados (ja existiam) : {contadores.get('pulado', 0)}")
    print(f"  Posts fora do filtro ano   : {contadores.get('pulado_ano', 0)}")
    print(f"  Erros download             : {contadores.get('erro', 0) + contadores.get('erros', 0)}")
    print(f"  Posts/paginas sem PDF      : {contadores.get('sem_pdf', 0)}")
    print(f"  Diárias extraídas          : {len(REGISTROS_DIARIAS)}")
    if planilha_diarias:
        print(f"  Planilha Diárias           : {planilha_diarias}")
    if planilha_sessoes:
        print(f"  Planilha Sessões           : {planilha_sessoes}")
    print(f"  Pasta base                 : {PASTA_BASE}")
    print("=" * 60)
    if cancelado:
        raise Cancelado()


if __name__ == "__main__":
    main()
