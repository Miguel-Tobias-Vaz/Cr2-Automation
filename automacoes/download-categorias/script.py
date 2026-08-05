"""Lista uma categoria WordPress, abre cada post e baixa PDF(s).

Coleta baseada em download-normas (modo categoria):
  1) AJAX Bunyad (Carregar Mais / infinite scroll) via bunyad_block
  2) Paginação clássica /page/2/, /page/3/...

Nomeia arquivos no mesmo padrão de normas:
  Portaria Nº010/2025.pdf  →  Portaria Nº010-2025.pdf no disco
  Lei Nº738/2023.pdf
  Ata Nº064/2023.pdf

Quando o link é genérico ("Clique aqui"), lê o texto do PDF (pypdf)
e/ou o título do post para classificar e numerar.

Requisito: pip install requests beautifulsoup4 pypdf
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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

# --- O que você deve mudar ---
# PASTA_BASE: onde salvar (cria subpastas categoria_2023, categoria_2024...)
# URL_CATEGORIA: página da categoria que lista os posts, com / no final
# SITE: mesmo domínio da URL acima, só https://... (sem path depois)
PASTA_BASE = r"C:\Downloads"
URL_CATEGORIA = "https://camaraparagominas.pa.gov.br/portal-da-transparencia/legislacao-de-pessoal-do-municipio/"
SITE = "https://camaraparagominas.pa.gov.br"
# Filtro de anos: lista de strings, ex. ["2023"] ou ["2022", "2023"].
# Lista vazia = baixa TODOS os anos.
ANOS_FILTRO = []
# Limite opcional de posts (0 = todos). Útil para teste.
LIMITE_POSTS = 0
# Lê as primeiras páginas do PDF para refinar o nome (recomendado).
LER_PDF = True
MAX_PAGINAS_PDF = 2

# IA local (Ollama) — corrige nome quando regras falham.
REFINAR_IA = False
MODELO_IA = "llama3.2:3b"
OLLAMA_URL = "http://127.0.0.1:11434"
IA_SEMPRE = False

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

MAX_PAGINAS = 80
MAX_PAGINAS_AJAX = 200


class Cancelado(Exception):
    """Fila interrompida pelo usuario (centro-automacoes)."""


def pedido_cancelado():
    return False


def _abortar_se_cancelado():
    if pedido_cancelado():
        print("  [AVISO] Fila cancelada pelo usuario.")
        raise Cancelado()


def criar_pasta(pasta):
    os.makedirs(pasta, exist_ok=True)


def extrair_ano_da_url(url):
    match = re.search(r"-(20\d{2}|19\d{2})-", url)
    if match:
        return int(match.group(1))
    match = re.search(r"\b(20\d{2}|19\d{2})\b", url)
    if match:
        return int(match.group(1))
    return "desconhecido"


def _anos_filtro_norm():
    return [str(a).strip() for a in (ANOS_FILTRO or []) if str(a).strip()]


def ano_permitido(ano):
    filtro = _anos_filtro_norm()
    if not filtro:
        return True
    if ano is None or str(ano) in ("", "desconhecido", "sem_ano"):
        return False
    return str(ano) in filtro


def _mesmo_dominio(url_a, url_b):
    host_a = urlparse(url_a).netloc.lower().replace("www.", "")
    host_b = urlparse(url_b).netloc.lower().replace("www.", "")
    return host_a == host_b and bool(host_a)


def _absolutizar(base, href):
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return urljoin(base, href)


def _get(url, timeout=45):
    resp = _SESSION.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp


def limpar_nome_arquivo(nome: str) -> str:
    for c in '<>:"/\\|?*':
        nome = nome.replace(c, "-")
    nome = re.sub(r"\s+", " ", nome).strip()
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


def _normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKC", texto)
    texto = texto.replace("\xa0", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


# =============================================================
# Classificação / nomenclatura (igual download-normas)
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
    ("LDO", re.compile(r"\bLDO\b", re.I)),
    ("LOA", re.compile(r"\bLOA\b", re.I)),
    ("Portaria", re.compile(r"\bportarias?\b", re.I)),
    ("Decreto", re.compile(r"\bdecretos?\b", re.I)),
    ("Resolução", re.compile(r"\bresolu[cç][aã]o(?:es)?\b", re.I)),
    ("Edital", re.compile(r"\beditais?\b", re.I)),
    ("Moção", re.compile(r"\bmo[cç][aã]o(?:es)?\b", re.I)),
    ("Requerimento", re.compile(r"\brequerimentos?\b", re.I)),
    ("Pauta", re.compile(r"\bpautas?\b", re.I)),
    ("Ata", re.compile(r"\batas?\b", re.I)),
    ("Lei", re.compile(r"\b(?:lei(?:s)?\s+municipal(?:is)?|projeto\s+de\s+lei|leis?)\b", re.I)),
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
        # Ex.: "64ª SESSÃO ... 2023" / "10a sessão extraordinaria ... 2023"
        m = re.search(
            r"(?<!\d)(\d{1,4})\s*[ªa]\b.{0,100}?(20\d{2}|19\d{2})",
            t,
            re.I,
        )
        if m:
            return int(m.group(1)), int(m.group(2))
    return None, None


def _detectar_tipo(*textos: str, pasta_hint: str = "") -> str | None:
    for texto in textos:
        blob = _normalizar_texto(texto)
        if not blob:
            continue
        cabeca = blob[:280]
        for tipo, rx in _RE_TIPO_PRIORIDADE:
            if rx.search(cabeca):
                return tipo
    hint = (pasta_hint or "").lower()
    if "portaria" in hint:
        return "Portaria"
    if "decreto" in hint:
        return "Decreto"
    if "moç" in hint or "moc" in hint:
        return "Moção"
    if "requerimento" in hint:
        return "Requerimento"
    if "pauta" in hint:
        return "Pauta"
    if "ata" in hint:
        return "Ata"
    if "lei" in hint:
        return "Lei"
    return None


def _tipos_catalogo() -> list:
    return [nome for nome, _ in _RE_TIPO_PRIORIDADE]


def _aplicar_ia_nome(nome, textos):
    if not REFINAR_IA:
        return nome
    auto = Path(__file__).resolve().parents[1]
    if str(auto) not in sys.path:
        sys.path.insert(0, str(auto))
    try:
        from _comum import refinar_nome_documento
    except ImportError as exc:
        print("    [IA]      pacote _comum indisponivel ({0})".format(exc))
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
    """Retorna nome lógico sem extensão, ex.: 'Portaria Nº010/2025'."""
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

    if tipo and num is not None and ano is not None:
        return f"{tipo} Nº{str(num).zfill(3)}/{ano}"

    if tipo and num is not None and ano_fallback:
        return f"{tipo} Nº{str(num).zfill(3)}/{ano_fallback}"

    candidato = link_util
    if not candidato:
        candidato = titulo_post or basename or "Documento"
    candidato = _normalizar_texto(candidato)
    candidato = re.sub(r"\s*\(.*?\)\s*$", "", candidato)
    candidato = candidato[:120].strip(" .-_")
    if not candidato:
        candidato = "Documento"
    if ano_fallback and not re.search(r"20\d{2}|19\d{2}", candidato):
        candidato = f"{candidato} {ano_fallback}"
    return candidato


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


# =============================================================
# Coleta de posts (mesma lógica de download-normas)
# =============================================================

_IGNORAR_HREF = (
    "/o-municipio",
    "/a-camara",
    "/webmail",
    "/admin",
    "/mapa",
    "/author",
    "/contracheque",
    "portalcr2",
    "facebook",
    "twitter",
    "instagram",
    "youtube",
    "mailto:",
    "/lgpd",
    "/sapl",
    "/tcm",
    "/page/",
    "wp-content/uploads",
    "cookie",
    "acessibilidade",
)


def _parece_item_listagem(texto, href):
    """Filtro permissivo igual ao de download-normas."""
    path = urlparse(href).path.lower()
    low = href.lower()
    if any(x in low for x in _IGNORAR_HREF):
        return False
    if path.rstrip("/").endswith(
        ("/leis", "/portarias", "/demais", "/decretos", "/publicacoes")
    ):
        return False
    if re.search(
        r"\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\s+\d{1,2}\b",
        texto,
        re.I,
    ):
        return True
    if re.search(
        r"(lei|portaria|decreto|resolu|edital|ata|relat[oó]rio|convoca|"
        r"chamada|projeto-de-lei|demais|pauta|sessao|sessão|legislacao|"
        r"legisla[cç][aã]o)",
        path,
        re.I,
    ):
        return True
    if re.search(r"\b(20\d{2}|19\d{2})\b", texto) and len(texto) > 8:
        return True
    # Título de post com link no mesmo domínio e path "de post" (slug longo)
    slug = path.rstrip("/").split("/")[-1]
    if slug and "-" in slug and len(slug) > 12:
        return True
    return False


def _flatten_form(valor, prefix=""):
    """Serializa dict/list no formato que o jQuery/PHP espera no admin-ajax."""
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


def _extrair_bloco_bunyad(soup):
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


def _tem_carregar_mais(soup):
    return bool(
        soup.select_one(
            ".pagination-more, a.load-button, "
            ".main-pagination[data-type='infinite'], "
            ".main-pagination[data-type='load-more']"
        )
    )


def _ajax_url_wordpress(base_url):
    p = urlparse(base_url)
    return f"{p.scheme}://{p.netloc}/wp-admin/admin-ajax.php"


def _candidatos_listagem(soup):
    """Extrai (texto, href) dos posts da listagem.

    - Arquivo WP com vários <article>: usa os cards (como normas).
    - Página índice com links no corpo (ex.: Paragominas): varre .post-content.
    """
    cards = []
    for art in soup.select("article"):
        if art.find_parent("footer") or art.find_parent("nav"):
            continue
        a = (
            art.select_one("a.post-title[href]")
            or art.select_one("h2 a[href], h3 a[href]")
            or art.select_one("a[href]")
        )
        if a and a.get("href"):
            cards.append((art.get_text(" ", strip=True), a["href"]))

    # Arquivo clássico / AJAX Bunyad: vários posts em cards
    if len(cards) >= 2:
        return cards

    candidatos = []
    vistos = set()

    def _add(texto, href):
        href = (href or "").strip()
        if not href or href.startswith("#"):
            return
        if href in vistos:
            return
        vistos.add(href)
        candidatos.append((texto or "", href))

    for texto, href in cards:
        _add(texto, href)

    for sel in (".post-content", ".entry-content", "article .content", "article"):
        scope = soup.select_one(sel)
        if not scope:
            continue
        for a in scope.find_all("a", href=True):
            if a.find_parent("nav") or a.find_parent("footer") or a.find_parent("aside"):
                continue
            _add(a.get_text(" ", strip=True), a["href"])
        if len(candidatos) > len(cards):
            return candidatos

    if candidatos:
        return candidatos

    for li in soup.select("li"):
        if li.find_parent("nav") or li.find_parent("footer"):
            continue
        a = li.find("a", href=True)
        if a:
            _add(li.get_text(" ", strip=True), a["href"])
    return candidatos


def _posts_de_soup_categoria(soup, base_url, url_categoria, vistos):
    novos = []
    for texto, href in _candidatos_listagem(soup):
        abs_url = _absolutizar(base_url, href)
        if not abs_url:
            continue
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


def coletar_posts_categoria(url_categoria):
    """Coleta URLs únicas de posts (mesma estratégia de download-normas)."""
    posts = []
    vistos = set()

    try:
        resp0 = _get(url_categoria)
    except Exception as e:
        print("  [ERRO] " + str(e))
        return posts

    soup0 = BeautifulSoup(resp0.content, "html.parser")
    bloco = _extrair_bloco_bunyad(soup0)

    if bloco and _tem_carregar_mais(soup0):
        print("  Detectado 'Carregar Mais' / infinite scroll (Bunyad).")
        print("  Coletando via AJAX bunyad_block...")
        ajax_url = _ajax_url_wordpress(resp0.url or SITE)
        pagina = 1
        while pagina <= MAX_PAGINAS_AJAX:
            _abortar_se_cancelado()
            print("  Lote AJAX " + str(pagina) + ": " + ajax_url)
            try:
                payload = _flatten_form(
                    {"action": "bunyad_block", "block": bloco, "paged": pagina}
                )
                headers = dict(HEADERS)
                headers["X-Requested-With"] = "XMLHttpRequest"
                resp = _SESSION.post(
                    ajax_url, data=payload, headers=headers, timeout=45
                )
            except Exception as e:
                print("  [ERRO] " + str(e))
                break
            corpo = (resp.text or "").strip()
            if resp.status_code != 200 or corpo in ("", "0", "-1"):
                print("  Fim do infinite scroll.")
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            novos = _posts_de_soup_categoria(
                soup, resp0.url, url_categoria, vistos
            )
            posts.extend(novos)
            print(
                "  "
                + str(len(novos))
                + " posts novos. Total: "
                + str(len(vistos))
            )
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
            print("  Pagina " + str(pagina) + ": " + url)
            try:
                resp = _get(url)
            except Exception as e:
                # 404 / redirect inválido → fim
                print("  Fim das paginas (" + str(e) + ").")
                break
            if resp.status_code == 404:
                print("  Fim das paginas.")
                break
            # Se redirecionou de volta para a página 1, acabou
            if resp.url.rstrip("/") == url_categoria.rstrip("/"):
                print("  Redirect para a pagina 1. Fim.")
                break
            soup = BeautifulSoup(resp.content, "html.parser")
            base = resp.url

        if pagina == 1:
            print("  Pagina " + str(pagina) + ": " + url)

        novos = _posts_de_soup_categoria(soup, base, url_categoria, vistos)
        print(
            "  "
            + str(len(novos))
            + " posts novos. Total: "
            + str(len(vistos))
        )
        posts.extend(novos)
        if not novos:
            print("  Nenhum post novo. Fim.")
            break
        pagina += 1
        if pagina > MAX_PAGINAS:
            print("  Limite de paginas atingido.")
            break
        time.sleep(0.6)
    return posts


# =============================================================
# PDFs do post
# =============================================================

def _podar_conteudo_relacionado(root):
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


def _corpo_principal_post(soup):
    scope = None
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
    if scope is None:
        scope = soup.body if soup.body else soup
    for aside in scope.find_all("aside"):
        aside.decompose()
    for footer in list(scope.find_all("footer")):
        footer.decompose()
    _podar_conteudo_relacionado(scope)
    return scope


def _eh_pdf_href(href):
    if not href:
        return False
    low = href.split("?")[0].split("#")[0].lower()
    return low.endswith(".pdf") or ("wp-content/uploads" in low and ".pdf" in low)


def titulo_da_pagina(soup) -> str:
    for sel in ("h1.post-title", "h1.entry-title", "h1", ".post-title"):
        node = soup.select_one(sel)
        if node:
            return _normalizar_texto(node.get_text(" ", strip=True))
    if soup.title:
        t = soup.title.get_text(" ", strip=True)
        t = re.split(r"\s*[-|–]\s*", t, maxsplit=1)[0]
        return _normalizar_texto(t)
    return ""


def obter_pdfs_do_post(url_post):
    """Retorna (titulo, [(texto_link, url_pdf), ...])."""
    resp = _get(url_post, timeout=30)
    soup = BeautifulSoup(resp.content, "html.parser")
    titulo = titulo_da_pagina(soup)
    scope = _corpo_principal_post(soup)
    vistos = set()
    ordenados = []
    for tag in scope.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#"):
            continue
        if not _eh_pdf_href(href):
            continue
        abs_url = _absolutizar(resp.url, href)
        if not _mesmo_dominio(abs_url, SITE):
            continue
        if abs_url in vistos:
            continue
        vistos.add(abs_url)
        texto = _normalizar_texto(tag.get_text(" ", strip=True))
        ordenados.append((texto, abs_url))
    return titulo, ordenados


def baixar_e_salvar(
    url_pdf: str,
    pasta: str,
    nome_logico: str,
    *,
    ler_pdf: bool,
    textos_extras: list,
    pasta_hint: str,
    ano_fallback,
) -> str:
    """Baixa o PDF, opcionalmente relê o texto para renomear, salva.
    Retorna: ok | pulado | erro
    """
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
            print("    [ERRO]    Resposta nao e PDF: " + url_pdf)
            return "erro"

        texto_pdf = ""
        if ler_pdf and LER_PDF:
            texto_pdf = ler_texto_pdf_bytes(data)
            if not texto_pdf:
                print(
                    "    [AVISO]    PDF sem texto extraivel "
                    "(escaneado/imagem) — nome pelo titulo/link"
                )

        nome = montar_nome_documento(
            texto_link=textos_extras[0] if textos_extras else "",
            titulo_post=textos_extras[1] if len(textos_extras) > 1 else "",
            texto_pdf=texto_pdf,
            url_pdf=url_pdf,
            pasta_hint=pasta_hint,
            ano_fallback=ano_fallback if isinstance(ano_fallback, int) else None,
        )
        if nome == "Documento" and nome_logico:
            nome = nome_logico

        nome = _aplicar_ia_nome(
            nome,
            [
                textos_extras[0] if textos_extras else "",
                textos_extras[1] if len(textos_extras) > 1 else "",
                (texto_pdf or "")[:3500],
            ],
        )

        arquivo = nome_arquivo_final(nome)
        caminho = os.path.join(pasta, arquivo)

        if os.path.exists(caminho):
            if os.path.getsize(caminho) == len(data):
                print("    [PULADO]  " + arquivo + " (ja existe)")
                return "pulado"
            stem = arquivo[:-4]
            n = 2
            while True:
                alt = stem + " (" + str(n) + ").pdf"
                alt_path = os.path.join(pasta, alt)
                if not os.path.exists(alt_path):
                    arquivo = alt
                    caminho = alt_path
                    break
                n += 1

        with open(caminho, "wb") as f:
            f.write(data)
        kb = len(data) / 1024
        try:
            print(
                "    [OK]      "
                + arquivo
                + " ("
                + str(round(kb, 1))
                + " KB) <- "
                + nome
            )
        except UnicodeEncodeError:
            print("    [OK]      " + arquivo + " (" + str(round(kb, 1)) + " KB)")
        return "ok"
    except Exception as e:
        print("    [ERRO]    " + url_pdf + " - " + str(e))
        return "erro"


# =============================================================
# Main
# =============================================================

def main():
    print("=" * 60)
    print("  DOWNLOAD POR CATEGORIA (listagem WordPress)")
    print("  Site: " + urlparse(SITE).netloc)
    print("  URL:  " + URL_CATEGORIA)
    filtro = _anos_filtro_norm()
    print("  Anos: " + (", ".join(filtro) if filtro else "todos"))
    print(
        "  Leitura PDF: "
        + ("sim" if LER_PDF and PdfReader else "nao")
    )
    print("=" * 60)
    print("")

    if LER_PDF and not PdfReader:
        print("  [AVISO] pypdf nao instalado — nomes sem leitura do PDF.")
        print("")

    print("PASSO 1: Coletando posts de todas as paginas...")
    print("-" * 60)

    urls = coletar_posts_categoria(URL_CATEGORIA)
    todos_posts = [(u, extrair_ano_da_url(u)) for u in urls]

    print("")
    print("Total de posts unicos coletados: " + str(len(todos_posts)))
    if filtro:
        antes = len(todos_posts)
        todos_posts = [(u, a) for u, a in todos_posts if ano_permitido(a)]
        print(
            "Filtro de anos ("
            + ", ".join(filtro)
            + "): "
            + str(len(todos_posts))
            + "/"
            + str(antes)
            + " posts."
        )
    if LIMITE_POSTS and LIMITE_POSTS > 0:
        todos_posts = todos_posts[: int(LIMITE_POSTS)]
        print("Limite de posts: " + str(len(todos_posts)))
    print("")

    print("PASSO 2: Baixando PDFs...")
    print("-" * 60)

    ok = pulados = erros = sem_pdf = 0
    total = len(todos_posts)
    cancelado = False
    pasta_hint = "categoria"

    try:
        for i, (url_post, ano) in enumerate(todos_posts, 1):
            _abortar_se_cancelado()
            prefix = "[" + str(i).zfill(3) + "/" + str(total) + "]"
            pasta = os.path.join(PASTA_BASE, "categoria_" + str(ano))
            criar_pasta(pasta)

            slug = url_post.rstrip("/").split("/")[-1][:50]
            print(prefix + " " + str(ano) + " | " + slug)

            try:
                titulo, pdfs = obter_pdfs_do_post(url_post)
            except Exception as e:
                print("    [ERRO]    abrir post: " + str(e))
                erros += 1
                continue

            if not pdfs:
                print("    [SEM PDF] Nenhum PDF encontrado no corpo do post.")
                sem_pdf += 1
                time.sleep(0.3)
                continue

            print(
                "    "
                + str(len(pdfs))
                + " PDF(s) | titulo: "
                + (titulo[:80] if titulo else "(sem titulo)")
            )

            ano_fb = ano if isinstance(ano, int) else None
            for texto_link, url_pdf in pdfs:
                _abortar_se_cancelado()
                nome_previo = montar_nome_documento(
                    texto_link=texto_link,
                    titulo_post=titulo,
                    url_pdf=url_pdf,
                    pasta_hint=pasta_hint,
                    ano_fallback=ano_fb,
                )
                resultado = baixar_e_salvar(
                    url_pdf,
                    pasta,
                    nome_previo,
                    ler_pdf=True,
                    textos_extras=[texto_link, titulo],
                    pasta_hint=pasta_hint,
                    ano_fallback=ano_fb,
                )
                if resultado == "ok":
                    ok += 1
                elif resultado == "pulado":
                    pulados += 1
                else:
                    erros += 1

            time.sleep(0.5)
    except Cancelado:
        cancelado = True

    print("")
    print("=" * 60)
    print("  RESUMO FINAL" + (" (CANCELADO)" if cancelado else ""))
    print("=" * 60)
    print("  Posts processados          : " + str(total))
    print(
        "  PDFs OK / pulados / erros  : "
        + str(ok)
        + " / "
        + str(pulados)
        + " / "
        + str(erros)
    )
    print("  Posts sem PDF              : " + str(sem_pdf))
    print("  Pasta base                 : " + PASTA_BASE)
    print("=" * 60)
    if cancelado:
        raise Cancelado()


if __name__ == "__main__":
    main()
