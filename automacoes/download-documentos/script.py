import os
import re
import sys
import time
import requests

from bs4 import BeautifulSoup
from urllib.parse import parse_qs, unquote, urljoin, urlparse


class Cancelado(Exception):
    """Fila interrompida pelo usuario (centro-automacoes)."""


def pedido_cancelado():
    return False


def _abortar_se_cancelado():
    if pedido_cancelado():
        print("[AVISO] Fila cancelada pelo usuario.")
        raise Cancelado()


# =============================================================
# CONFIGURAÇÕES PRINCIPAIS
# =============================================================

# Pasta principal onde tudo será salvo
PASTA_BASE = r"C:\Downloads"

# Tipo do documento (texto livre ou PPA / LDO / LOA). Vazio = usa o título da página (h1).
TIPO_DOCUMENTO = ""

# Filtro de anos: lista de strings, ex. ["2023"] ou ["2022", "2023"].
# Lista vazia = baixa TODOS os anos encontrados na página.
ANOS_FILTRO = []

# Uma ou várias páginas. Pode ser só a URL (str) ou dict com overrides:
#   {"url": "https://...", "tipo": "Parecer TC"}
URLS_PAGINAS = [
    "https://camaraparagominas.pa.gov.br/folha-de-pagamento/",
    "https://camaraparagominas.pa.gov.br/folha-de-pagamento-2022/",
    "https://camaraparagominas.pa.gov.br/folha-de-pagamento-2021/",
    "https://camaraparagominas.pa.gov.br/folha-de-pagamento-2020/",
    "https://camaraparagominas.pa.gov.br/folha-de-pagamento-2019/",
    "https://camaraparagominas.pa.gov.br/folha-de-pagamento-2018/",
    "https://camaraparagominas.pa.gov.br/folha-de-pagamento-2017/",
    "https://camaraparagominas.pa.gov.br/folha-de-pagamento-2016/",
     # {"url": "https://outro-site.gov.br/ldo/", "tipo": "LDO"},
]

# Subpastas reconhecidas em paginas de Balancete (Despesa / Receita).
SUBPASTAS_BALANCETE = (
    "Balancete de Despesa",
    "Balancete de Receita",
)

# Compatibilidade: primeiro link da lista.
def _primeira_url_lista():
    if not URLS_PAGINAS:
        return ""
    primeiro = URLS_PAGINAS[0]
    if isinstance(primeiro, dict):
        return (primeiro.get("url") or "").strip()
    return str(primeiro).strip()


URL_PAGINA = _primeira_url_lista()
# Cabeçalhos para simular navegador real
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),

    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),

    "Accept-Language": "pt-BR,pt;q=0.9",

    "Referer": "",
}


# =============================================================
# CRIAR PASTA
# =============================================================

def criar_pasta(caminho_pasta):
    """
    Cria uma pasta caso ela não exista.
    """

    os.makedirs(caminho_pasta, exist_ok=True)


# =============================================================
# LIMPAR NOME DA PASTA
# =============================================================

def limpar_nome_pasta(nome):
    """
    Remove caracteres inválidos para nomes de pasta.
    """

    caracteres_invalidos = r'<>:"/\|?*'

    for caractere in caracteres_invalidos:

        nome = nome.replace(caractere, "")

    return nome.strip()


# =============================================================
# LIMPAR NOME DO ARQUIVO
# =============================================================

def limpar_nome_arquivo(nome):
    """
    Remove caracteres inválidos para arquivos no Windows.
    """

    caracteres_invalidos = r'<>:"/\|?*'

    for caractere in caracteres_invalidos:

        nome = nome.replace(caractere, "-")

    # Remove espaços duplos
    nome = re.sub(r"\s+", " ", nome)

    return nome.strip()


# =============================================================
# GOOGLE DRIVE — ID E DOWNLOAD (PDF hospedado no Drive)
# =============================================================

_DRIVE_UC = "https://drive.google.com/uc"


def eh_url_google_drive_arquivo(url):
    """
    Indica URL de arquivo no Drive (não pasta).
    Pastas (/folders/) exigiriam API/outro fluxo.
    """

    if not url:

        return False

    u = url.lower()

    if "drive.google.com" not in u:

        return False

    if "/folders/" in u:

        return False

    if "/file/d/" in u or "/open?" in u or "/uc?" in u:

        return True

    return False


def extrair_id_arquivo_google_drive(url):
    """
    Extrai o ID do arquivo a partir do link do Drive.
    """

    if not url:

        return None

    m = re.search(
        r"/file/d/([A-Za-z0-9_-]+)",
        url,
        re.IGNORECASE
    )

    if m:

        return m.group(1)

    query = urlparse(url).query

    params = parse_qs(query)

    ids = params.get("id")

    if ids:

        return ids[0]

    return None


def baixar_arquivo_google_drive(file_id, caminho_destino, timeout=120):
    """
    Baixa arquivo público pelo ID (uc?export=download).
    Trata aviso de verificação de vírus (cookie confirm ou link na página).
    """

    params = {
        "export": "download",
        "id": file_id,
    }

    sessao = requests.Session()

    sessao.headers.update(HEADERS)

    r1 = sessao.get(
        _DRIVE_UC,
        params=params,
        timeout=timeout,
    )

    r1.raise_for_status()

    token = None

    for chave, valor in r1.cookies.items():

        if chave.startswith("download_warning"):

            token = valor

            break

    if token is None and r1.content[:5].startswith(b"%PDF"):

        with open(caminho_destino, "wb") as arquivo:

            arquivo.write(r1.content)

    elif token is not None:

        r2 = sessao.get(
            _DRIVE_UC,
            params={
                **params,
                "confirm": token,
            },
            timeout=timeout,
            stream=True,
        )

        r2.raise_for_status()

        with open(caminho_destino, "wb") as arquivo:

            for parte in r2.iter_content(chunk_size=8192):

                if parte:

                    arquivo.write(parte)

    else:

        m = re.search(
            r"confirm=([\w-]+)",
            r1.text
        )

        if not m:

            raise ValueError(
                "Download do Drive bloqueado ou link sem permissão pública "
                "(não foi possível obter confirm token)."
            )

        r2 = sessao.get(
            _DRIVE_UC,
            params={
                **params,
                "confirm": m.group(1),
            },
            timeout=timeout,
            stream=True,
        )

        r2.raise_for_status()

        with open(caminho_destino, "wb") as arquivo:

            for parte in r2.iter_content(chunk_size=8192):

                if parte:

                    arquivo.write(parte)

    with open(caminho_destino, "rb") as arquivo:

        cabeca = arquivo.read(8)

    if len(cabeca) < 5:

        raise ValueError("Arquivo do Drive ficou vazio.")

    if not cabeca.startswith(b"%PDF"):

        raise ValueError(
            "Resposta do Drive não parece um PDF "
            "(link pode exigir login, não ser público ou não ser PDF)."
        )


# =============================================================
# PEGAR TÍTULO DA PÁGINA
# =============================================================

def obter_titulo_pagina(soup):
    """
    Pega o título principal da página.
    """

    h1 = soup.find("h1")

    if h1:

        titulo = h1.get_text(strip=True)

        titulo = limpar_nome_pasta(titulo)

        return titulo

    return "downloads"


def _detectar_subpasta_balancete(texto):
    """
    Titulos tipo 'Balancete de Despesa' / 'Balancete de Receita' na pagina CR2.
    """
    if not texto:
        return None
    t = re.sub(r"\s+", " ", texto.strip().lower())
    if re.search(r"balancete\s+de\s+despesa", t):
        return "Balancete de Despesa"
    if re.search(r"balancete\s+de\s+receita", t):
        return "Balancete de Receita"
    return None


def _chave_grupo_pasta(subpasta, ano):
    """Chave interna: (subpasta ou '', ano)."""
    return (subpasta or "", str(ano))


def _href_parece_arquivo_pdf(href):
    """PDF direto, upload WordPress ou Google Drive."""
    if not href:
        return False
    href_lower = href.lower()
    return (
        ".pdf" in href_lower
        or "/uploads/" in href_lower
        or eh_url_google_drive_arquivo(href)
    )


_ROTULOS_GENERICOS = frozenset({
    "pdf", "xlsx", "xls", "txt", "doc", "docx", "odt", "csv",
    "download", "baixar", "clique aqui", "clique", "aqui", "arquivo",
    "ver", "visualizar", "abrir",
})


def _texto_link_generico(texto):
    """Rotulos curtos do site (PDF, XLSX, TXT...) nao servem como nome de arquivo."""
    t = re.sub(r"\s+", " ", (texto or "").strip().lower())
    if not t:
        return True
    return t in _ROTULOS_GENERICOS


def _nome_base_da_url(href):
    nome = os.path.basename(unquote(urlparse(href).path.split("?")[0]))
    return limpar_nome_arquivo(nome) if nome else ""


def _garantir_nomes_unicos(lista):
    """Evita colisao de nomes na mesma pasta (mesmo URL ou rotulos iguais)."""
    usados = set()
    saida = []
    for nome, url in lista:
        base, ext = os.path.splitext(nome)
        if not ext:
            ext = ".pdf"
            base = nome
        candidato = base + ext
        if candidato not in usados:
            usados.add(candidato)
            saida.append((candidato, url))
            continue
        n = 2
        while True:
            candidato = "{0}-{1}{2}".format(base, n, ext)
            if candidato not in usados:
                usados.add(candidato)
                saida.append((candidato, url))
                break
            n += 1
    return saida


def _nome_arquivo_para_link(texto, href, ano, titulo_pagina):
    """Monta nome do arquivo a partir do link ou da URL."""
    texto = (texto or "").strip()
    nome_url = _nome_base_da_url(href)

    if eh_url_google_drive_arquivo(href):
        id_tmp = extrair_id_arquivo_google_drive(href)
        if id_tmp:
            return limpar_nome_arquivo(id_tmp + ".pdf")

    if _texto_link_generico(texto) or len(texto) < 3:
        if nome_url:
            return nome_url
        if eh_url_google_drive_arquivo(href):
            id_tmp = extrair_id_arquivo_google_drive(href)
            texto = id_tmp if id_tmp else "drive-google"
        else:
            texto = titulo_pagina or "documento"

    if re.match(r"^\d{4}$", texto):
        if nome_url:
            return nome_url
        return limpar_nome_arquivo("{}-{}.pdf".format(titulo_pagina, ano))

    if nome_url and "." in nome_url:
        _, ext = os.path.splitext(nome_url)
        return limpar_nome_arquivo("{0}-{1}{2}".format(texto, ano, ext or ".pdf"))

    return limpar_nome_arquivo("{}-{}.pdf".format(texto, ano))


def _registrar_pdf(resultado, links_ja_adicionados, texto, href, ano, subpasta, titulo_pagina):
    """Adiciona um PDF ao resultado se ainda não estiver na lista."""
    if href in links_ja_adicionados:
        return
    links_ja_adicionados.add(href)
    chave = _chave_grupo_pasta(subpasta, ano)
    if chave not in resultado:
        resultado[chave] = []
    nome_arquivo = _nome_arquivo_para_link(texto, href, ano, titulo_pagina)
    resultado[chave].append((nome_arquivo, href))


# =============================================================
# ENCONTRAR PDFs E ORGANIZAR POR ANO / SUBPASTA
# =============================================================

def obter_pdfs_por_ano(url):
    """
    Le a pagina e organiza PDFs por ano.
    Se houver secoes 'Balancete de Despesa' e 'Balancete de Receita',
    separa em subpastas distintas.
    Retorna titulo_pagina e dict {(subpasta, ano): [(nome, url), ...]}.
    """

    resposta = requests.get(
        url,
        headers=HEADERS,
        timeout=15
    )

    resposta.raise_for_status()

    soup = BeautifulSoup(
        resposta.text,
        "html.parser"
    )

    # =========================================================
    # TÍTULO DA PÁGINA
    # =========================================================

    titulo_pagina = obter_titulo_pagina(soup)

    m_ano_titulo = re.search(r"(20\d{2}|19\d{2})", titulo_pagina)
    ano_titulo = m_ano_titulo.group(1) if m_ano_titulo else None

    resultado = {}
    ano_atual = ano_titulo or "SEM_ANO"
    subpasta_atual = ""
    links_ja_adicionados = set()

    for tag in soup.find_all():
        texto = tag.get_text(strip=True)

        sub = _detectar_subpasta_balancete(texto)
        if sub and len(texto) < 80:
            subpasta_atual = sub
            continue

        # CR2: anos listados como links diretos para PDF (texto "2024" -> /uploads/...pdf)
        if tag.name == "a":
            href = tag.get("href", "")
            if href:
                if not href.startswith("http"):
                    href = urljoin(url, href)
                if _href_parece_arquivo_pdf(href):
                    ano_pdf = texto if re.match(r"^\d{4}$", texto) else ano_atual
                    _registrar_pdf(
                        resultado,
                        links_ja_adicionados,
                        texto,
                        href,
                        ano_pdf,
                        subpasta_atual,
                        titulo_pagina,
                    )
                    continue

        if re.match(r"^\d{4}$", texto):
            ano_atual = texto
            continue

        if tag.name != "a":
            continue

        href = tag.get("href", "")
        if not href:
            continue

        if not href.startswith("http"):
            href = urljoin(url, href)

        if not _href_parece_arquivo_pdf(href):
            continue

        _registrar_pdf(
            resultado,
            links_ja_adicionados,
            texto,
            href,
            ano_atual,
            subpasta_atual,
            titulo_pagina,
        )

    for chave in list(resultado.keys()):
        resultado[chave] = _garantir_nomes_unicos(resultado[chave])

    return titulo_pagina, resultado


# =============================================================
# BAIXAR PDF
# =============================================================

def baixar_pdf(nome_arquivo, url_pdf, pasta_destino):
    """
    Faz download do PDF.
    """

    caminho_arquivo = os.path.join(
        pasta_destino,
        nome_arquivo
    )

    # =========================================================
    # EVITAR DOWNLOAD REPETIDO
    # =========================================================

    if os.path.exists(caminho_arquivo):

        print(
            f"    [PULADO] {nome_arquivo} "
            f"(já existe)"
        )

        return {
            "status": "pulado",
            "nome": nome_arquivo,
            "motivo": "já existe no disco",
            "pasta": pasta_destino,
        }

    # =========================================================
    # DOWNLOAD
    # =========================================================

    try:

        id_drive = None

        if "drive.google.com" in (
            url_pdf.lower()
        ):

            id_drive = extrair_id_arquivo_google_drive(
                url_pdf
            )

        if (
            id_drive
            and eh_url_google_drive_arquivo(url_pdf)
        ):

            baixar_arquivo_google_drive(
                id_drive,
                caminho_arquivo,
            )

        else:

            resposta = requests.get(
                url_pdf,
                headers=HEADERS,
                timeout=30,
                stream=True
            )

            resposta.raise_for_status()

            with open(caminho_arquivo, "wb") as arquivo:

                for chunk in resposta.iter_content(
                    chunk_size=8192
                ):

                    arquivo.write(chunk)

        tamanho_kb = (
            os.path.getsize(caminho_arquivo) / 1024
        )

        print(
            f"    [OK] {nome_arquivo} "
            f"({round(tamanho_kb, 1)} KB)"
        )

        return {
            "status": "ok",
            "nome": nome_arquivo,
            "pasta": pasta_destino,
        }

    except Exception as erro:

        print(
            f"    [ERRO] {nome_arquivo} "
            f"- {erro}"
        )

        # Remove arquivo quebrado
        if os.path.exists(caminho_arquivo):

            os.remove(caminho_arquivo)

        return {
            "status": "erro",
            "nome": nome_arquivo,
            "motivo": str(erro),
            "pasta": pasta_destino,
        }


# =============================================================
# LISTA DE URLs (CONFIG + LINHA DE COMANDO)
# =============================================================

def _normalizar_item_url_pagina(item, tipo_cli=None):
    """
    Aceita str (só URL) ou dict {url, tipo?}.
    Retorna dict padronizado ou None se URL inválida.
    """
    if isinstance(item, dict):
        url = (item.get("url") or "").strip()
        tipo = (item.get("tipo") or TIPO_DOCUMENTO or "").strip()
    else:
        url = str(item).strip() if item else ""
        tipo = (TIPO_DOCUMENTO or "").strip()

    if tipo_cli:
        tipo = tipo_cli.strip()

    if not url or not url.startswith("http"):
        return None

    return {
        "url": url,
        "tipo": tipo,
    }


def _normalizar_lista_entradas_paginas(entradas, tipo_cli=None):
    """Remove vazios e URLs duplicadas (mantém ordem)."""
    vistos = set()
    saida = []
    for item in entradas:
        norm = _normalizar_item_url_pagina(item, tipo_cli)
        if norm is None:
            continue
        chave = norm["url"].rstrip("/").lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(norm)
    return saida


def _montar_nome_pasta_tipo(tipo, titulo_pagina):
    """
    Pasta principal pelo tipo ou título da página (h1).
    Ex.: Balancete Financeiro, Relatório de Gestão Fiscal.
    """
    tipo_limpo = limpar_nome_pasta((tipo or "").strip())
    if not tipo_limpo:
        tipo_limpo = limpar_nome_pasta(titulo_pagina) or "documentos"
    return tipo_limpo


def _urls_da_linha_comando():
    """
    URLs extras: python script.py https://site1/ https://site2/
    Ou: python script.py --url https://site1/ --url https://site2/
    """
    extras = []
    i = 0
    args = sys.argv[1:]
    while i < len(args):
        a = args[i]
        if a in ("--url", "-u") and i + 1 < len(args):
            extras.append(args[i + 1])
            i += 2
            continue
        if a.startswith("http://") or a.startswith("https://"):
            extras.append(a)
        i += 1
    return extras


def _tipo_da_linha_comando():
    tipo = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--tipo", "-t") and i + 1 < len(args):
            tipo = args[i + 1]
            i += 2
            continue
        i += 1
    return tipo


def coletar_urls_para_processar():
    """CONFIG URLS_PAGINAS + links passados na linha de comando."""
    tipo_cli = _tipo_da_linha_comando()
    extras_url = _urls_da_linha_comando()
    todas = list(URLS_PAGINAS) + extras_url
    return _normalizar_lista_entradas_paginas(todas, tipo_cli)


# =============================================================
# PROCESSAR UMA PÁGINA
# =============================================================

def processar_pagina(entrada):
    """
    Lê uma URL, baixa PDFs por ano e retorna contadores + pasta principal.
    entrada: dict {url, tipo} ou str (URL).
    Retorna None se a página falhar.
    """
    norm = _normalizar_item_url_pagina(entrada)
    if norm is None:
        return None

    url_pagina = norm["url"]
    tipo_cfg = norm["tipo"]

    print("\n" + "=" * 60)
    print("PÁGINA: {}".format(url_pagina[:72]))
    if len(url_pagina) > 72:
        print("        {}".format(url_pagina[72:140]))
    if tipo_cfg:
        print("Tipo (config)    : {}".format(tipo_cfg))
    print("=" * 60)

    try:
        titulo_pagina, pdfs_por_ano = obter_pdfs_por_ano(url_pagina)
    except Exception as erro:
        print("[ERRO] Não foi possível acessar a página:")
        print(str(erro))
        return None

    total_pdfs = sum(len(lista) for lista in pdfs_por_ano.values())

    if total_pdfs == 0:
        print("\nNenhum PDF encontrado nesta página.")
        pasta_vazia = os.path.join(
            PASTA_BASE,
            _montar_nome_pasta_tipo(tipo_cfg, titulo_pagina),
        )
        return {
            "ok": 0,
            "pulados": 0,
            "erros": 0,
            "lista_pulados": [],
            "lista_erros": [],
            "pasta": pasta_vazia,
            "titulo": titulo_pagina,
            "url": url_pagina,
            "tipo_pasta": _montar_nome_pasta_tipo(tipo_cfg, titulo_pagina),
        }

    nome_pasta_raiz = _montar_nome_pasta_tipo(tipo_cfg, titulo_pagina)
    pasta_principal = os.path.join(PASTA_BASE, nome_pasta_raiz)
    criar_pasta(pasta_principal)

    chaves = sorted(
        pdfs_por_ano.keys(),
        key=lambda k: (k[0] or "zzz", k[1]),
        reverse=True,
    )

    anos_filtro = [str(a).strip() for a in (ANOS_FILTRO or []) if str(a).strip()]
    if anos_filtro:
        antes = len(chaves)
        chaves = [k for k in chaves if k[1] in anos_filtro or k[1] == "SEM_ANO"]
        pulados_ano = antes - len(chaves)
        print("Filtro de anos  : {}".format(", ".join(anos_filtro)))
        if pulados_ano:
            print("Grupos fora do filtro (pulados): {}".format(pulados_ano))

    subpastas_usadas = sorted({k[0] for k in chaves if k[0]})
    anos_usados = sorted({k[1] for k in chaves}, reverse=True)

    print("\n============================================================")
    print("PASTA: {}".format(nome_pasta_raiz))
    print("TÍTULO DA PÁGINA: {}".format(titulo_pagina))
    print("============================================================")
    if subpastas_usadas:
        print("Subpastas: " + ", ".join(subpastas_usadas))
    print("Anos a baixar: " + (", ".join(anos_usados) if anos_usados else "(nenhum)"))
    print("Total de PDFs neste filtro: {}".format(
        sum(len(pdfs_por_ano[k]) for k in chaves)
    ))
    print()

    if not chaves:
        print("[AVISO] Nenhum PDF nos anos filtrados nesta página.")
        return {
            "ok": 0,
            "pulados": 0,
            "erros": 0,
            "lista_pulados": [],
            "lista_erros": [],
            "pasta": pasta_principal,
            "titulo": titulo_pagina,
            "url": url_pagina,
            "tipo_pasta": nome_pasta_raiz,
        }

    total_ok = 0
    total_pulados = 0
    total_erros = 0
    lista_pulados = []
    lista_erros = []

    for subpasta, ano in chaves:
        _abortar_se_cancelado()
        pdfs = pdfs_por_ano[(subpasta, ano)]
        if subpasta:
            pasta_ano = os.path.join(pasta_principal, subpasta, ano)
            rotulo = "{} / {}".format(subpasta, ano)
        else:
            pasta_ano = os.path.join(pasta_principal, ano)
            rotulo = ano

        criar_pasta(pasta_ano)

        print("=" * 60)
        print("{} - {} arquivo(s)".format(rotulo, len(pdfs)))
        print("=" * 60)

        ok = 0
        pulados = 0
        erros = 0

        for nome_arquivo, url_pdf in pdfs:
            _abortar_se_cancelado()
            item = baixar_pdf(nome_arquivo, url_pdf, pasta_ano)
            status = item.get("status")
            if status == "ok":
                ok += 1
            elif status == "pulado":
                pulados += 1
                lista_pulados.append(item)
            else:
                erros += 1
                lista_erros.append(item)
            time.sleep(0.5)

        tamanho_mb = sum(
            os.path.getsize(os.path.join(pasta_ano, arquivo))
            for arquivo in os.listdir(pasta_ano)
            if os.path.isfile(os.path.join(pasta_ano, arquivo))
        ) / (1024 * 1024)

        print()
        print(
            "Baixados : {}  |  Pulados : {}  |  Erros : {}".format(
                ok, pulados, erros
            )
        )
        print("Tamanho  : {} MB".format(round(tamanho_mb, 2)))
        print("Pasta    : {}".format(pasta_ano))
        print()

        total_ok += ok
        total_pulados += pulados
        total_erros += erros
        time.sleep(1)

    return {
        "ok": total_ok,
        "pulados": total_pulados,
        "erros": total_erros,
        "lista_pulados": lista_pulados,
        "lista_erros": lista_erros,
        "pasta": pasta_principal,
        "titulo": titulo_pagina,
        "url": url_pagina,
        "tipo_pasta": nome_pasta_raiz,
    }


def _formatar_item_relatorio(item):
    pasta = item.get("pasta") or ""
    nome = item.get("nome") or "?"
    caminho = os.path.join(pasta, nome) if pasta else nome
    motivo = item.get("motivo")
    if motivo:
        return "  - {}  ({})".format(caminho, motivo)
    return "  - {}".format(caminho)


def _montar_texto_mini_relatorio(resultados_paginas, paginas_falha):
    """Texto do mini relatório: pulados, erros e páginas que falharam."""
    linhas = []
    linhas.append("=" * 60)
    linhas.append("MINI RELATÓRIO — pulados e erros")
    linhas.append("=" * 60)

    total_pul = sum(len(r.get("lista_pulados") or []) for r in resultados_paginas)
    total_err = sum(len(r.get("lista_erros") or []) for r in resultados_paginas)
    linhas.append(
        "Resumo: {} pulado(s)  |  {} erro(s) em PDF  |  {} página(s) com falha".format(
            total_pul,
            total_err,
            len(paginas_falha),
        )
    )
    linhas.append("")

    if paginas_falha:
        linhas.append("--- Páginas não processadas ---")
        for falha in paginas_falha:
            linhas.append("  - {}".format(falha.get("url", "?")))
            if falha.get("motivo"):
                linhas.append("    motivo: {}".format(falha["motivo"]))
        linhas.append("")

    for res in resultados_paginas:
        pul = res.get("lista_pulados") or []
        err = res.get("lista_erros") or []
        if not pul and not err:
            continue

        titulo = res.get("tipo_pasta") or res.get("titulo") or "Página"
        linhas.append("--- {} ---".format(titulo))
        linhas.append("  URL: {}".format(res.get("url", "")))
        if pul:
            linhas.append("  Pulados ({}):".format(len(pul)))
            for item in pul:
                linhas.append(_formatar_item_relatorio(item))
        if err:
            linhas.append("  Erros ({}):".format(len(err)))
            for item in err:
                linhas.append(_formatar_item_relatorio(item))
        linhas.append("")

    if total_pul == 0 and total_err == 0 and not paginas_falha:
        linhas.append("Nenhum pulado, erro ou falha de página.")

    linhas.append("=" * 60)
    return "\n".join(linhas)


def _salvar_mini_relatorio(texto):
    """Grava relatório em PASTA_BASE se houver conteúdo relevante."""
    if "Nenhum pulado" in texto:
        return None
    criar_pasta(PASTA_BASE)
    marca = time.strftime("%Y%m%d_%H%M%S")
    caminho = os.path.join(PASTA_BASE, "relatorio_download_{}.txt".format(marca))
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write(texto)
        fh.write("\n")
    return caminho


def _exibir_mini_relatorio(resultados_paginas, paginas_falha):
    total_pul = sum(len(r.get("lista_pulados") or []) for r in resultados_paginas)
    total_err = sum(len(r.get("lista_erros") or []) for r in resultados_paginas)
    if total_pul == 0 and total_err == 0 and not paginas_falha:
        return

    texto = _montar_texto_mini_relatorio(resultados_paginas, paginas_falha)
    print()
    print(texto)
    caminho = _salvar_mini_relatorio(texto)
    if caminho:
        print("Relatório salvo em:\n  {}".format(caminho))
        print()


# =============================================================
# FUNÇÃO PRINCIPAL
# =============================================================

def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(
            "Uso: python \"Automações- documentos.py\" [opcoes] [URLs...]\n\n"
            "  CONFIG: TIPO_DOCUMENTO (opcional), URLS_PAGINAS (str ou dict com url/tipo).\n"
            "  Pastas: PASTA_BASE\\<TIPO>\\<ANO>\\arquivo.pdf\n\n"
            "  --tipo, -t TEXTO      Sobrescreve TIPO (ex. LDO, PPA, LOA ou titulo fixo)\n"
            "  --url, -u URL         URL extra\n"
            "  python script.py https://site1/ https://site2/\n"
        )
        return

    entradas = coletar_urls_para_processar()

    if not entradas:
        print("[ERRO] Nenhuma URL configurada.")
        print("       Preencha URLS_PAGINAS no script ou passe links http(s) na linha de comando.")
        return

    print("=" * 60)
    print("DOWNLOAD AUTOMÁTICO DE PDFs")
    print("=" * 60)
    if TIPO_DOCUMENTO:
        print("Tipo padrão    : {}".format(TIPO_DOCUMENTO))
    print("\n{} página(s) na fila:\n".format(len(entradas)))
    for idx, item in enumerate(entradas, 1):
        linha = "  [{}/{}] {} | {}".format(
            idx,
            len(entradas),
            item["url"][:56],
            item["tipo"] or "(titulo da pagina)",
        )
        print(linha)

    geral_ok = 0
    geral_pulados = 0
    geral_erros = 0
    paginas_falha = []
    resultados_paginas = []
    pastas_salvas = []
    cancelado = False

    try:
        for entrada in entradas:
            _abortar_se_cancelado()
            res = processar_pagina(entrada)
            if res is None:
                url_f = entrada.get("url") if isinstance(entrada, dict) else str(entrada)
                paginas_falha.append({
                    "url": url_f,
                    "motivo": "nao foi possivel acessar ou ler a pagina",
                })
                continue
            resultados_paginas.append(res)
            geral_ok += res["ok"]
            geral_pulados += res["pulados"]
            geral_erros += res["erros"]
            if res.get("pasta"):
                pastas_salvas.append(res["pasta"])
    except Cancelado:
        cancelado = True

    print("\n" + "=" * 60)
    print("RESUMO GERAL" + (" (CANCELADO)" if cancelado else ""))
    print("=" * 60)
    print("Paginas na fila      : {}".format(len(entradas)))
    print("Paginas com falha    : {}".format(len(paginas_falha)))
    print("Total baixados       : {}".format(geral_ok))
    print("Total pulados        : {}".format(geral_pulados))
    print("Total erros (PDFs)   : {}".format(geral_erros))
    print()
    if pastas_salvas:
        print("Pastas com arquivos:")
        for p in pastas_salvas:
            print("  - {}".format(p))
    print("=" * 60)

    _exibir_mini_relatorio(resultados_paginas, paginas_falha)
    if cancelado:
        raise Cancelado()


# =============================================================
# INICIAR PROGRAMA
# =============================================================

if __name__ == "__main__":
    main()