# =====================================================================
#  Publicação de RGF, RREO, Balanço e Balancete — portal CR2 (Playwright)
# =====================================================================
#
#  Documentacao (dependencias, pastas/URLs, linha de comando, mapa de funcoes):
#    GUIA_WINDOWS.md  (pasta automacoes/)
#
#  Cada tipo so entra na fila se URL_PORTAL_* estiver preenchida (nao vazia).
#  Modal Bubble: titulos e labels podem variar — ajuste CONFIG se o portal mudar.

import json
import os
import re
import subprocess
import unicodedata
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright
except ImportError:
    PWTimeout = None
    sync_playwright = None


class Cancelado(Exception):
    """Fila interrompida pelo usuario (centro-automacoes)."""


def pedido_cancelado():
    return False


def _abortar_se_cancelado():
    if pedido_cancelado():
        print("[AVISO] Fila cancelada pelo usuario.")
        raise Cancelado()


def _recarregar_playwright():
    """Tenta importar playwright de novo (apos pip install)."""
    global PWTimeout, sync_playwright
    try:
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        PWTimeout = None
        sync_playwright = None
        return False


def _mesmo_python(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except Exception:
        return False


def _python_venv_do_projeto():
    return Path(__file__).resolve().parent / "venv" / "Scripts" / "python.exe"


def _pip_instalar(python_exe, pacote):
    print("[INFO] Instalando '{}' com: {}".format(pacote, python_exe))
    r = subprocess.run(
        [str(python_exe), "-m", "pip", "install", pacote],
        check=False,
    )
    return r.returncode == 0


def garantir_playwright_pronto():
    """
    Garante playwright no Python em uso.
    Se o IDE usar Python 3.13 sem o pacote: instala ou recria o script com venv\\Scripts\\python.exe.
    """
    if sync_playwright is not None:
        return

    if _pip_instalar(sys.executable, "playwright") and _recarregar_playwright():
        print("[INFO] Playwright OK neste interpretador.")
        return

    venv_py = _python_venv_do_projeto()
    if not venv_py.is_file():
        print("[INFO] Criando venv em: {}".format(venv_py.parent.parent))
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_py.parent.parent)],
            check=True,
        )

    if venv_py.is_file():
        _pip_instalar(venv_py, "playwright")
        if not _mesmo_python(sys.executable, venv_py):
            print("[INFO] Reiniciando o script com o Python do venv do projeto...")
            os.execv(str(venv_py), [str(venv_py)] + sys.argv)
        if _recarregar_playwright():
            print("[INFO] Playwright OK no venv do projeto.")
            return

# ---------------------------------------------------------------------
#  CONFIG — edite aqui (pastas, URLs, login)
#  URL vazia = fila desligada. Documentacao: README_publicador_CR2.md
# ---------------------------------------------------------------------

PASTA_RGF = Path(r"C:\Downloads\Relatório de Gestão Fiscal (RGF)")
PASTA_RREO = Path(r"C:\Downloads\Relatório RREO")
PASTA_BALANCETE = Path(r"C:\Downloads\Balancete Financeiro")
PASTA_BALANCO_REL_ANUAIS = Path(r"C:\Downloads\Balanço e Relatórios Anuais")

URL_PORTAL_RGF = ""
URL_PORTAL_RREO = "https://www.portalcr2.com.br/relatorio-resumido-rreo/rreo-maracana"
URL_PORTAL_BALANCETE = ""
URL_PORTAL_BALANCO_REL_ANUAIS = ""

URL_LOGIN = "https://www.portalcr2.com.br/?view=login"

ABRIR_LOGIN_ANTES_DO_PORTAL = True
HEADLESS = False

# Credenciais só pelo painel ou variáveis de ambiente (nunca no código).
PORTAL_USUARIO = os.environ.get("PORTAL_USUARIO", "").strip()
PORTAL_SENHA = os.environ.get("PORTAL_SENHA", "").strip()

# ---------------------------------------------------------------------
#  CONFIG avancado (filtros, tempos, Bubble — raramente precisa mudar)
# ---------------------------------------------------------------------

PASTA_BASE = PASTA_RGF
ANO_FILTRO = None

ABRIR_LOGIN_ANTES_DO_RGF = ABRIR_LOGIN_ANTES_DO_PORTAL
PORTAL_LOGIN_BOTAO = "Entrar"
MODO_TESTE = False
PUBLICAR_DUPLO_BUBBLE = False

PAUSA_APOS_ANEXAR_PDF = 0.48
PAUSA_POLL_UPLOAD_UI = 0.24
MAX_TENTATIVAS_POLL_UPLOAD = 18
PAUSA_APOS_CONFIRMAR_UPLOAD = 0.7
PAUSA_APOS_CLICAR_PUBLICAR = 1.5

TIMEOUT_PUBLICAR_HABILITADO_S = 75
TIMEOUT_RESULTADO_PUBLICACAO_S = 55

_TEXTO_ERRO_APOS_PUBLICAR_RX = re.compile(
    r"(erro|falha|inv[aá]lid|obrigat[oó]rio|n[aã]o\s+foi\s+poss[ií]vel|"
    r"tente\s+novamente|j[aá]\s+existe|duplicad|\bduplicat)",
    re.I,
)
_TEXTO_SUCESSO_MODAL_RX = re.compile(
    r"(publicad|salvo\s+com\s+sucesso|cadastrad|registrad|enviad\s+com\s+sucesso)",
    re.I,
)

TIMEOUT_LOADER_TOPO_S = 120
OPERA_EXE = None
PASTA_SCREENSHOTS = Path(__file__).resolve().parent / "screenshots_pub"

MODAL_TITULO_REGEX_RGF = r"Criar.*(Relatório de Gestão Fiscal|RGF)"
MODAL_TITULO_REGEX_RREO = (
    r"Criar.*(Relatório Resumido de Execução Orçamentária|RREO|Execução Orçamentária)"
)
MODAL_TITULO_REGEX_BALANCETE = r"Criar.*Balancete\s+Financeiro"
MODAL_TITULO_REGEX_BALANCO_REL = (
    r"Criar.*Balan[çc]o\s+e\s+Relat[óo]rios\s+Anuais"
)
MODAL_TITULO_REGEX = MODAL_TITULO_REGEX_RGF

TIPOS_BALANCO_REL_ANUAIS_UI = (
    "Relatório do Controle Interno",
    "Balanço Anual",
    "Relatório de Gestão",
    "Demais Relatórios",
)

LABELS_DESCRICAO_BALANCO_REL = ("Descrição", "Descricao")
LABELS_TIPO_BALANCO_REL = ("Tipo",)

LABELS_ANO = (
    "Ano",
    "Ano de referência",
    "Exercício",
    "Informe o ano",
    "Digite o ano",
)
LABELS_REFERENCIA = ("Referência", "Período", "Quadrimestre")
LABELS_NOME_DOC = (
    "Nome do documento",
    "Nome do Documento",
    "Nome",
    "Titulo",
    "Título",
)

OPCOES_QUADRIMESTRE_UI = {
    1: "1º quadrimestre",
    2: "2º quadrimestre",
    3: "3º quadrimestre",
}

OPCOES_SEMESTRE_UI = {
    1: "1º semestre",
    2: "2º semestre",
}

OPCOES_BIMESTRE_UI = {
    1: "1º bimestre",
    2: "2º bimestre",
    3: "3º bimestre",
    4: "4º bimestre",
    5: "5º bimestre",
    6: "6º bimestre",
}

MESES_PT_PARA_NUM = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

LABELS_MES_ANO_BALANCETE = (
    "Mês e Ano",
    "Mes e Ano",
    "Mês/Ano",
)


def url_portal_ativa(url):
    return bool((url or "").strip())


def _fold_ascii(s):
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()


def _build_mapa_tipos_balanco_pasta():
    """Nome da pasta (sem '-AAAA') -> texto exato no dropdown Bubble."""
    m = {}
    for ui in TIPOS_BALANCO_REL_ANUAIS_UI:
        m[_fold_ascii(ui)] = ui
    m[_fold_ascii("Relatorio do Controle Interno")] = "Relatório do Controle Interno"
    m[_fold_ascii("Balanco Anual")] = "Balanço Anual"
    m[_fold_ascii("Relatorio de Gestao")] = "Relatório de Gestão"
    m[_fold_ascii("Demais Relatorios")] = "Demais Relatórios"
    return m


_MAPA_TIPO_PASTA_BALANCO_REL = _build_mapa_tipos_balanco_pasta()


# ---------------------------------------------------------------------


def _opera_via_program_files():
    local = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("PROGRAMFILES", "")
    prog_x86 = os.environ.get("PROGRAMFILES(X86)", "")
    candidatos = []
    base_local = Path(local) / "Programs"
    if base_local.is_dir():
        for folder in sorted(base_local.glob("Opera*")):
            if folder.is_dir():
                exe = folder / "opera.exe"
                if exe.is_file():
                    candidatos.append(exe.resolve())
    candidatos.extend(
        [
            Path(local) / "Programs" / "Opera" / "opera.exe",
            Path(local) / "Programs" / "Opera GX" / "opera.exe",
            Path(prog) / "Opera" / "opera.exe",
            Path(prog) / "Opera GX" / "opera.exe",
            Path(prog_x86) / "Opera" / "opera.exe",
            Path(prog_x86) / "Opera GX" / "opera.exe",
        ]
    )
    visto = set()
    for p in candidatos:
        try:
            if p.is_file():
                r = p.resolve()
                if r not in visto:
                    visto.add(r)
                    return r
        except Exception:
            continue
    return None


def _opera_via_registro_windows():
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )

    for hive, path in roots:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        i = 0
        while True:
            try:
                subname = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            try:
                sk = winreg.OpenKey(key, subname)
            except OSError:
                continue
            try:
                try:
                    disp = winreg.QueryValueEx(sk, "DisplayName")[0]
                except OSError:
                    continue
                if "Opera" not in str(disp):
                    continue
                try:
                    loc = winreg.QueryValueEx(sk, "InstallLocation")[0]
                    exe = Path(str(loc).strip().strip('"')) / "opera.exe"
                    if exe.is_file():
                        return exe.resolve()
                except OSError:
                    pass
                try:
                    icon = winreg.QueryValueEx(sk, "DisplayIcon")[0]
                    icon = str(icon).split(",")[0].strip().strip('"')
                    if icon.lower().endswith("opera.exe"):
                        exe = Path(icon)
                        if exe.is_file():
                            return exe.resolve()
                except OSError:
                    pass
            finally:
                try:
                    winreg.CloseKey(sk)
                except Exception:
                    pass
        try:
            winreg.CloseKey(key)
        except Exception:
            pass
    return None


def resolver_caminho_opera():
    """Encontra opera.exe sem configuracao manual (Windows)."""
    if OPERA_EXE:
        p = Path(OPERA_EXE).expanduser()
        if p.is_file():
            return p.resolve()
        print("[ERRO] OPERA_EXE nao encontrado: {}".format(p))
        return None

    via_path = shutil.which("opera.exe")
    if via_path:
        p = Path(via_path)
        if p.is_file():
            return p.resolve()

    p = _opera_via_program_files()
    if p is not None:
        return p

    p = _opera_via_registro_windows()
    if p is not None:
        return p

    return None


def normalizar(texto):
    subs = {
        "ç": "c", "ã": "a", "á": "a", "â": "a", "à": "a",
        "é": "e", "ê": "e", "í": "i", "ó": "o", "ô": "o",
        "õ": "o", "ú": "u", "ü": "u",
    }
    for orig, dest in subs.items():
        texto = texto.replace(orig, dest)
    return texto


def extrair_meta_rgf(pdf_path):
    """
    Retorna dict com ano, referencia_tipo (quadrimestre|semestre|bimestre), referencia_num,
    quadrimestre (alias legado para ordenacao/log) e nome_documento; ou None.
    """
    parent = pdf_path.parent.name
    ano = None
    if re.fullmatch(r"\d{4}", parent):
        ano = int(parent)

    nome_arq = pdf_path.name
    nome_norm = normalizar(nome_arq.lower())

    referencia_tipo = None
    referencia_num = None

    _rx_periodo = r"(\d)\s*(?:\u00ba|º|°|o)?\.?\s*{}"

    m_bim = re.search(_rx_periodo.format("bimestre"), nome_norm)
    if m_bim:
        referencia_num = int(m_bim.group(1))
        if 1 <= referencia_num <= 6:
            referencia_tipo = "bimestre"

    if referencia_tipo is None:
        m_sem = re.search(_rx_periodo.format("semestre"), nome_norm)
        if m_sem:
            referencia_num = int(m_sem.group(1))
            if 1 <= referencia_num <= 2:
                referencia_tipo = "semestre"

    if referencia_tipo is None:
        m_quad = re.search(_rx_periodo.format("quadrimestre"), nome_norm)
        if m_quad:
            referencia_num = int(m_quad.group(1))
            if 1 <= referencia_num <= 3:
                referencia_tipo = "quadrimestre"

    if referencia_tipo is None:
        return None

    if ano is None:
        m_ano = re.search(r"(20\d{2})", nome_norm)
        if not m_ano:
            return None
        ano = int(m_ano.group(1))

    return {
        "ano": ano,
        "referencia_tipo": referencia_tipo,
        "referencia_num": referencia_num,
        "quadrimestre": referencia_num,
        "nome_documento": pdf_path.stem,
    }


extrair_meta_rreo = extrair_meta_rgf


def listar_pdfs_rreo(pasta_base=None, ano_filtro=None):
    """Mesma estrutura do RGF: subpastas por ano + quadrimestre/semestre no nome."""
    if pasta_base is None:
        pasta_base = PASTA_RREO
    return listar_pdfs_rgf(pasta_base, ano_filtro)


def ordenar_fila_pdfs_rreo(pdfs):
    return ordenar_fila_pdfs_rgf(pdfs)


def listar_pdfs_rgf(pasta_base, ano_filtro=None):
    if not pasta_base.exists():
        print("[ERRO] Pasta nao encontrada: {}".format(pasta_base))
        sys.exit(1)

    if ano_filtro:
        pasta = pasta_base / str(ano_filtro)
        if not pasta.is_dir():
            print("[ERRO] Pasta do ano nao encontrada: {}".format(pasta))
            sys.exit(1)
        pdfs = sorted(pasta.glob("*.pdf"))
    else:
        pdfs = sorted(pasta_base.rglob("*.pdf"))

    if not pdfs:
        print("[ERRO] Nenhum PDF encontrado.")
        sys.exit(1)
    return pdfs


def listar_pdfs_balancete(pasta_base):
    """PDFs em subpastas Mes-Ano ou nomes Mes-Ano.pdf sob pasta_base."""
    if not pasta_base.exists():
        print("[ERRO] Pasta Balancete nao encontrada: {}".format(pasta_base))
        sys.exit(1)
    pdfs = sorted(pasta_base.rglob("*.pdf"))
    if not pdfs:
        print("[ERRO] Nenhum PDF de Balancete encontrado em {}.".format(pasta_base))
        sys.exit(1)
    return pdfs


def extrair_meta_balancete(pdf_path):
    """
    Pastas/arquivos tipo 'Janeiro-2021' ou 'setembro-2021'.
    Aceita ...\\Balancete de Despesa\\2025\\Janeiro-2025.pdf (ano so na pasta pai).
    """
    candidatos = [pdf_path.stem]
    p = pdf_path.parent
    for _ in range(5):
        if not p.name:
            break
        candidatos.append(p.name)
        if p == p.parent:
            break
        p = p.parent

    ano_pasta_pai = None
    if re.fullmatch(r"\d{4}", pdf_path.parent.name or ""):
        ano_pasta_pai = int(pdf_path.parent.name)

    balancete_grupo = None
    for parte in pdf_path.parts:
        pl = parte.lower()
        if "balancete de despesa" in pl or pl == "despesa":
            balancete_grupo = "Despesa"
            break
        if "balancete de receita" in pl or pl == "receita":
            balancete_grupo = "Receita"
            break

    for nome in candidatos:
        nome_l = nome.strip()
        m = re.match(r"^(.+?)-(\d{4})$", nome_l, re.I)
        if not m:
            continue
        mes_txt = normalizar(m.group(1).strip().lower())
        ano = int(m.group(2))
        mes_txt = mes_txt.replace("março", "marco")
        mes_num = MESES_PT_PARA_NUM.get(mes_txt)
        if mes_num is None:
            continue
        meta = {
            "mes": mes_num,
            "ano": ano,
            "mes_ano_ui": "{:02d}/{}".format(mes_num, ano),
            "nome_documento": pdf_path.stem,
        }
        if balancete_grupo:
            meta["balancete_grupo"] = balancete_grupo
        return meta

    if ano_pasta_pai is not None:
        stem = pdf_path.stem.strip()
        mes_txt = normalizar(stem.lower()).replace("março", "marco")
        mes_num = MESES_PT_PARA_NUM.get(mes_txt)
        if mes_num is not None:
            meta = {
                "mes": mes_num,
                "ano": ano_pasta_pai,
                "mes_ano_ui": "{:02d}/{}".format(mes_num, ano_pasta_pai),
                "nome_documento": pdf_path.stem,
            }
            if balancete_grupo:
                meta["balancete_grupo"] = balancete_grupo
            return meta

    return None


def ordenar_fila_pdfs_balancete(pdfs):
    def key(p):
        m = extrair_meta_balancete(p)
        if m:
            grp = m.get("balancete_grupo") or ""
            return (0, grp, m["ano"], m["mes"], str(p).lower())
        return (1, "zzz", 9999, 99, str(p).lower())
    return sorted(pdfs, key=key)


def ordenar_fila_pdfs_rgf(pdfs):
    """Ordem estavel: ano, quadrimestre (meta no nome). Sem meta vai ao fim."""
    def key(p):
        m = extrair_meta_rgf(p)
        if m:
            return (0, m["ano"], m["quadrimestre"], str(p).lower())
        return (1, 9999, 99, str(p).lower())
    return sorted(pdfs, key=key)


def listar_pdfs_balanco_rel_anuais(pasta_base):
    if not pasta_base.exists():
        print(
            "[ERRO] Pasta Balanco/Relatorios Anuais nao encontrada: {}".format(
                pasta_base
            )
        )
        sys.exit(1)
    pdfs = sorted(pasta_base.rglob("*.pdf"))
    if not pdfs:
        print("[ERRO] Nenhum PDF encontrado em {}.".format(pasta_base))
        sys.exit(1)
    return pdfs


def _resolver_tipo_pasta_balanco_para_ui(nome_tipo_pasta):
    """Nome da pasta do tipo (sem ano) -> texto exato no dropdown Bubble."""
    if not nome_tipo_pasta:
        return None
    chave = _fold_ascii(nome_tipo_pasta.strip())
    tipo_ui = _MAPA_TIPO_PASTA_BALANCO_REL.get(chave)
    if tipo_ui is not None:
        return tipo_ui
    for ui in TIPOS_BALANCO_REL_ANUAIS_UI:
        if chave == _fold_ascii(ui):
            return ui
    for ui in TIPOS_BALANCO_REL_ANUAIS_UI:
        fc = _fold_ascii(ui)
        if chave.startswith(fc) or fc.startswith(chave):
            return ui
    return None


def extrair_meta_balanco_rel_anuais(pdf_path):
    """
    Aceita:
      - Pasta pai '<Tipo>-<AAAA>' (ex.: Relatorio de Gestao-2024)
      - Ou .../<Tipo>/<AAAA>/arquivo.pdf (pasta do ano so numerica).
    """
    nome_pasta = pdf_path.parent.name.strip()

    m_hifen = re.match(r"^(.+)-(\d{4})$", nome_pasta)
    if m_hifen:
        ano = int(m_hifen.group(2))
        tipo_ui = _resolver_tipo_pasta_balanco_para_ui(m_hifen.group(1))
        if tipo_ui is None:
            return None
        descricao = pdf_path.stem.replace("_", " ").strip()[:200]
        return {
            "tipo_ui": tipo_ui,
            "ano": ano,
            "descricao": descricao,
            "nome_documento": pdf_path.stem,
        }

    m_so_ano = re.match(r"^(\d{4})$", nome_pasta)
    if m_so_ano:
        ano = int(m_so_ano.group(1))
        try:
            tipo_folder = pdf_path.parent.parent.name.strip()
        except Exception:
            return None
        tipo_ui = _resolver_tipo_pasta_balanco_para_ui(tipo_folder)
        if tipo_ui is None:
            return None
        descricao = pdf_path.stem.replace("_", " ").strip()[:200]
        return {
            "tipo_ui": tipo_ui,
            "ano": ano,
            "descricao": descricao,
            "nome_documento": pdf_path.stem,
        }

    return None


def ordenar_fila_pdfs_balanco_rel_anuais(pdfs):
    def key(p):
        meta = extrair_meta_balanco_rel_anuais(p)
        if meta:
            try:
                ordem_tipo = TIPOS_BALANCO_REL_ANUAIS_UI.index(meta["tipo_ui"])
            except ValueError:
                ordem_tipo = 99
            return (0, meta["ano"], ordem_tipo, str(p).lower())
        return (1, 9999, 99, str(p).lower())

    return sorted(pdfs, key=key)


def salvar_screenshot(page, nome):
    try:
        PASTA_SCREENSHOTS.mkdir(parents=True, exist_ok=True)
        caminho = PASTA_SCREENSHOTS / "{}.png".format(nome)
        page.screenshot(path=str(caminho), full_page=True)
    except Exception:
        pass


def preencher_campo(page, locator, valor):
    locator.click()
    time.sleep(0.08)
    page.keyboard.press("Control+a")
    time.sleep(0.05)
    page.keyboard.press("Delete")
    time.sleep(0.05)
    locator.fill(valor)
    time.sleep(0.08)


def preencher_campo_rapido(page, locator, valor):
    """Login Bubble: fill direto (menos sleeps que preencher_campo)."""
    try:
        locator.focus(timeout=4000)
    except Exception:
        locator.click(timeout=6000)
    locator.fill(valor, timeout=8000)


def fazer_upload(page, pdf_path, modal_root=None):
    try:
        page.evaluate("""
            const inputs = document.querySelectorAll('input[type=file]');
            inputs.forEach(el => {
                el.style.display = 'block';
                el.style.opacity = '1';
                el.style.visibility = 'visible';
                el.style.position = 'fixed';
                el.style.top = '0';
                el.style.left = '0';
                el.style.zIndex = '99999';
            });
        """)
        time.sleep(0.1)
        if modal_root is not None:
            input_file = modal_root.locator("input[type=file]").first
        else:
            input_file = page.locator("input[type=file]").first
        input_file.wait_for(state="attached", timeout=5000)
        input_file.set_input_files(str(pdf_path))
        time.sleep(PAUSA_APOS_ANEXAR_PDF)
        return True
    except Exception as e:
        print("    [Upload] Falhou: {}".format(str(e)[:80]))
        return False


def _regex_modal_titulo(modal_kind):
    if modal_kind == "balancete":
        return MODAL_TITULO_REGEX_BALANCETE
    if modal_kind == "balanco_rel":
        return MODAL_TITULO_REGEX_BALANCO_REL
    if modal_kind == "rreo":
        return MODAL_TITULO_REGEX_RREO
    return MODAL_TITULO_REGEX_RGF


def _loc_modal_titulo(page, modal_kind="rgf"):
    """modal_kind: 'rgf' | 'rreo' | 'balancete' | 'balanco_rel'"""
    return page.locator(
        "text=/{}/i".format(_regex_modal_titulo(modal_kind))
    ).first


def abrir_modal(page, modal_kind="rgf"):
    criar_btn = page.locator("button:has-text('Criar Publicação')").first
    criar_btn.wait_for(state="visible", timeout=15000)
    criar_btn.scroll_into_view_if_needed()
    time.sleep(0.06)
    criar_btn.click()
    time.sleep(0.26)
    _loc_modal_titulo(page, modal_kind).wait_for(state="visible", timeout=10000)
    time.sleep(0.11)


def _limpar_marcador_modal_cr2(page):
    try:
        page.evaluate(
            """
            () => {
                document.querySelectorAll('[data-cr2-pub-modal-marker]').forEach(function (el) {
                    el.removeAttribute('data-cr2-pub-modal-marker');
                });
            }
            """
        )
    except Exception:
        pass


def _modal_bubble_publicacao(page, modal_kind="rgf"):
    """
    Bubble: ancestral do botao Publicar.
    rgf: select Referencia + campo ano.
    rreo: igual ao RGF (Ano + Referencia + Arquivo).
    balancete: Mês e Arquivo (sem select no modal).
    balanco_rel: Tipo (select) + Ano + Arquivo.
    """
    _limpar_marcador_modal_cr2(page)
    try:
        marcado = page.evaluate(
            """
            (kind) => {
                document.querySelectorAll('[data-cr2-pub-modal-marker]').forEach(function (el) {
                    el.removeAttribute('data-cr2-pub-modal-marker');
                });
                function texto(btn) {
                    return ((btn.innerText || btn.textContent || '') + '').trim();
                }
                var pubs = Array.from(
                    document.querySelectorAll('button, div[role="button"], .bubble-element.Button')
                ).filter(function (b) {
                    var t = texto(b);
                    return (t === 'Publicar' || t.indexOf('Publicar') >= 0) && t.length < 48;
                });
                for (var i = pubs.length - 1; i >= 0; i--) {
                    var node = pubs[i];
                    var depth = 0;
                    while (node && depth < 28) {
                        depth++;
                        node = node.parentElement;
                        if (!node || !node.querySelectorAll) continue;
                        var txt = (node.innerText || '').slice(0, 5000);
                        var selects = node.querySelectorAll('select');
                        var files = node.querySelectorAll('input[type=file]');
                        var inpAno = node.querySelector(
                            'input[placeholder*="Ex"], input[placeholder*="202"], '
                                + 'input.bubble-element.Input'
                        );
                        var inpMes = node.querySelector(
                            'input[placeholder*="01"], input[placeholder*="/20"], '
                                + 'input[placeholder*="/"], input.bubble-element.Input'
                        );
                        if (kind === 'balanco_rel') {
                            var tituloBRA = txt.indexOf('Relatórios Anuais') >= 0 ||
                                txt.indexOf('Relatórios anuais') >= 0 ||
                                txt.indexOf('Balanço e Relatórios') >= 0 ||
                                txt.indexOf('Balanco e Relatorios') >= 0;
                            var mesAnoLbl = txt.indexOf('Mês e Ano') >= 0 ||
                                txt.indexOf('Mes e Ano') >= 0;
                            var quadLbl = txt.indexOf('Quadrimestre') >= 0 ||
                                txt.indexOf('quadrimestre') >= 0;
                            if (mesAnoLbl || quadLbl) continue;
                            if (!tituloBRA && txt.indexOf('Tipo') < 0) continue;
                            if (!selects.length || !inpAno || !files.length) continue;
                            node.setAttribute('data-cr2-pub-modal-marker', '1');
                            return true;
                        }
                        if (kind === 'rgf') {
                            if (txt.indexOf('Relatórios Anuais') >= 0 ||
                                txt.indexOf('Relatórios anuais') >= 0 ||
                                txt.indexOf('Balanço e Relatórios') >= 0 ||
                                txt.indexOf('Balanco e Relatorios') >= 0) continue;
                            if (txt.indexOf('RREO') >= 0 ||
                                txt.indexOf('Execução Orçamentária') >= 0 ||
                                txt.indexOf('Execucao Orcamentaria') >= 0 ||
                                txt.indexOf('Resumido de Execu') >= 0) continue;
                            if (!selects.length || !inpAno) continue;
                            node.setAttribute('data-cr2-pub-modal-marker', '1');
                            return true;
                        }
                        if (kind === 'rreo') {
                            if (txt.indexOf('Relatórios Anuais') >= 0 ||
                                txt.indexOf('Relatórios anuais') >= 0 ||
                                txt.indexOf('Balanço e Relatórios') >= 0 ||
                                txt.indexOf('Balanco e Relatorios') >= 0) continue;
                            if (txt.indexOf('Gestão Fiscal') >= 0 ||
                                txt.indexOf('Gestao Fiscal') >= 0 ||
                                (txt.indexOf('RGF') >= 0 &&
                                    txt.indexOf('RREO') < 0)) continue;
                            var tituloRREO = txt.indexOf('RREO') >= 0 ||
                                txt.indexOf('Execução Orçamentária') >= 0 ||
                                txt.indexOf('Execucao Orcamentaria') >= 0 ||
                                txt.indexOf('Resumido de Execu') >= 0;
                            if (!tituloRREO) continue;
                            if (!selects.length || !inpAno) continue;
                            node.setAttribute('data-cr2-pub-modal-marker', '1');
                            return true;
                        }
                        if (kind === 'balancete') {
                            var tituloBal = txt.indexOf('Balancete Financeiro') >= 0;
                            var mesAnoLbl = txt.indexOf('Mês e Ano') >= 0 ||
                                txt.indexOf('Mes e Ano') >= 0;
                            var arqLbl = txt.indexOf('Arquivo') >= 0;
                            if (!tituloBal && !(mesAnoLbl && arqLbl)) continue;
                            if (!files.length || !inpMes) continue;
                            node.setAttribute('data-cr2-pub-modal-marker', '1');
                            return true;
                        }
                    }
                }
                return false;
            }
            """,
            modal_kind,
        )
        if marcado:
            root = page.locator('[data-cr2-pub-modal-marker="1"]').first
            root.wait_for(state="visible", timeout=12000)
            return root
    except Exception:
        pass

    sel_drop = (
        "select.bubble-element.Dropdown, select.dropdown-chevron, "
        "select[class*='Dropdown']"
    )
    inp_ano = (
        "input[placeholder*='Ex'], input[placeholder*='202'], "
        "input.bubble-element.Input"
    )
    inp_mes = (
        "input[placeholder*='01'], input[placeholder*='/'], "
        "input.bubble-element.Input"
    )
    try:
        if modal_kind == "rgf":
            cand = page.locator("div.bubble-element.Group").filter(
                has=page.locator("button:has-text('Publicar')")
            ).filter(has=page.locator(sel_drop)).filter(has=page.locator(inp_ano))
        elif modal_kind == "rreo":
            cand = page.locator("div.bubble-element.Group").filter(
                has_text=re.compile(
                    r"RREO|Execu[cç][aã]o\s+Or[cç]ament[aá]ria|Resumido",
                    re.I,
                )
            ).filter(has=page.locator("button:has-text('Publicar')")).filter(
                has=page.locator(sel_drop)
            ).filter(has=page.locator(inp_ano))
        elif modal_kind == "balanco_rel":
            cand = page.locator("div.bubble-element.Group").filter(
                has_text=re.compile(
                    r"Relatórios\s+Anuais|Balan[çc]o\s+e\s+Relat",
                    re.I,
                )
            ).filter(has=page.locator("button:has-text('Publicar')")).filter(
                has=page.locator(sel_drop)
            ).filter(has=page.locator(inp_ano)).filter(
                has=page.locator("input[type=file]")
            )
        else:
            cand = page.locator("div.bubble-element.Group").filter(
                has=page.locator("button:has-text('Publicar')")
            ).filter(has=page.locator("input[type=file]")).filter(
                has=page.locator(inp_mes)
            )
        if cand.count() > 0:
            root = cand.first
            root.wait_for(state="visible", timeout=12000)
            return root
    except Exception:
        pass
    try:
        root = page.locator("div.bubble-element.Group").filter(
            has=page.locator("button:has-text('Fechar')")
        ).filter(has=page.locator("button:has-text('Publicar')")).first
        root.wait_for(state="visible", timeout=12000)
        return root
    except Exception:
        return None


def _escopos_modal_publicacao(page):
    """Bubble pode nao usar role=dialog; tentamos varios ancestrais do modal."""
    roots = []
    bm = _modal_bubble_publicacao(page, "rgf")
    if bm is not None:
        roots.append(bm)
    try:
        dlg = page.locator("[role='dialog']").filter(
            has_text=re.compile(r"Gestão Fiscal|RGF", re.I)
        ).first
        dlg.wait_for(state="visible", timeout=6000)
        roots.append(dlg)
    except Exception:
        pass
    try:
        dlg2 = page.locator("[role='dialog']").first
        dlg2.wait_for(state="visible", timeout=4000)
        if dlg2 not in roots:
            roots.append(dlg2)
    except Exception:
        pass
    roots.append(page)
    return roots


def _preencher_ano(page, ano_int, modal_root=None):
    s = str(ano_int)

    def tentar_em(root, nome_log):
        # Bubble usa type="input" e classe bubble-element Input (placeholder Ex.: 2026)
        try:
            loc = root.locator(
                "input.bubble-element.Input[placeholder*='Ex'], "
                "input.bubble-element.Input[placeholder*='202'], "
                "input[type='input'][placeholder*='Ex'], "
                "input[type='input'][placeholder*='202'], "
                "input[placeholder*='Ex'], input[placeholder*='2026'], "
                "input[placeholder*='202']"
            ).first
            loc.wait_for(state="visible", timeout=5000)
            preencher_campo(page, loc, s)
            print("    Ano preenchido ({} — CSS placeholder).".format(nome_log))
            return True
        except Exception:
            pass
        try:
            loc = root.get_by_placeholder(re.compile(r"ex\.?\s*:", re.I)).first
            loc.wait_for(state="visible", timeout=4000)
            preencher_campo(page, loc, s)
            print("    Ano preenchido ({} — get_by_placeholder).".format(nome_log))
            return True
        except Exception:
            pass
        if _fill_by_label_candidates(root, LABELS_ANO, s, page):
            print("    Ano preenchido ({} — label).".format(nome_log))
            return True
        for rx in (
            re.compile(r"informe.*ano", re.I),
            re.compile(r"^\s*Ano\s*\*?\s*$", re.I),
            re.compile(r"\bano\b", re.I),
        ):
            try:
                loc = root.get_by_label(rx).first
                loc.wait_for(state="visible", timeout=2500)
                preencher_campo(page, loc, s)
                print("    Ano preenchido ({} — label regex).".format(nome_log))
                return True
            except Exception:
                continue
        try:
            loc = root.locator(
                "xpath=(//*[contains(normalize-space(.),'Ano')]"
                "[not(contains(normalize-space(.),'Refer'))])[1]"
                "/following::input[not(@type='file') and not(@type='hidden')][1]"
            ).first
            loc.wait_for(state="visible", timeout=5000)
            preencher_campo(page, loc, s)
            print("    Ano preenchido ({} — xpath apos rotulo).".format(nome_log))
            return True
        except Exception:
            pass
        try:
            curto = root.locator(
                "input[maxlength='4'], input[inputmode='numeric']"
            ).first
            curto.wait_for(state="visible", timeout=3000)
            preencher_campo(page, curto, s)
            print("    Ano preenchido ({} — campo curto).".format(nome_log))
            return True
        except Exception:
            pass
        try:
            prim = root.locator(
                "input:not([type='file']):not([type='hidden'])"
            ).first
            prim.wait_for(state="visible", timeout=4000)
            preencher_campo(page, prim, s)
            print(
                "    Ano preenchido ({} — primeiro input editavel do modal).".format(
                    nome_log
                )
            )
            return True
        except Exception:
            pass
        return False

    if modal_root is not None:
        try:
            if tentar_em(modal_root, "modal atual"):
                return
        except Exception:
            pass

    for idx, root in enumerate(_escopos_modal_publicacao(page)):
        if tentar_em(root, "escopo {}".format(idx)):
            return

    try:
        if page.evaluate(
            """
            (v) => {
                function fire(el) {
                    el.dispatchEvent(new Event("input", {bubbles: true}));
                    el.dispatchEvent(new Event("change", {bubbles: true}));
                }
                function bubbleModalRoot() {
                    var groups = document.querySelectorAll('div.bubble-element.Group');
                    for (var i = groups.length - 1; i >= 0; i--) {
                        var g = groups[i];
                        var bs = g.querySelectorAll('button');
                        var hasF = false, hasP = false;
                        for (var k = 0; k < bs.length; k++) {
                            var t = (bs[k].innerText || '').trim();
                            if (t.indexOf('Fechar') >= 0) hasF = true;
                            if (t.indexOf('Publicar') >= 0) hasP = true;
                        }
                        if (hasF && hasP) return g;
                    }
                    return null;
                }
                var roots = [];
                var dialogs = document.querySelectorAll('[role="dialog"]');
                if (dialogs.length) roots = roots.concat(Array.from(dialogs));
                var bm = bubbleModalRoot();
                if (bm) roots.push(bm);
                if (!roots.length) roots = [document.body];
                for (var i = 0; i < roots.length; i++) {
                    var r = roots[i];
                    var inputs = r.querySelectorAll(
                        'input:not([type="file"]):not([type="hidden"])'
                    );
                    for (var j = 0; j < inputs.length; j++) {
                        var el = inputs[j];
                        var ph = (el.getAttribute("placeholder") || "").toLowerCase();
                        if (ph.indexOf("ex") >= 0 || ph.indexOf("202") >= 0) {
                            el.focus();
                            el.value = v;
                            fire(el);
                            return true;
                        }
                    }
                    if (inputs.length) {
                        var el = inputs[0];
                        el.focus();
                        el.value = v;
                        fire(el);
                        return true;
                    }
                }
                return false;
            }
            """,
            s,
        ):
            print("    Ano preenchido (injetado no DOM — Bubble).")
            time.sleep(0.05)
            return
    except Exception:
        pass

    raise Exception("Campo Ano nao encontrado")


def fechar_modal(page, modal_kind="rgf"):
    try:
        modal_root = _modal_bubble_publicacao(page, modal_kind)
        if modal_root is not None:
            fechar = modal_root.locator("button:has-text('Fechar')").first
        else:
            fechar = page.locator("button:has-text('Fechar')").first
        fechar.wait_for(state="visible", timeout=5000)
        fechar.click()
        time.sleep(0.25)
        _loc_modal_titulo(page, modal_kind).wait_for(state="hidden", timeout=8000)
        time.sleep(0.11)
    except Exception:
        try:
            page.keyboard.press("Escape")
            time.sleep(0.22)
        except Exception:
            pass


def _fill_by_label_candidates(scope, labels, valor, page):
    for lb in labels:
        loc = scope.get_by_label(lb, exact=False).first
        try:
            loc.wait_for(state="visible", timeout=2500)
            preencher_campo(page, loc, valor)
            return True
        except Exception:
            continue
    return False


def _preencher_nome_documento_se_existir(page, nome, modal_root=None):
    """Formulario RGF do CR2 costuma ter só Ano + Referência + Arquivo (sem nome separado)."""
    scope = modal_root if modal_root is not None else page
    if _fill_by_label_candidates(scope, LABELS_NOME_DOC, nome, page):
        print("    Nome do documento preenchido.")
        return
    for rx in (
        re.compile(r"Nome", re.I),
        re.compile(r"documento", re.I),
        re.compile(r"t[ií]tulo", re.I),
    ):
        loc = scope.get_by_placeholder(rx).first
        try:
            loc.wait_for(state="visible", timeout=2000)
            preencher_campo(page, loc, nome)
            print("    Nome do documento preenchido (placeholder).")
            return
        except Exception:
            continue
    print("    [INFO] Sem campo 'Nome do documento' no modal — usando só o arquivo.")


def _variantes_texto_quadrimestre(quadrimestre):
    """Bubble pode listar '1º quadrimestre' ou '1º Quadrimestre'."""
    base = OPCOES_QUADRIMESTRE_UI[quadrimestre]
    parte_num, parte_txt = base.rsplit(" ", 1)
    cap_q = "{} {}".format(parte_num, parte_txt.capitalize())
    return [base, cap_q]


def _variantes_texto_semestre(semestre):
    base = OPCOES_SEMESTRE_UI[semestre]
    parte_num, parte_txt = base.rsplit(" ", 1)
    cap_s = "{} {}".format(parte_num, parte_txt.capitalize())
    return [base, cap_s]


def _variantes_texto_bimestre(bimestre):
    base = OPCOES_BIMESTRE_UI[bimestre]
    parte_num, parte_txt = base.rsplit(" ", 1)
    cap_b = "{} {}".format(parte_num, parte_txt.capitalize())
    return [base, cap_b]


def _variantes_referencia_rgf(meta):
    n = meta["referencia_num"]
    tipo = meta.get("referencia_tipo")
    if tipo == "semestre":
        return _variantes_texto_semestre(n)
    if tipo == "bimestre":
        return _variantes_texto_bimestre(n)
    return _variantes_texto_quadrimestre(n)


def _tentar_select_referencia_modal(modal_root, variantes, periodo_num, modo="quadrimestre"):
    """Tenta cada <select> dentro do modal (Bubble pode ocultar visualmente o native)."""
    if modal_root is None:
        return False
    selects = modal_root.locator("select")
    try:
        n = selects.count()
    except Exception:
        return False
    if modo == "semestre":
        texto_ui = OPCOES_SEMESTRE_UI[periodo_num]
        rotulo = "semestre"
    elif modo == "bimestre":
        texto_ui = OPCOES_BIMESTRE_UI[periodo_num]
        rotulo = "bimestre"
    else:
        texto_ui = OPCOES_QUADRIMESTRE_UI[periodo_num]
        rotulo = "quadrimestre"
    valores_extra = [
        str(periodo_num),
        "{}__{}".format(periodo_num, rotulo),
        "{}_{}".format(periodo_num, rotulo),
        texto_ui.replace(" ", "_").lower(),
        texto_ui.replace("º ", "").replace(" ", "_").lower(),
    ]
    for i in range(n):
        sel = selects.nth(i)
        try:
            sel.wait_for(state="attached", timeout=4000)
        except Exception:
            continue
        for texto_opcao in variantes:
            try:
                sel.select_option(label=texto_opcao, timeout=4000)
                print(
                    "    Referencia (select idx {} — modal Bubble): {}".format(
                        i, texto_opcao
                    )
                )
                return True
            except Exception:
                pass
            try:
                sel.select_option(
                    label=re.compile(re.escape(texto_opcao), re.I), timeout=3000
                )
                print(
                    "    Referencia (select idx {} — regex label): {}".format(
                        i, texto_opcao
                    )
                )
                return True
            except Exception:
                pass
        for v in valores_extra:
            try:
                sel.select_option(value=v, timeout=2000)
                print("    Referencia (select idx {} — value): {}".format(i, v))
                return True
            except Exception:
                continue
    return False


def _preencher_referencia_rgf(page, meta, modal_root=None):
    variantes = _variantes_referencia_rgf(meta)
    periodo_num = meta["referencia_num"]
    modo = meta.get("referencia_tipo") or "quadrimestre"

    if _tentar_select_referencia_modal(modal_root, variantes, periodo_num, modo=modo):
        return

    if modal_root is not None:
        sel = modal_root.locator("select.bubble-element.Dropdown").first
        try:
            sel.wait_for(state="visible", timeout=6000)
            for texto_opcao in variantes:
                try:
                    sel.select_option(label=texto_opcao)
                    print("    Referencia (select — modal Bubble): {}".format(texto_opcao))
                    return
                except Exception:
                    continue
        except Exception:
            pass

    def clicar_opcao_lista_aberta():
        for texto_opcao in variantes:
            tentativas = [
                lambda t=texto_opcao: page.get_by_text(t, exact=True).last,
                lambda t=texto_opcao: page.get_by_role(
                    "option", name=re.compile(re.escape(t), re.I)
                ).last,
                lambda t=texto_opcao: page.locator(
                    "[role='option']:has-text('{}')".format(t)
                ).last,
            ]
            for mk in tentativas:
                try:
                    opt = mk()
                    opt.wait_for(state="visible", timeout=3500)
                    opt.click()
                    print("    Referencia (lista): {}".format(texto_opcao))
                    return True
                except Exception:
                    continue
        return False

    scope = modal_root if modal_root is not None else page
    for lb in LABELS_REFERENCIA:
        loc = scope.get_by_label(lb, exact=False).first
        try:
            loc.wait_for(state="visible", timeout=4000)
            tag = loc.evaluate("el => el.tagName")
            if tag == "SELECT":
                for texto_opcao in variantes:
                    try:
                        loc.select_option(label=texto_opcao)
                        print("    Referencia (select): {}".format(texto_opcao))
                        return
                    except Exception:
                        continue
            for texto_opcao in variantes:
                try:
                    loc.select_option(label=texto_opcao)
                    print("    Referencia (select native): {}".format(texto_opcao))
                    return
                except Exception:
                    continue
            for texto_opcao in variantes:
                try:
                    preencher_campo(page, loc, texto_opcao)
                    print("    Referencia (texto): {}".format(texto_opcao))
                    return
                except Exception:
                    continue
            loc.click()
            time.sleep(0.2)
            if clicar_opcao_lista_aberta():
                return
        except Exception:
            continue

    raise Exception(
        "Campo Referencia/Periodo nao encontrado ({})".format(modo)
    )


def preencher_modal_rgf(page, meta, pdf_path):
    _preencher_modal_ano_referencia(page, meta, pdf_path, modal_kind="rgf")


def preencher_modal_rreo(page, meta, pdf_path):
    _preencher_modal_ano_referencia(page, meta, pdf_path, modal_kind="rreo")


def _preencher_modal_ano_referencia(page, meta, pdf_path, modal_kind="rgf"):
    modal_root = _modal_bubble_publicacao(page, modal_kind)
    _preencher_ano(page, meta["ano"], modal_root=modal_root)
    time.sleep(0.03)
    _preencher_referencia_rgf(page, meta, modal_root=modal_root)
    time.sleep(0.03)
    _preencher_nome_documento_se_existir(
        page, meta["nome_documento"], modal_root=modal_root
    )
    time.sleep(0.04)

    if not fazer_upload(page, pdf_path, modal_root=modal_root):
        raise Exception("Upload falhou")

    nome_pdf_lower = pdf_path.name.lower()
    print("    Aguardando confirmacao do upload...")
    for _ in range(MAX_TENTATIVAS_POLL_UPLOAD):
        try:
            if modal_root is not None:
                area = modal_root.locator(".file-input-text").first
            else:
                area = page.locator(".file-input-text").first
            txt = area.inner_text().strip()
            tl = txt.lower()
            if nome_pdf_lower and nome_pdf_lower in tl:
                print("    Upload confirmado (arquivo na UI).")
                break
            if len(txt) > 5 and "clique aqui" not in tl:
                print("    Upload confirmado: '{}'".format(txt[:50]))
                break
        except Exception:
            pass
        time.sleep(PAUSA_POLL_UPLOAD_UI)

    time.sleep(PAUSA_APOS_CONFIRMAR_UPLOAD)


def _inner_text_modal_publicacao(page, modal_kind, modal_root):
    if modal_root is not None:
        try:
            return modal_root.inner_text(timeout=2500)
        except Exception:
            pass
    try:
        alt = _modal_bubble_publicacao(page, modal_kind)
        if alt is not None:
            return alt.inner_text(timeout=2500)
    except Exception:
        pass
    try:
        return page.locator("body").inner_text(timeout=2000)
    except Exception:
        return ""


def aguardar_resultado_apos_publicar(page, modal_kind, modal_root):
    """
    Confirma que o Bubble processou Publicar: titulo do modal some (caso comum)
    ou aparece texto de sucesso; se aparecer padrao de erro, levanta excecao.
    """
    titulo_loc = _loc_modal_titulo(page, modal_kind)
    fim = time.monotonic() + TIMEOUT_RESULTADO_PUBLICACAO_S
    ultimo = ""
    while time.monotonic() < fim:
        try:
            visivel = titulo_loc.is_visible(timeout=400)
        except Exception:
            visivel = False
        if not visivel:
            time.sleep(0.28)
            try:
                if titulo_loc.is_visible(timeout=400):
                    continue
            except Exception:
                pass
            print("    Modal fechou — assumindo publicacao aceita pelo Bubble.")
            return

        ultimo = _inner_text_modal_publicacao(page, modal_kind, modal_root)
        if _TEXTO_ERRO_APOS_PUBLICAR_RX.search(ultimo):
            raise RuntimeError(
                "Resposta no modal apos Publicar: {}".format(
                    ultimo.replace("\n", " ").strip()[:260]
                )
            )
        if _TEXTO_SUCESSO_MODAL_RX.search(ultimo):
            print("    Mensagem de sucesso detectada no modal.")
            return

        time.sleep(0.42)

    salvar_screenshot(page, "TIMEOUT_APOS_PUBLICAR_{}".format(modal_kind))
    raise TimeoutError(
        "Modal ainda aberto apos Publicar (~{}s). Ultimo texto: {}".format(
            TIMEOUT_RESULTADO_PUBLICACAO_S,
            ultimo.replace("\n", " ").strip()[:200],
        )
    )


def clicar_publicar(page, modal_kind="rgf"):
    modal_root = _modal_bubble_publicacao(page, modal_kind)
    if modal_root is not None:
        publicar_btn = modal_root.locator("button:has-text('Publicar')").first
    else:
        publicar_btn = page.locator("button:has-text('Publicar')").first
    publicar_btn.wait_for(state="visible", timeout=15000)
    publicar_btn.scroll_into_view_if_needed()

    limite = time.monotonic() + TIMEOUT_PUBLICAR_HABILITADO_S
    while time.monotonic() < limite:
        try:
            if publicar_btn.is_enabled():
                break
        except Exception:
            pass
        time.sleep(0.35)
    else:
        salvar_screenshot(page, "TIMEOUT_PUBLICAR_DESABILITADO_{}".format(modal_kind))
        raise TimeoutError(
            "Botao Publicar ficou desabilitado mais de {}s — "
            "formulario/upload pode estar incompleto.".format(TIMEOUT_PUBLICAR_HABILITADO_S)
        )

    aguardar_barra_carregamento_topo(page, etiqueta="antes de Publicar ({})".format(modal_kind))

    time.sleep(0.12)
    try:
        publicar_btn.click(timeout=15000)
    except Exception:
        publicar_btn.click(force=True, timeout=15000)

    time.sleep(0.18)
    aguardar_resultado_apos_publicar(page, modal_kind, modal_root)
    time.sleep(PAUSA_APOS_CLICAR_PUBLICAR)


def modal_titulo_visivel(page, modal_kind="rgf"):
    try:
        return _loc_modal_titulo(page, modal_kind).is_visible()
    except Exception:
        return False


def modal_rgf_visivel(page):
    return modal_titulo_visivel(page, "rgf")


def publicar_um(page, pdf_path, meta):
    publicar_um_ano_referencia(page, pdf_path, meta, modal_kind="rgf")


def publicar_um_rreo(page, pdf_path, meta):
    publicar_um_ano_referencia(page, pdf_path, meta, modal_kind="rreo")


def publicar_um_ano_referencia(page, pdf_path, meta, modal_kind="rgf"):
    nome_base = normalizar(pdf_path.stem.replace(" ", "_"))
    preencher_fn = (
        preencher_modal_rreo if modal_kind == "rreo" else preencher_modal_rgf
    )

    def rodada_publicar(prefixo_log, prefixo_shot):
        abrir_modal(page, modal_kind)
        preencher_fn(page, meta, pdf_path)
        salvar_screenshot(
            page, "{}_antes_publicar_{}".format(prefixo_shot, nome_base)
        )
        clicar_publicar(page, modal_kind)
        salvar_screenshot(page, "{}_apos_publicar_{}".format(prefixo_shot, nome_base))

    if PUBLICAR_DUPLO_BUBBLE:
        print("    [1/2] Workaround Bubble (PUBLICAR_DUPLO_BUBBLE=True)...")
        rodada_publicar("passo1", "t1")
        print("    Fechando modal para segunda passagem...")
        fechar_modal(page, modal_kind)
        time.sleep(0.28)
        print("    [2/2] Segunda publicacao (workaround)...")
        rodada_publicar("passo2", "t2")
    else:
        rodada_publicar("unica", "pub")

    if modal_titulo_visivel(page, modal_kind):
        print("    Fechando modal apos publicacao...")
        fechar_modal(page, modal_kind)

    time.sleep(0.14)
    print("    Concluido.")


def _preencher_mes_ano_balancete(page, modal_root, mes_ano_ui):
    scope = modal_root if modal_root is not None else page
    for lb in LABELS_MES_ANO_BALANCETE:
        try:
            loc = scope.get_by_label(lb, exact=False).first
            loc.wait_for(state="visible", timeout=4000)
            preencher_campo(page, loc, mes_ano_ui)
            print("    Mes/Ano preenchido (rotulo — {}).".format(lb))
            return
        except Exception:
            continue
    try:
        loc = scope.locator(
            "input[placeholder*='/'], input[placeholder*='01'], "
            "input[placeholder*='202'], input.bubble-element.Input"
        ).first
        loc.wait_for(state="visible", timeout=5000)
        preencher_campo(page, loc, mes_ano_ui)
        print("    Mes/Ano preenchido (placeholder).")
        return
    except Exception:
        pass
    raise Exception("Campo Mes e Ano (Balancete) nao encontrado")


def preencher_modal_balancete(page, meta, pdf_path):
    modal_root = _modal_bubble_publicacao(page, "balancete")
    _preencher_mes_ano_balancete(page, modal_root, meta["mes_ano_ui"])
    try:
        page.keyboard.press("Tab")
    except Exception:
        pass
    time.sleep(0.12)

    if not fazer_upload(page, pdf_path, modal_root=modal_root):
        raise Exception("Upload falhou")

    nome_pdf_lower = pdf_path.name.lower()
    print("    Aguardando confirmacao do upload...")
    for _ in range(MAX_TENTATIVAS_POLL_UPLOAD):
        try:
            if modal_root is not None:
                area = modal_root.locator(".file-input-text").first
            else:
                area = page.locator(".file-input-text").first
            txt = area.inner_text().strip()
            tl = txt.lower()
            if nome_pdf_lower and nome_pdf_lower in tl:
                print("    Upload confirmado (arquivo na UI).")
                break
            if len(txt) > 5 and "clique aqui" not in tl:
                print("    Upload confirmado: '{}'".format(txt[:50]))
                break
        except Exception:
            pass
        time.sleep(PAUSA_POLL_UPLOAD_UI)

    time.sleep(PAUSA_APOS_CONFIRMAR_UPLOAD)


def publicar_um_balancete(page, pdf_path, meta):
    nome_base = normalizar(pdf_path.stem.replace(" ", "_"))

    def rodada(prefixo_shot):
        abrir_modal(page, "balancete")
        preencher_modal_balancete(page, meta, pdf_path)
        salvar_screenshot(
            page, "{}_antes_balancete_{}".format(prefixo_shot, nome_base)
        )
        clicar_publicar(page, "balancete")
        salvar_screenshot(
            page, "{}_apos_balancete_{}".format(prefixo_shot, nome_base)
        )

    if PUBLICAR_DUPLO_BUBBLE:
        print("    [1/2] Balancete — workaround duplo...")
        rodada("t1")
        fechar_modal(page, "balancete")
        time.sleep(0.28)
        rodada("t2")
    else:
        rodada("pub")

    if modal_titulo_visivel(page, "balancete"):
        print("    Fechando modal apos publicacao...")
        fechar_modal(page, "balancete")

    time.sleep(0.14)
    print("    Concluido.")


def _preencher_tipo_balanco_rel(page, modal_root, tipo_ui):
    scope = modal_root if modal_root is not None else page
    if modal_root is not None:
        try:
            selects = modal_root.locator("select")
            n = selects.count()
            for i in range(n):
                sel = selects.nth(i)
                try:
                    sel.wait_for(state="attached", timeout=3000)
                except Exception:
                    continue
                try:
                    sel.select_option(label=tipo_ui, timeout=4000)
                    print("    Tipo (select): {}".format(tipo_ui))
                    return
                except Exception:
                    pass
                try:
                    sel.select_option(
                        label=re.compile(re.escape(tipo_ui), re.I),
                        timeout=3500,
                    )
                    print("    Tipo (select regex): {}".format(tipo_ui))
                    return
                except Exception:
                    pass
        except Exception:
            pass

    for lb in LABELS_TIPO_BALANCO_REL:
        try:
            loc = scope.get_by_label(lb, exact=False).first
            loc.wait_for(state="visible", timeout=4000)
            if loc.evaluate("el => el.tagName") == "SELECT":
                loc.select_option(label=tipo_ui, timeout=4000)
                print("    Tipo (native SELECT): {}".format(tipo_ui))
                return
            loc.click()
            time.sleep(0.28)
            opt = page.get_by_text(tipo_ui, exact=True).last
            opt.wait_for(state="visible", timeout=5000)
            opt.click()
            print("    Tipo (lista Bubble): {}".format(tipo_ui))
            return
        except Exception:
            continue

    raise Exception("Campo Tipo (Balanco e Relatorios Anuais) nao encontrado")


def _preencher_descricao_balanco_rel(page, modal_root, texto):
    if not (texto or "").strip():
        print("    [INFO] Descricao vazia — campo opcional omitido.")
        return
    scope = modal_root if modal_root is not None else page
    tx = texto.strip()
    if _fill_by_label_candidates(scope, LABELS_DESCRICAO_BALANCO_REL, tx, page):
        print("    Descricao preenchida.")
        return
    try:
        loc = scope.get_by_placeholder(re.compile(r"balan", re.I)).first
        loc.wait_for(state="visible", timeout=4000)
        preencher_campo(page, loc, tx)
        print("    Descricao preenchida (placeholder).")
        return
    except Exception:
        pass
    print("    [AVISO] Campo Descricao nao encontrado — segue sem.")


def preencher_modal_balanco_rel_anuais(page, meta, pdf_path):
    modal_root = _modal_bubble_publicacao(page, "balanco_rel")
    _preencher_tipo_balanco_rel(page, modal_root, meta["tipo_ui"])
    time.sleep(0.06)
    _preencher_ano(page, meta["ano"], modal_root=modal_root)
    time.sleep(0.06)
    _preencher_descricao_balanco_rel(page, modal_root, meta.get("descricao", ""))
    try:
        page.keyboard.press("Tab")
    except Exception:
        pass
    time.sleep(0.12)

    if not fazer_upload(page, pdf_path, modal_root=modal_root):
        raise Exception("Upload falhou")

    nome_pdf_lower = pdf_path.name.lower()
    print("    Aguardando confirmacao do upload...")
    for _ in range(MAX_TENTATIVAS_POLL_UPLOAD):
        try:
            if modal_root is not None:
                area = modal_root.locator(".file-input-text").first
            else:
                area = page.locator(".file-input-text").first
            txt = area.inner_text().strip()
            tl = txt.lower()
            if nome_pdf_lower and nome_pdf_lower in tl:
                print("    Upload confirmado (arquivo na UI).")
                break
            if len(txt) > 5 and "clique aqui" not in tl:
                print("    Upload confirmado: '{}'".format(txt[:50]))
                break
        except Exception:
            pass
        time.sleep(PAUSA_POLL_UPLOAD_UI)

    time.sleep(PAUSA_APOS_CONFIRMAR_UPLOAD)


def publicar_um_balanco_rel_anuais(page, pdf_path, meta):
    nome_base = normalizar(pdf_path.stem.replace(" ", "_"))

    def rodada(prefixo_shot):
        abrir_modal(page, "balanco_rel")
        preencher_modal_balanco_rel_anuais(page, meta, pdf_path)
        salvar_screenshot(
            page, "{}_antes_balanco_rel_{}".format(prefixo_shot, nome_base)
        )
        clicar_publicar(page, "balanco_rel")
        salvar_screenshot(
            page, "{}_apos_balanco_rel_{}".format(prefixo_shot, nome_base)
        )

    if PUBLICAR_DUPLO_BUBBLE:
        print("    [1/2] Balanco/Relatorios Anuais — workaround duplo...")
        rodada("t1")
        fechar_modal(page, "balanco_rel")
        time.sleep(0.28)
        rodada("t2")
    else:
        rodada("pub")

    if modal_titulo_visivel(page, "balanco_rel"):
        print("    Fechando modal apos publicacao...")
        fechar_modal(page, "balanco_rel")

    time.sleep(0.14)
    print("    Concluido.")


def credenciais_portal_configuradas():
    u = (PORTAL_USUARIO or "").strip()
    s = (PORTAL_SENHA or "").strip()
    return bool(u and s)


def _resolver_escopo_login(page):
    """
    Bubble demora a hidratar o formulario; as vezes inputs ficam em iframe.
    Retorna Page ou Frame onde aparece input[type=password] visivel.
    """
    ultimo = None
    for _ in range(50):
        ordem = [page]
        try:
            mf = page.main_frame
            for fr in page.frames:
                if fr != mf:
                    ordem.append(fr)
        except Exception:
            ordem.extend([f for f in page.frames if f not in ordem])

        for scope in ordem:
            try:
                scope.locator("input[type='password']").first.wait_for(
                    state="visible",
                    timeout=300,
                )
                return scope
            except Exception as e:
                ultimo = e
                continue
        time.sleep(0.08)
    raise TimeoutError(
        "Formulario de login nao ficou pronto (campo senha invisivel). Ultimo: {}".format(
            ultimo
        )
    )


def login_automatico_portal(page):
    """Preenche usuario/senha na tela 'Acesso ao Portal CR2' (Bubble) e envia."""
    usuario = PORTAL_USUARIO.strip()
    senha = PORTAL_SENHA.strip()

    scope = _resolver_escopo_login(page)

    # Rotulos reais da tela CR2 (podem vir com dois-pontos ou espacos no Bubble).
    rotulos_email_cr2 = (
        re.compile(r"informe seu e-?\s*mail\s*:?", re.I),
        re.compile(r"^\s*informe seu e-?\s*mail", re.I),
        re.compile(r"seu e-?\s*mail", re.I),
    )
    rotulos_senha_cr2 = (
        re.compile(r"informe sua senha\s*:?", re.I),
        re.compile(r"^\s*informe sua senha", re.I),
        re.compile(r"sua senha", re.I),
    )

    preenchido_usuario = False
    for rx in rotulos_email_cr2:
        try:
            loc = scope.get_by_label(rx).first
            loc.wait_for(state="visible", timeout=3500)
            preencher_campo_rapido(page, loc, usuario)
            preenchido_usuario = True
            print("[INFO] Login: e-mail via rotulo Portal CR2.")
            break
        except Exception:
            continue

    if not preenchido_usuario:
        for label in (
            "Email",
            "E-mail",
            "Usuário",
            "Usuario",
            "Login",
            "User",
        ):
            try:
                loc = scope.get_by_label(
                    re.compile("^" + re.escape(label) + "$", re.I)
                ).first
                loc.wait_for(state="visible", timeout=2000)
                preencher_campo_rapido(page, loc, usuario)
                preenchido_usuario = True
                print("[INFO] Login: campo usuario via rotulo '{}'.".format(label))
                break
            except Exception:
                continue

    if not preenchido_usuario:
        candidatos_user = [
            scope.get_by_placeholder(
                re.compile(
                    r"gmail|meucontato|e-?\s*mail|@\.",
                    re.I,
                )
            ),
            scope.locator("input[type='email']"),
            scope.get_by_placeholder(
                re.compile(
                    r"e\s*-?\s*mail|correio|usu[aá]rio|login|user|account",
                    re.I,
                )
            ),
            scope.locator("input[autocomplete='username']"),
            scope.locator("input[autocomplete='email']"),
            scope.locator("input[name*='email' i]"),
            scope.locator("input[type='text']"),
        ]
        for loc in candidatos_user:
            alvo = loc.first
            try:
                alvo.wait_for(state="visible", timeout=4500)
                preencher_campo_rapido(page, alvo, usuario)
                preenchido_usuario = True
                print("[INFO] Login: campo usuario preenchido (placeholder/outro).")
                break
            except Exception:
                continue

    if not preenchido_usuario:
        raise RuntimeError("Nao foi possivel localizar o campo de usuario/email")

    preenchido_senha = False
    for rx in rotulos_senha_cr2:
        try:
            loc = scope.get_by_label(rx).first
            loc.wait_for(state="visible", timeout=4000)
            preencher_campo_rapido(page, loc, senha)
            preenchido_senha = True
            print("[INFO] Login: senha via rotulo Portal CR2.")
            break
        except Exception:
            continue

    if not preenchido_senha:
        campo_senha = scope.locator("input[type='password']").first
        campo_senha.wait_for(state="visible", timeout=10000)
        preencher_campo_rapido(page, campo_senha, senha)

    time.sleep(0.07)

    clicou = False
    txt_botao = (PORTAL_LOGIN_BOTAO or "").strip()
    if txt_botao:
        try:
            b = scope.get_by_role(
                "button",
                name=re.compile(re.escape(txt_botao), re.I),
            ).first
            b.wait_for(state="visible", timeout=6000)
            b.click(force=True)
            clicou = True
            print("[INFO] Login: clique no botao configurado em PORTAL_LOGIN_BOTAO.")
        except Exception:
            try:
                b = scope.locator("div[role='button']").filter(
                    has_text=re.compile(re.escape(txt_botao), re.I)
                ).first
                b.wait_for(state="visible", timeout=4000)
                b.click(force=True)
                clicou = True
                print("[INFO] Login: clique (div) PORTAL_LOGIN_BOTAO.")
            except Exception:
                pass

    if not clicou:
        # Botao principal do CR2: "Acessar"
        for rotulo in (
            "Acessar",
            "Entrar",
            "Login",
            "Sign in",
            "Continuar",
            "Log in",
            "Entrar na conta",
            "Acessar conta",
        ):
            loc_btn = scope.get_by_role(
                "button", name=re.compile(re.escape(rotulo), re.I)
            ).first
            try:
                loc_btn.wait_for(state="visible", timeout=2200)
                loc_btn.click(force=True)
                clicou = True
                print("[INFO] Login: clique em '{}'.".format(rotulo))
                break
            except Exception:
                try:
                    alt = scope.locator(
                        "button:has-text('{}'), div[role='button']:has-text('{}')".format(
                            rotulo,
                            rotulo,
                        )
                    ).first
                    alt.wait_for(state="visible", timeout=1800)
                    alt.click(force=True)
                    clicou = True
                    print("[INFO] Login: clique (fallback) em '{}'.".format(rotulo))
                    break
                except Exception:
                    continue

    if not clicou:
        sub = scope.locator(
            "button[type='submit'], input[type='submit']"
        ).first
        sub.wait_for(state="visible", timeout=6000)
        sub.click(force=True)
        print("[INFO] Login: clique em submit generico.")


def aguardar_barra_carregamento_topo(page, timeout_s=None, etiqueta=""):
    """
    Espera a barra fina no topo sumir (Bubble costuma usar NProgress; Turbo usa .turbo-progress-bar).
    Retorna logo se nenhuma barra for detectada em atividade.
    """
    if timeout_s is None:
        timeout_s = TIMEOUT_LOADER_TOPO_S
    tag = " [{}]".format(etiqueta) if etiqueta else ""
    limite = time.monotonic() + float(timeout_s)
    viu_barra = False
    js_topo = """
        () => {
            function barraTopoAtiva(el) {
                if (!el) return false;
                var s = window.getComputedStyle(el);
                if (s.display === 'none' || parseFloat(s.opacity) < 0.08) return false;
                var r = el.getBoundingClientRect();
                if (r.top > 22 || r.height > 28) return false;
                return r.width > 12;
            }
            var np = document.querySelector('#nprogress .bar');
            if (barraTopoAtiva(np)) return true;
            var turbo = document.querySelector('.turbo-progress-bar');
            if (barraTopoAtiva(turbo)) return true;
            return false;
        }
    """
    while time.monotonic() < limite:
        try:
            ativo = page.evaluate(js_topo)
        except Exception:
            ativo = False
        if ativo:
            if not viu_barra:
                print("[INFO] Aguardando barra de progresso no topo sumir{}...".format(tag))
                viu_barra = True
            time.sleep(0.14)
            continue
        if viu_barra:
            print("[INFO] Barra de progresso no topo concluida{}.".format(tag))
        return

    raise TimeoutError(
        "Barra de progresso no topo ainda ativa apos {}s{}. "
        "Verifique rede ou aumente TIMEOUT_LOADER_TOPO_S no CONFIG.".format(timeout_s, tag)
    )


def navegar_para_url(page, url, etiqueta, pausa_apos_carregar=1.0):
    """
    Carrega URL sem esperar networkidle (SPAs Bubble quase nunca param de rede).
    """
    print("[INFO] Carregando {}...".format(etiqueta))
    ultimo = None
    for wt in ("domcontentloaded", "load"):
        try:
            page.goto(url, wait_until=wt, timeout=120000)
            ultimo = None
            break
        except Exception as e:
            ultimo = e
    if ultimo:
        raise ultimo
    time.sleep(pausa_apos_carregar)


def garantir_pagina_portal(page, url_alvo, etiqueta_log):
    """Abre URL da área administrativa e espera o botão Criar Publicação."""
    navegar_para_url(
        page,
        url_alvo,
        etiqueta_log,
        pausa_apos_carregar=0.52,
    )

    path = (urlparse(url_alvo).path or "").strip("/")
    slug_esperado = path.split("/")[-1] if path else ""

    if slug_esperado and slug_esperado not in page.url:
        print(
            "[AVISO] Endereco pode nao bater com o esperado (slug {}). Forçando URL.".format(
                slug_esperado
            )
        )
        try:
            page.evaluate("(u) => { window.location.href = u; }", url_alvo)
            page.wait_for_load_state("domcontentloaded", timeout=120000)
        except Exception:
            page.goto(url_alvo, wait_until="domcontentloaded", timeout=120000)
        time.sleep(0.22)

    print("[INFO] URL atual: {}".format(page.url))

    try:
        page.locator("button:has-text('Criar Publicação')").wait_for(
            state="visible",
            timeout=45000,
        )
        print("[INFO] Pagina carregada (botao Criar Publicacao visivel).")
        aguardar_barra_carregamento_topo(page, etiqueta=etiqueta_log)
    except Exception as e:
        print(
            "[AVISO] Botao 'Criar Publicacao' nao apareceu. Verifique login e o link. ({})".format(
                str(e)[:120]
            )
        )


def aguardar_login_usuario(page, pular_enter=False):
    """Abre URL_LOGIN; login manual ou automatico; segue para o RGF depois."""
    navegar_para_url(
        page,
        URL_LOGIN,
        "login — {}".format(URL_LOGIN),
        pausa_apos_carregar=0.12,
    )
    print("[INFO] Pagina de login aberta: {}".format(URL_LOGIN))

    if credenciais_portal_configuradas():
        print("[INFO] Tentando login automatico (usuario preenchido no CONFIG)...")
        try:
            login_automatico_portal(page)
            print("[INFO] Formulario de login enviado.")
            time.sleep(0.52)
        except Exception as e:
            print(
                "[AVISO] Login automatico falhou ({}). Use o navegador.".format(
                    str(e)[:160]
                )
            )
    else:
        print(
            "[INFO] Login automatico desligado: preencha PORTAL_USUARIO e PORTAL_SENHA\n"
            "      no topo deste script, ou faça login manualmente no Opera."
        )

    msg = (
        "[INFO] Quando estiver logado no portal (ja pode ter ido para outra pagina), "
        "pressione Enter aqui para abrir o RGF...\n>>> "
    )
    if pular_enter:
        seg = 1.25
        print(
            "[INFO] Confirmacao automatica: aguardando {}s e abrindo o RGF (--yes).".format(
                seg
            )
        )
        time.sleep(seg)
    else:
        try:
            input(msg)
        except EOFError:
            seg = 10
            print(
                "[INFO] Sem terminal interativo: aguardando {}s e abrindo o RGF.".format(
                    seg
                )
            )
            time.sleep(seg)


def verificar_playwright_instalado():
    """Garante playwright (instala/reinicia com venv) ou encerra com instrucao."""
    if sync_playwright is not None:
        return
    garantir_playwright_pronto()
    if sync_playwright is not None:
        return
    venv_py = _python_venv_do_projeto()
    print("\n[ERRO] Playwright ainda indisponivel.")
    print("       Python usado agora: {}".format(sys.executable))
    print("\n       Tente no terminal (pasta automacoes):")
    print('       "{}" -m pip install playwright'.format(sys.executable))
    if venv_py.is_file():
        print('       ou: "{}" "{}"'.format(venv_py, Path(__file__).name))
    print("\n       No Cursor: Python: Select Interpreter -> venv\\Scripts\\python.exe")
    sys.exit(1)


def criar_navegador_e_login(pular_enter_pos_login=False):
    """Abre Opera + login. Nao navega para RGF/Balancete."""
    verificar_playwright_instalado()

    opera_path = resolver_caminho_opera()
    if opera_path is None:
        print(
            "\n[ERRO] Opera (opera.exe) nao encontrado neste PC.\n"
            "      Instale o Opera ou defina OPERA_EXE no script com o caminho completo."
        )
        sys.exit(1)

    pw = sync_playwright().start()
    print("\n[INFO] Abrindo Opera: {}".format(opera_path))
    try:
        browser = pw.chromium.launch(
            executable_path=str(opera_path),
            headless=HEADLESS,
        )
    except Exception as e:
        print("\n[ERRO] Falha ao iniciar Opera: {}".format(e))
        print(
            "      Confira se o Playwright esta ok: python -m playwright install chromium"
        )
        pw.stop()
        sys.exit(1)

    context = browser.new_context()
    page = context.new_page()
    if ABRIR_LOGIN_ANTES_DO_PORTAL:
        aguardar_login_usuario(page, pular_enter=pular_enter_pos_login)
    return pw, browser, page


def abrir_navegador(pular_enter_pos_login=False):
    """Login + pagina RGF (uso isolado / --analise). Exige URL_PORTAL_RGF."""
    pw, browser, page = criar_navegador_e_login(pular_enter_pos_login)
    if not url_portal_ativa(URL_PORTAL_RGF):
        print("[ERRO] URL_PORTAL_RGF vazio — configure o link ou use a execucao central.")
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass
        sys.exit(1)
    garantir_pagina_portal(
        page,
        URL_PORTAL_RGF,
        "RGF — {}".format(URL_PORTAL_RGF),
    )
    time.sleep(0.28)
    return pw, browser, page


def analisar_popup_criar_publicacao(page):
    """
    Abre o fluxo 'Criar Publicação', captura screenshot e extrai estrutura do popup
    (inputs, labels, botoes, trecho HTML) para arquivo JSON — util para ajustar seletores.
    """
    marca = time.strftime("%Y%m%d_%H%M%S")
    PASTA_SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    print("[INFO] ABRINDO POPUP 'Criar Publicação' para escaneamento...")
    try:
        abrir_modal(page, "rgf")
    except Exception as e:
        print("[ERRO] Nao foi possivel abrir o modal: {}".format(str(e)[:200]))
        salvar_screenshot(page, "analise_ERRO_modal_{}".format(marca))
        raise

    salvar_screenshot(page, "analise_popup_rgf_{}_pagina".format(marca))

    dados = page.evaluate(
        """
        () => {
            function vis(el) {
                try {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                } catch (e) {
                    return false;
                }
            }
            const out = {
                url: location.href,
                title: document.title,
                dialogs: [],
                bubbleGroups: [],
            };

            document.querySelectorAll('[role="dialog"]').forEach(function (d, i) {
                const rect = d.getBoundingClientRect();
                const inputs = Array.from(d.querySelectorAll("input")).map(
                    function (inp) {
                        return {
                            type: inp.type || "",
                            placeholder: inp.placeholder || "",
                            name: inp.name || "",
                            id: inp.id || "",
                            maxlength: inp.maxLength > 0 ? String(inp.maxLength) : "",
                            autocomplete: inp.autocomplete || "",
                            visible: vis(inp),
                            ariaLabel: inp.getAttribute("aria-label") || "",
                        };
                    }
                );
                const selects = Array.from(d.querySelectorAll("select")).map(
                    function (s) {
                        return {
                            id: s.id || "",
                            name: s.name || "",
                            options: Array.from(s.options).map(function (o) {
                                return { text: o.text, value: o.value };
                            }),
                        };
                    }
                );
                const btns = Array.from(
                    d.querySelectorAll("button, [role='button']")
                ).map(function (b) {
                    return {
                        text: (b.innerText || "").trim().slice(0, 160),
                        role: b.getAttribute("role") || "button",
                    };
                });
                const labels = Array.from(d.querySelectorAll("label")).map(
                    function (l) {
                        return {
                            text: (l.innerText || "").trim().slice(0, 240),
                            htmlFor: l.htmlFor || "",
                        };
                    }
                );
                out.dialogs.push({
                    index: i,
                    className: d.className || "",
                    rect: { w: rect.width, h: rect.height },
                    innerHTML_snippet: (d.innerHTML || "").slice(0, 14000),
                    inputs: inputs,
                    selects: selects,
                    buttons: btns,
                    labels: labels,
                });
            });

            Array.from(
                document.querySelectorAll(".bubble-element.Group, [class*='Floating']")
            ).forEach(function (d, i) {
                if (i > 25) return;
                const preview = (d.innerText || "").slice(0, 120);
                if (
                    preview.indexOf("Criar Relat") >= 0 ||
                    preview.indexOf("Ano") >= 0 ||
                    preview.indexOf("Refer") >= 0
                ) {
                    const inputs = Array.from(d.querySelectorAll("input")).map(
                        function (inp) {
                            return {
                                type: inp.type || "",
                                placeholder: inp.placeholder || "",
                                visible: vis(inp),
                            };
                        }
                    );
                    out.bubbleGroups.push({
                        index: i,
                        textPreview: preview,
                        inputs: inputs,
                        snippet: (d.innerHTML || "").slice(0, 8000),
                    });
                }
            });

            return out;
        }
        """
    )

    caminho_json = PASTA_SCREENSHOTS / "analise_popup_rgf_{}.json".format(marca)
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    print("[INFO] Escaneamento concluido.")
    print("       JSON : {}".format(caminho_json))
    print(
        "       PNG  : {}".format(
            PASTA_SCREENSHOTS / "analise_popup_rgf_{}_pagina.png".format(marca)
        )
    )
    print(
        "[INFO] Revise 'dialogs' e 'bubbleGroups' no JSON; "
        "innerHTML_snippet mostra o markup real do Bubble."
    )


def rodar_analise_popup():
    pw = None
    browser = None
    try:
        pw, browser, page = abrir_navegador()
        analisar_popup_criar_publicacao(page)
        print(
            "\n[INFO] Popup aberto no navegador para voce inspecionar manualmente "
            "(DevTools: F12)."
        )
        try:
            input("\n[INFO] Enter aqui para fechar o Opera e encerrar...\n>>> ")
        except EOFError:
            print("[INFO] Sem stdin: aguardando 20s antes de fechar...")
            time.sleep(20)
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass


def publicar_filas_combinadas(
    pdfs_rgf,
    pdfs_balancete,
    pdfs_balanco_rel_anuais=None,
    pdfs_rreo=None,
    pular_enter_pos_login=False,
):
    """Uma sessao: login, depois RGF, RREO, Balancete e/ou Balanco/Rel. Anuais."""
    if pdfs_balanco_rel_anuais is None:
        pdfs_balanco_rel_anuais = []
    if pdfs_rreo is None:
        pdfs_rreo = []

    verificar_playwright_instalado()

    pw = None
    browser = None
    ok = 0
    erros = []
    url_corrente = None

    try:
        pw, browser, page = criar_navegador_e_login(
            pular_enter_pos_login=pular_enter_pos_login
        )

        def navegar_se_preciso(url, etiqueta):
            nonlocal url_corrente
            if not url_portal_ativa(url):
                return False
            if url_corrente != url:
                garantir_pagina_portal(page, url, etiqueta)
                url_corrente = url
            return True

        if pdfs_rgf:
            navegar_se_preciso(URL_PORTAL_RGF, "RGF — {}".format(URL_PORTAL_RGF))

            for pdf_path in pdfs_rgf:
                _abortar_se_cancelado()
                meta = extrair_meta_rgf(pdf_path)
                if meta is None:
                    print(
                        "\n[AVISO] Meta RGF nao detectada: {} - pulando.".format(
                            pdf_path.name
                        )
                    )
                    erros.append((pdf_path.name, "meta nao detectada RGF"))
                    continue

                nome_base = normalizar(pdf_path.stem.replace(" ", "_"))
                print("\n[-> RGF] {}".format(pdf_path))
                ref = "{} {}".format(
                    meta.get("referencia_tipo", "quadrimestre"),
                    meta["referencia_num"],
                )
                print(
                    "     Ano: {} | Ref: {} | Nome: {}".format(
                        meta["ano"],
                        ref,
                        meta["nome_documento"],
                    )
                )

                try:
                    publicar_um(page, pdf_path, meta)
                    ok += 1
                    print("    [OK] Publicado!")
                except PWTimeout as e:
                    msg = "Timeout: {}".format(str(e)[:150])
                    print("    [ERRO] {}".format(msg))
                    erros.append((pdf_path.name, msg))
                    salvar_screenshot(page, "ERRO_RGF_{}".format(nome_base))
                    try:
                        fechar_modal(page, "rgf")
                    except Exception:
                        pass
                except Exception as e:
                    msg = str(e)[:150]
                    print("    [ERRO] {}".format(msg))
                    erros.append((pdf_path.name, msg))
                    salvar_screenshot(page, "ERRO_RGF_{}".format(nome_base))
                    try:
                        fechar_modal(page, "rgf")
                    except Exception:
                        pass

        if pdfs_rreo:
            navegar_se_preciso(URL_PORTAL_RREO, "RREO — {}".format(URL_PORTAL_RREO))

            for pdf_path in pdfs_rreo:
                _abortar_se_cancelado()
                meta = extrair_meta_rreo(pdf_path)
                if meta is None:
                    print(
                        "\n[AVISO] Meta RREO nao detectada: {} - pulando.".format(
                            pdf_path.name
                        )
                    )
                    erros.append((pdf_path.name, "meta nao detectada RREO"))
                    continue

                nome_base = normalizar(pdf_path.stem.replace(" ", "_"))
                print("\n[-> RREO] {}".format(pdf_path))
                ref = "{} {}".format(
                    meta.get("referencia_tipo", "quadrimestre"),
                    meta["referencia_num"],
                )
                print(
                    "     Ano: {} | Ref: {} | Nome: {}".format(
                        meta["ano"],
                        ref,
                        meta["nome_documento"],
                    )
                )

                try:
                    publicar_um_rreo(page, pdf_path, meta)
                    ok += 1
                    print("    [OK] Publicado!")
                except PWTimeout as e:
                    msg = "Timeout: {}".format(str(e)[:150])
                    print("    [ERRO] {}".format(msg))
                    erros.append((pdf_path.name, msg))
                    salvar_screenshot(page, "ERRO_RREO_{}".format(nome_base))
                    try:
                        fechar_modal(page, "rreo")
                    except Exception:
                        pass
                except Exception as e:
                    msg = str(e)[:150]
                    print("    [ERRO] {}".format(msg))
                    erros.append((pdf_path.name, msg))
                    salvar_screenshot(page, "ERRO_RREO_{}".format(nome_base))
                    try:
                        fechar_modal(page, "rreo")
                    except Exception:
                        pass

        if pdfs_balancete:
            navegar_se_preciso(
                URL_PORTAL_BALANCETE,
                "Balancete — {}".format(URL_PORTAL_BALANCETE),
            )

            for pdf_path in pdfs_balancete:
                _abortar_se_cancelado()
                meta = extrair_meta_balancete(pdf_path)
                if meta is None:
                    print(
                        "\n[AVISO] Meta Balancete nao detectada (pasta Mes-Ano?): {} — pulando.".format(
                            pdf_path.name
                        )
                    )
                    erros.append((pdf_path.name, "meta nao detectada Balancete"))
                    continue

                nome_base = normalizar(pdf_path.stem.replace(" ", "_"))
                print("\n[-> Balancete] {}".format(pdf_path))
                print(
                    "     Mes/Ano: {} | Nome: {}".format(
                        meta["mes_ano_ui"],
                        meta["nome_documento"],
                    )
                )

                try:
                    publicar_um_balancete(page, pdf_path, meta)
                    ok += 1
                    print("    [OK] Publicado!")
                except PWTimeout as e:
                    msg = "Timeout: {}".format(str(e)[:150])
                    print("    [ERRO] {}".format(msg))
                    erros.append((pdf_path.name, msg))
                    salvar_screenshot(page, "ERRO_BAL_{}".format(nome_base))
                    try:
                        fechar_modal(page, "balancete")
                    except Exception:
                        pass
                except Exception as e:
                    msg = str(e)[:150]
                    print("    [ERRO] {}".format(msg))
                    erros.append((pdf_path.name, msg))
                    salvar_screenshot(page, "ERRO_BAL_{}".format(nome_base))
                    try:
                        fechar_modal(page, "balancete")
                    except Exception:
                        pass

        if pdfs_balanco_rel_anuais:
            navegar_se_preciso(
                URL_PORTAL_BALANCO_REL_ANUAIS,
                "Balanco/Rel. Anuais — {}".format(URL_PORTAL_BALANCO_REL_ANUAIS),
            )

            for pdf_path in pdfs_balanco_rel_anuais:
                _abortar_se_cancelado()
                meta = extrair_meta_balanco_rel_anuais(pdf_path)
                if meta is None:
                    print(
                        "\n[AVISO] Meta Balanco/Rel. Anuais nao detectada (pasta Tipo-AAAA?): {} — pulando.".format(
                            pdf_path.name
                        )
                    )
                    erros.append(
                        (pdf_path.name, "meta nao detectada Balanco/Rel. Anuais")
                    )
                    continue

                nome_base = normalizar(pdf_path.stem.replace(" ", "_"))
                print("\n[-> Balanco/Rel. Anuais] {}".format(pdf_path))
                print(
                    "     Tipo: {} | Ano: {} | Desc.: {}".format(
                        meta["tipo_ui"],
                        meta["ano"],
                        (meta.get("descricao") or "")[:60],
                    )
                )

                try:
                    publicar_um_balanco_rel_anuais(page, pdf_path, meta)
                    ok += 1
                    print("    [OK] Publicado!")
                except PWTimeout as e:
                    msg = "Timeout: {}".format(str(e)[:150])
                    print("    [ERRO] {}".format(msg))
                    erros.append((pdf_path.name, msg))
                    salvar_screenshot(page, "ERRO_BRA_{}".format(nome_base))
                    try:
                        fechar_modal(page, "balanco_rel")
                    except Exception:
                        pass
                except Exception as e:
                    msg = str(e)[:150]
                    print("    [ERRO] {}".format(msg))
                    erros.append((pdf_path.name, msg))
                    salvar_screenshot(page, "ERRO_BRA_{}".format(nome_base))
                    try:
                        fechar_modal(page, "balanco_rel")
                    except Exception:
                        pass

        print("\n" + "=" * 50)
        print("  Publicados : {}".format(ok))
        print("  Erros      : {}".format(len(erros)))
        if erros:
            print("\n  Erros:")
            for nome, motivo in erros:
                print("    - {}: {}".format(nome, motivo))
        print("=" * 50)

    except Cancelado:
        print("\n[AVISO] Fila cancelada pelo usuario.")
        raise
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass


def _format_resumo_meta(pdf_path):
    meta = extrair_meta_rgf(pdf_path)
    if not meta:
        return "NAO DETECTADO - sera pulado"
    ref = "{} {}".format(
        meta.get("referencia_tipo", "quadrimestre"),
        meta["referencia_num"],
    )
    return "ano={} ref={} nome={}".format(
        meta["ano"],
        ref,
        meta["nome_documento"],
    )


def _format_resumo_rreo(pdf_path):
    return _format_resumo_meta(pdf_path)


def _format_resumo_balancete(pdf_path):
    meta = extrair_meta_balancete(pdf_path)
    if not meta:
        return "NAO DETECTADO - sera pulado (pasta Mes-Ano ex.: Janeiro-2021)"
    grp = meta.get("balancete_grupo")
    sufixo = " grupo={}".format(grp) if grp else ""
    return "mes_ano={} nome={}{}".format(
        meta["mes_ano_ui"], meta["nome_documento"], sufixo
    )


def _format_resumo_balanco_rel_anuais(pdf_path):
    meta = extrair_meta_balanco_rel_anuais(pdf_path)
    if not meta:
        return (
            "NAO DETECTADO - pasta ex.: Relatorio-Gestao-2024 ou Relatorio de Gestao/2024/"
        )
    return "tipo={} ano={} nome={}".format(
        meta["tipo_ui"],
        meta["ano"],
        meta["nome_documento"],
    )


def _ano_filtro_linha_comando():
    """Retorna ex. '2017' se veio --ano 2017 ou -a 2017."""
    for i, a in enumerate(sys.argv):
        if a in ("--ano", "-a") and i + 1 < len(sys.argv):
            v = sys.argv[i + 1].strip()
            if v and not v.startswith("-"):
                return v
    return None


if __name__ == "__main__":
    # Antes da fila: corrige Python do IDE (ex. 3.13 Store) sem playwright.
    if sync_playwright is None and "--help" not in sys.argv and "-h" not in sys.argv:
        garantir_playwright_pronto()

    if "--help" in sys.argv or "-h" in sys.argv:
        print(
            "Uso: python \"Publicação - RGF, RREO, Balanço e Balancete.py\" [opcoes]\n\n"
            "  Central CR2: preencha URL_PORTAL_RGF, URL_PORTAL_RREO, URL_PORTAL_BALANCETE e/ou\n"
            "  URL_PORTAL_BALANCO_REL_ANUAIS no CONFIG. Link vazio = tipo DESLIGADO.\n\n"
            "  --test, -t           No max. 1 PDF por fila habilitada.\n"
            "  --ano ANO, -a ANO    So subpasta ANO em PASTA_RGF e PASTA_RREO.\n"
            "  --todos              Todos os anos em RGF/RREO (ignora ANO_FILTRO).\n"
            "  --so-rgf             Apenas fila RGF.\n"
            "  --so-rreo            Apenas fila RREO.\n"
            "  --so-balancete       Apenas fila Balancete Financeiro.\n"
            "  --so-balanco-rel     Apenas fila Balanco e Relatorios Anuais.\n"
            "  --yes, -y            Pula confirmacoes + Enter pos-login (~1.25s).\n"
            "  --analise, --scan    Escaneia popup RGF (precisa URL_PORTAL_RGF).\n\n"
            "  Pastas: PASTA_RGF e PASTA_RREO (por ano, quadrimestre/semestre no nome);\n"
            "  PASTA_BALANCETE (Mes-Ano); "
            "PASTA_BALANCO_REL_ANUAIS: '<Tipo>-<AAAA>' ou '<Tipo>/<AAAA>/' (PDF dentro)."
        )
        sys.exit(0)

    if "--analise" in sys.argv or "--scan" in sys.argv:
        print("=" * 50)
        print("  Modo ANALISE — escaneamento do popup RGF")
        print("=" * 50)
        rodar_analise_popup()
        sys.exit(0)

    modo_teste = (
        MODO_TESTE
        or "--test" in sys.argv
        or "-t" in sys.argv
    )
    confirmar_automatico = "--yes" in sys.argv or "-y" in sys.argv
    ano_cli = _ano_filtro_linha_comando()
    if "--todos" in sys.argv:
        filtro_ano = None
    else:
        filtro_ano = ano_cli if ano_cli else ANO_FILTRO

    only_rgf = "--so-rgf" in sys.argv
    only_rreo = "--so-rreo" in sys.argv
    only_bal = "--so-balancete" in sys.argv
    only_bra = "--so-balanco-rel" in sys.argv
    if only_rgf and only_bal:
        print("[AVISO] --so-rgf e --so-balancete: mantendo apenas --so-rgf.")
        only_bal = False
    if only_rgf and only_bra:
        print("[AVISO] --so-rgf e --so-balanco-rel: mantendo apenas --so-rgf.")
        only_bra = False
    if only_rgf and only_rreo:
        print("[AVISO] --so-rgf e --so-rreo: mantendo apenas --so-rgf.")
        only_rreo = False
    if only_rreo and only_bal:
        print("[AVISO] --so-rreo e --so-balancete: mantendo apenas --so-rreo.")
        only_bal = False
    if only_rreo and only_bra:
        print("[AVISO] --so-rreo e --so-balanco-rel: mantendo apenas --so-rreo.")
        only_bra = False
    if only_bal and only_bra:
        print("[AVISO] --so-balancete e --so-balanco-rel: mantendo apenas --so-balancete.")
        only_bra = False

    exec_rgf = (
        url_portal_ativa(URL_PORTAL_RGF)
        and not only_bal
        and not only_bra
        and not only_rreo
    )
    exec_rreo = (
        url_portal_ativa(URL_PORTAL_RREO)
        and not only_rgf
        and not only_bal
        and not only_bra
    )
    exec_bal = (
        url_portal_ativa(URL_PORTAL_BALANCETE)
        and not only_rgf
        and not only_rreo
        and not only_bra
    )
    exec_bra = (
        url_portal_ativa(URL_PORTAL_BALANCO_REL_ANUAIS)
        and not only_rgf
        and not only_rreo
        and not only_bal
    )

    print("=" * 50)
    print("  Central CR2 (RGF + RREO + Balancete + Balanco/Rel. Anuais)")
    print("=" * 50)

    if exec_rgf:
        print("\n  [RGF] ATIVO — {}".format(URL_PORTAL_RGF[:72]))
    else:
        print(
            "\n  [RGF] pulado ({})".format(
                "URL vazia"
                if not url_portal_ativa(URL_PORTAL_RGF)
                else (
                    "--so-balancete"
                    if only_bal
                    else ("--so-balanco-rel" if only_bra else ("--so-rreo" if only_rreo else "?"))
                )
            )
        )

    if exec_rreo:
        print("  [RREO] ATIVO — {}".format(URL_PORTAL_RREO[:72]))
    else:
        print(
            "  [RREO] pulado ({})".format(
                "URL vazia"
                if not url_portal_ativa(URL_PORTAL_RREO)
                else (
                    "--so-rgf"
                    if only_rgf
                    else (
                        "--so-balancete"
                        if only_bal
                        else ("--so-balanco-rel" if only_bra else "?")
                    )
                )
            )
        )

    if exec_bal:
        print("  [Balancete] ATIVO — {}".format(URL_PORTAL_BALANCETE[:72]))
    else:
        print(
            "  [Balancete] pulado ({})".format(
                "URL vazia"
                if not url_portal_ativa(URL_PORTAL_BALANCETE)
                else ("--so-rgf" if only_rgf else ("--so-rreo" if only_rreo else "--so-balanco-rel"))
            )
        )

    if exec_bra:
        print(
            "  [Balanco/Rel. Anuais] ATIVO — {}".format(
                URL_PORTAL_BALANCO_REL_ANUAIS[:72]
            )
        )
    else:
        print(
            "  [Balanco/Rel. Anuais] pulado ({})".format(
                "URL vazia"
                if not url_portal_ativa(URL_PORTAL_BALANCO_REL_ANUAIS)
                else (
                    "--so-rgf"
                    if only_rgf
                    else ("--so-rreo" if only_rreo else "--so-balancete")
                )
            )
        )

    pdfs_rgf = []
    pdfs_rreo = []
    pdfs_bal = []
    pdfs_bra = []

    if modo_teste:
        print("\n  *** MODO TESTE — ate 1 PDF por fila habilitada ***\n")

    if exec_rgf:
        if filtro_ano:
            print("  *** RGF filtro pasta ano: {} ***".format(filtro_ano))
        else:
            print("  *** RGF: todos os PDFs sob {} ***".format(PASTA_RGF))
        pdfs_rgf = ordenar_fila_pdfs_rgf(listar_pdfs_rgf(PASTA_RGF, filtro_ano))
        if modo_teste and pdfs_rgf:
            pdfs_rgf = pdfs_rgf[:1]

    if exec_rreo:
        if filtro_ano:
            print("  *** RREO filtro pasta ano: {} ***".format(filtro_ano))
        else:
            print("  *** RREO: todos os PDFs sob {} ***".format(PASTA_RREO))
        pdfs_rreo = ordenar_fila_pdfs_rreo(listar_pdfs_rreo(PASTA_RREO, filtro_ano))
        if modo_teste and pdfs_rreo:
            pdfs_rreo = pdfs_rreo[:1]

    if exec_bal:
        print("\n  *** Balancete: PDFs sob {} ***".format(PASTA_BALANCETE))
        pdfs_bal = ordenar_fila_pdfs_balancete(listar_pdfs_balancete(PASTA_BALANCETE))
        if modo_teste and pdfs_bal:
            pdfs_bal = pdfs_bal[:1]

    if exec_bra:
        print(
            "\n  *** Balanco/Rel. Anuais: PDFs sob {} ***".format(
                PASTA_BALANCO_REL_ANUAIS
            )
        )
        pdfs_bra = ordenar_fila_pdfs_balanco_rel_anuais(
            listar_pdfs_balanco_rel_anuais(PASTA_BALANCO_REL_ANUAIS)
        )
        if modo_teste and pdfs_bra:
            pdfs_bra = pdfs_bra[:1]

    if not pdfs_rgf and not pdfs_rreo and not pdfs_bal and not pdfs_bra:
        print(
            "\n[INFO] Nenhuma fila para processar "
            "(URLs desligadas, pastas sem PDF, ou filtros).\n"
        )
        sys.exit(0)

    total_items = len(pdfs_rgf) + len(pdfs_rreo) + len(pdfs_bal) + len(pdfs_bra)
    print("\n{} item(ns) na fila total:\n".format(total_items))

    if pdfs_rgf:
        print("--- RGF ({} arquivo(s)) ---".format(len(pdfs_rgf)))
        for p in pdfs_rgf:
            print("  {}\n    -> {}".format(p, _format_resumo_meta(p)))
    if pdfs_rreo:
        print("--- RREO ({} arquivo(s)) ---".format(len(pdfs_rreo)))
        for p in pdfs_rreo:
            print("  {}\n    -> {}".format(p, _format_resumo_rreo(p)))
    if pdfs_bal:
        print("--- Balancete ({} arquivo(s)) ---".format(len(pdfs_bal)))
        for p in pdfs_bal:
            print("  {}\n    -> {}".format(p, _format_resumo_balancete(p)))
    if pdfs_bra:
        print(
            "--- Balanco/Relatorios Anuais ({} arquivo(s)) ---".format(len(pdfs_bra))
        )
        for p in pdfs_bra:
            print("  {}\n    -> {}".format(p, _format_resumo_balanco_rel_anuais(p)))

    print()
    if confirmar_automatico:
        resposta = "s"
        print(
            "[INFO] Confirmacao automatica (--yes): Prosseguir + Enter pos-login (~1.25s).\n"
        )
    else:
        try:
            resposta = input("Prosseguir? (s/n): ").strip().lower()
        except EOFError:
            print(
                "[INFO] Sem terminal interativo para responder. "
                "Rode com --yes ou use o terminal do Cursor.\n"
                "Encerrando."
            )
            sys.exit(0)
    if resposta != "s":
        sys.exit(0)

    verificar_playwright_instalado()

    if pdfs_rgf and not url_portal_ativa(URL_PORTAL_RGF):
        print("[ERRO] Inconsistencia: PDFs RGF mas URL_PORTAL_RGF vazio.")
        sys.exit(1)
    if pdfs_rreo and not url_portal_ativa(URL_PORTAL_RREO):
        print("[ERRO] Inconsistencia: PDFs RREO mas URL_PORTAL_RREO vazio.")
        sys.exit(1)
    if pdfs_bal and not url_portal_ativa(URL_PORTAL_BALANCETE):
        print("[ERRO] Inconsistencia: PDFs Balancete mas URL_PORTAL_BALANCETE vazio.")
        sys.exit(1)
    if pdfs_bra and not url_portal_ativa(URL_PORTAL_BALANCO_REL_ANUAIS):
        print("[ERRO] Inconsistencia: PDFs Balanco/Rel. Anuais mas URL vazio.")
        sys.exit(1)

    publicar_filas_combinadas(
        pdfs_rgf,
        pdfs_bal,
        pdfs_balanco_rel_anuais=pdfs_bra,
        pdfs_rreo=pdfs_rreo,
        pular_enter_pos_login=confirmar_automatico,
    )
