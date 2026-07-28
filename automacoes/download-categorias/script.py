"""Lista uma categoria WordPress (paginação /page/2/...), abre cada post e baixa PDF(s).
Cada post pode ter vários PDFs na mesma página (ex.: compilado PORTARIAS 2024).
Só considera links dentro do corpo do artigo (.entry-content / article); corta blocos
tipo CONTEÚDO RELACIONADO antes de listar arquivos.
Requisito: pip install requests beautifulsoup4
"""
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

# --- O que você deve mudar ---
# PASTA_BASE: onde salvar (cria subpastas categoria_2023, categoria_2024...)
# URL_CATEGORIA: página da categoria que lista os posts, com / no final
# SITE: mesmo domínio da URL acima, só https://... (sem path depois)
PASTA_BASE = r"C:\Downloads"
URL_CATEGORIA = "https://camaraparagominas.pa.gov.br/portal-da-transparencia/legislacao-de-pessoal-do-municipio/"
SITE = "https://camaraparagominas.pa.gov.br"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
}


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
    match = re.search(r'-(20\d{2}|19\d{2})-', url)
    if match:
        return int(match.group(1))
    match = re.search(r'\b(20\d{2}|19\d{2})\b', url)
    if match:
        return int(match.group(1))
    return "desconhecido"


def _mesmo_dominio(url_a, url_b):
    host_a = urlparse(url_a).netloc.lower().replace("www.", "")
    host_b = urlparse(url_b).netloc.lower().replace("www.", "")
    return host_a == host_b and bool(host_a)


def _li_parece_post_de_norma(texto, href_abs):
    path = urlparse(href_abs).path.lower()

    excluir_slug = (
        "pauta-da-",
        "ata-da-",
        "vereadores-",
    )
    if any(fragment in path for fragment in excluir_slug):
        return False

    if re.search(
        r"\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\s+\d{1,2}\b",
        texto,
        re.I,
    ):
        return True

    if re.search(
        r"\d{1,2}\s+de\s+"
        r"(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|"
        r"outubro|novembro|dezembro)\s+de\s+\d{4}",
        texto,
        re.I,
    ):
        return True

    if re.search(
        r"(lei-municipal|projeto-de-lei|lei-organica|emenda-organica|portarias?)",
        path,
    ):
        return True

    return False


def _podar_conteudo_relacionado(root):
    """
    Remove trecho a partir de titulos tipo 'CONTEUDO RELACIONADO' dentro do mesmo pai,
    para nao baixar PDFs de widgets de posts relacionados.
    """
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
    """Trecho do post onde ficam os links das normas (fora de aside/footer quando possivel)."""
    scope = None
    for sel in ("article .entry-content", ".entry-content", "article", "main"):
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


def _normalizar_href_pdf(href):
    if not href:
        return False
    base = href.split("?")[0].split("#")[0].lower()
    return base.endswith(".pdf")


def _absolutizar(site_base, href):
    href = href.strip()
    if href.startswith("http"):
        return href
    return urljoin(site_base, href)


def obter_pdfs_do_post(url_post):
    """
    Retorna todos os links PDF do corpo do post (lista ordenada, sem repetir).
    Posts tipo 'PORTARIAS 2024' costumam listar varios PDFs na mesma pagina.
    """
    try:
        resp = requests.get(url_post, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        base_resp = resp.url
        scope = _corpo_principal_post(soup)

        candidatos = []
        for tag in scope.find_all("a", href=True):
            href = tag["href"].strip()
            if not href or href.startswith("#"):
                continue
            low = href.lower()
            if _normalizar_href_pdf(href):
                candidatos.append(("pdf", href))
            elif "wp-content/uploads" in low and ".pdf" in low.split("?")[0].lower():
                candidatos.append(("upload", href))

        vistos = set()
        ordenados = []
        for _, href in candidatos:
            abs_url = _absolutizar(base_resp, href)
            if not _mesmo_dominio(abs_url, SITE):
                continue
            if abs_url in vistos:
                continue
            vistos.add(abs_url)
            ordenados.append(abs_url)

        return ordenados
    except Exception:
        return []


def _adicionar_post_se_valido(link_tag, container_tag, links_vistos, posts, texto_opcional=None):
    if not link_tag or not link_tag.get("href"):
        return

    href_bruto = link_tag["href"].strip()
    if not href_bruto or href_bruto.startswith("#"):
        return

    cat_base = URL_CATEGORIA.rstrip("/") + "/"
    href_abs = urljoin(cat_base, href_bruto)

    if href_abs.rstrip("/") == URL_CATEGORIA.rstrip("/"):
        return

    if not _mesmo_dominio(href_abs, SITE):
        return

    ignorar = [
        "/o-municipio",
        "/a-camara",
        "/portal",
        "/processo",
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
        "pinterest",
        "linkedin",
        "google",
        "tumblr",
        "mailto:",
        "/lgpd",
        "/sapl",
        "/tcm",
        "/page/",
        "wp-content/uploads",
    ]
    low = href_abs.lower()
    if any(fragment in low for fragment in ignorar):
        return

    texto = texto_opcional if texto_opcional is not None else container_tag.get_text(" ", strip=True)
    if not _li_parece_post_de_norma(texto, href_abs):
        return

    if href_abs in links_vistos:
        return

    links_vistos.add(href_abs)
    posts.append((href_abs, extrair_ano_da_url(href_abs)))


def coletar_posts_da_pagina(soup):
    posts = []
    links_vistos = set()

    for art in soup.select("article"):
        if art.find_parent("footer"):
            continue
        if art.find_parent("nav"):
            continue

        link_tag = art.select_one("a[href]")
        _adicionar_post_se_valido(link_tag, art, links_vistos, posts)

    for li in soup.select("li"):
        if li.find_parent("nav"):
            continue
        if li.find_parent("footer"):
            continue

        link_tag = li.find("a", href=True)
        if not link_tag:
            continue

        _adicionar_post_se_valido(link_tag, li, links_vistos, posts)

    return posts


def baixar_pdf(nome, url_pdf, pasta):
    caminho = os.path.join(pasta, nome)

    if os.path.exists(caminho):
        print(
            "    [PULADO]  "
            + nome
            + " (ja existe nesta pasta - nao sobrescreve)"
        )
        print("              -> " + caminho)
        return "pulado"

    try:
        resp = requests.get(url_pdf, headers=HEADERS, timeout=30, stream=True)
        resp.raise_for_status()

        with open(caminho, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        tamanho_kb = os.path.getsize(caminho) / 1024
        print("    [OK]      " + nome + " (" + str(round(tamanho_kb, 1)) + " KB)")
        return "ok"

    except Exception as e:
        print("    [ERRO]    " + nome + " - " + str(e))
        if os.path.exists(caminho):
            os.remove(caminho)
        return "erro"


def main():
    print("=" * 60)
    print("  DOWNLOAD POR CATEGORIA (listagem WordPress)")
    print("  Site: " + urlparse(SITE).netloc)
    print("=" * 60)
    print("")

    print("PASSO 1: Coletando posts de todas as paginas...")
    print("-" * 60)

    todos_posts = []
    links_globais = set()
    pagina = 1

    while True:
        _abortar_se_cancelado()
        if pagina == 1:
            url = URL_CATEGORIA
        else:
            url = URL_CATEGORIA + "page/" + str(pagina) + "/"

        print("  Pagina " + str(pagina) + ": " + url)

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 404 or SITE + "/c/" not in resp.url and pagina > 1:
                print("  Fim das paginas.")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            posts_pagina = coletar_posts_da_pagina(soup)

            novos = [(h, a) for h, a in posts_pagina if h not in links_globais]
            for h, a in novos:
                links_globais.add(h)
            todos_posts.extend(novos)

            print("  " + str(len(novos)) + " posts novos encontrados. Total ate agora: " + str(len(todos_posts)))

            if len(novos) == 0:
                print("  Nenhum post novo. Fim das paginas.")
                break

            pagina += 1
            time.sleep(0.8)

        except Exception as e:
            print("  [ERRO] " + str(e))
            break

    print("")
    print("Total de posts unicos coletados: " + str(len(todos_posts)))
    print("")

    print("PASSO 2: Baixando PDFs...")
    print("-" * 60)

    ok = pulados = erros = sem_pdf = 0
    total = len(todos_posts)
    cancelado = False

    try:
        for i, (url_post, ano) in enumerate(todos_posts, 1):
            _abortar_se_cancelado()
            prefix = "[" + str(i).zfill(3) + "/" + str(total) + "]"
            pasta = os.path.join(PASTA_BASE, "categoria_" + str(ano))
            criar_pasta(pasta)

            slug = url_post.rstrip("/").split("/")[-1][:50]
            print(prefix + " " + str(ano) + " | " + slug)

            urls_pdf = obter_pdfs_do_post(url_post)

            if not urls_pdf:
                print("    [SEM PDF] Nenhum PDF encontrado no corpo do post.")
                sem_pdf += 1
                time.sleep(0.3)
                continue

            print("    " + str(len(urls_pdf)) + " PDF(s) no conteudo principal.")

            usados_local = set()
            for j, url_pdf in enumerate(urls_pdf, 1):
                _abortar_se_cancelado()
                nome = os.path.basename(urlparse(url_pdf).path.split("?")[0])
                if not nome or not nome.lower().endswith(".pdf"):
                    nome = slug.replace("/", "_") + "_" + str(j).zfill(2) + ".pdf"
                stem = nome[:-4] if nome.lower().endswith(".pdf") else nome
                sufixo = 1
                nome_final = nome
                while nome_final.lower() in usados_local:
                    sufixo += 1
                    nome_final = stem + "_" + str(sufixo) + ".pdf"
                usados_local.add(nome_final.lower())

                resultado = baixar_pdf(nome_final, url_pdf, pasta)
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
