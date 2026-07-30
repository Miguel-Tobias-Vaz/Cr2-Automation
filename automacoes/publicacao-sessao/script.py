# =====================================================================
#  Publicação de Sessão — portal CR2 (Playwright / Bubble)
# =====================================================================
#
# Campos do modal:
#   Tipo *, Data *, Número *, Pauta, Ata, Lista de Presença,
#   Votações Nominais (arquivo), Votações Nominais (Link)
#
# Entrada (prioridade):
#   1) REGISTRO_UNICO (painel — 1 sessao)
#   2) PASTA_SESSOES — pastas filhas: "33ª Ordinária - 14-10-2021" com Pauta.pdf / Ata.pdf
#   3) CSV_FILA
#
# Flags: --test  --yes  --headless  --pasta CAMINHO  --csv CAMINHO

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
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


# ---------------------------------------------------------------------
#  CONFIG
# ---------------------------------------------------------------------

URL_LOGIN = "https://www.portalcr2.com.br/?view=login"
URL_PORTAL_SESSAO = ""  # ex.: https://www.portalcr2.com.br/sessoes/sessoes-entidade

PORTAL_USUARIO = ""
PORTAL_SENHA = ""

HEADLESS = False
MODO_TESTE = False
ABRIR_LOGIN_ANTES_DO_PORTAL = True
PORTAL_LOGIN_BOTAO = "Entrar"

CSV_FILA = Path(__file__).resolve().parent / "fila_sessoes.csv"
# Pasta com subpastas de sessao (ex.: ...\sessoes_2021\33ª Ordinária - 14-10-2021)
PASTA_SESSOES = Path(r"C:\Users\tobia\Documents\mds\missao_baixar_sessao\sessoes_2021")
# Preenchido pelo painel para 1 sessao avulsa (dict). None = usa pasta/CSV.
REGISTRO_UNICO = None

OPERA_EXE = None
PASTA_SCREENSHOTS = Path(__file__).resolve().parent / "screenshots_pub"

PAUSA_APOS_ANEXAR = 0.55
TIMEOUT_PUBLICAR_HABILITADO_S = 75
TIMEOUT_RESULTADO_PUBLICACAO_S = 55
TIMEOUT_LOADER_TOPO_S = 120
PAUSA_APOS_CLICAR_PUBLICAR = 1.5

MODAL_TITULO_REGEX = r"Criar.*Sess[aã]o"

LABELS_TIPO = ("Tipo",)
LABELS_DATA = ("Data", "Data da sessão", "Data da Sessão", "Data da sessao")
LABELS_NUMERO = ("Número", "Numero", "Nº", "N°", "Sessão", "Sessao")
LABELS_LINK_VOTACOES = (
    "Votações Nominais (Link)",
    "Votacoes Nominais (Link)",
    "Votações Nominais Link",
    "Link Votações Nominais",
    "Link",
)

UPLOADS = (
    ("pauta", ("Pauta",)),
    ("ata", ("Ata",)),
    ("presenca", ("Lista de Presença", "Lista de Presenca", "Presença", "Presenca")),
    (
        "votacoes_arquivo",
        (
            "Votações Nominais (arquivo)",
            "Votacoes Nominais (arquivo)",
            "Votações Nominais",
            "Votacoes Nominais",
        ),
    ),
)

_TEXTO_ERRO_APOS_PUBLICAR_RX = re.compile(
    r"(erro|falha|inv[aá]lid|obrigat[oó]rio|n[aã]o\s+foi\s+poss[ií]vel|"
    r"tente\s+novamente|j[aá]\s+existe|duplicad|\bduplicat)",
    re.I,
)
_TEXTO_SUCESSO_MODAL_RX = re.compile(
    r"(publicad|salvo\s+com\s+sucesso|cadastrad|registrad|enviad\s+com\s+sucesso)",
    re.I,
)


# ---------------------------------------------------------------------
#  Playwright / Opera
# ---------------------------------------------------------------------

def _recarregar_playwright():
    global PWTimeout, sync_playwright
    try:
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        PWTimeout = None
        sync_playwright = None
        return False


def _python_venv_do_projeto():
    # automacoes/venv ou centro-automacoes/venv
    aqui = Path(__file__).resolve().parent
    for cand in (
        aqui.parent / "venv" / "Scripts" / "python.exe",
        aqui.parent.parent / "centro-automacoes" / "venv" / "Scripts" / "python.exe",
    ):
        if cand.is_file():
            return cand
    return aqui.parent / "venv" / "Scripts" / "python.exe"


def garantir_playwright_pronto():
    if sync_playwright is not None:
        return
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "playwright"],
        check=False,
    )
    if _recarregar_playwright():
        return
    venv_py = _python_venv_do_projeto()
    if venv_py.is_file():
        subprocess.run([str(venv_py), "-m", "pip", "install", "playwright"], check=False)
        if Path(sys.executable).resolve() != venv_py.resolve():
            os.execv(str(venv_py), [str(venv_py)] + sys.argv)
        _recarregar_playwright()


def verificar_playwright_instalado():
    if sync_playwright is not None:
        return
    garantir_playwright_pronto()
    if sync_playwright is None:
        print("[ERRO] Playwright indisponivel. pip install playwright")
        sys.exit(1)


def _opera_via_program_files():
    local = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("PROGRAMFILES", "")
    prog_x86 = os.environ.get("PROGRAMFILES(X86)", "")
    for p in (
        Path(local) / "Programs" / "Opera" / "opera.exe",
        Path(local) / "Programs" / "Opera GX" / "opera.exe",
        Path(prog) / "Opera" / "opera.exe",
        Path(prog_x86) / "Opera" / "opera.exe",
    ):
        if p.is_file():
            return p.resolve()
    base = Path(local) / "Programs"
    if base.is_dir():
        for folder in sorted(base.glob("Opera*")):
            exe = folder / "opera.exe"
            if exe.is_file():
                return exe.resolve()
    return None


def resolver_caminho_opera():
    if OPERA_EXE:
        p = Path(OPERA_EXE)
        if p.is_file():
            return p.resolve()
    found = shutil.which("opera") or shutil.which("opera.exe")
    if found:
        return Path(found).resolve()
    return _opera_via_program_files()


# ---------------------------------------------------------------------
#  Utilitarios
# ---------------------------------------------------------------------

def normalizar(texto):
    nfd = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower().strip()


def url_portal_ativa(url):
    return bool((url or "").strip())


def salvar_screenshot(page, nome):
    try:
        PASTA_SCREENSHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(PASTA_SCREENSHOTS / "{}.png".format(nome)), full_page=True)
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
    try:
        locator.focus(timeout=4000)
    except Exception:
        locator.click(timeout=6000)
    locator.fill(valor, timeout=8000)


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


def _caminho_arquivo(valor):
    if not valor:
        return None
    p = Path(str(valor).strip().strip('"'))
    if not p.is_file():
        return None
    return p


# ---------------------------------------------------------------------
#  Leitura de fila
# ---------------------------------------------------------------------

CSV_COLS = (
    "tipo",
    "data",
    "numero",
    "pauta",
    "ata",
    "presenca",
    "votacoes_arquivo",
    "votacoes_link",
)


def _registro_vazio():
    return {k: "" for k in CSV_COLS}


_RE_PASTA_SESSAO = re.compile(
    r"^(?:(\d+\s*[ªºa°]?)\s+)?(.+?)\s*[-–—]\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\s*$",
    re.I,
)


def parse_nome_pasta_sessao(nome_pasta: str) -> dict:
    """
    '33ª Ordinária - 14-10-2021' -> tipo=Ordinária, data=14/10/2021, numero=33ª Sessão Ordinária
    'Ordinária - 11-05-2021'     -> tipo=Ordinária, data=11/05/2021, numero=Sessão Ordinária
    """
    nome = (nome_pasta or "").strip()
    item = _registro_vazio()
    m = _RE_PASTA_SESSAO.match(nome)
    if m:
        num_raw = (m.group(1) or "").strip()
        tipo = (m.group(2) or "").strip()
        d, mo, y = m.group(3), m.group(4), m.group(5)
        item["tipo"] = tipo
        item["data"] = "{:02d}/{:02d}/{}".format(int(d), int(mo), y)
        if num_raw:
            item["numero"] = "{} Sessão {}".format(num_raw, tipo).strip()
        else:
            item["numero"] = "Sessão {}".format(tipo).strip()
        return item
    # Fallback: usa o nome da pasta como numero/tipo
    item["tipo"] = nome
    item["numero"] = nome
    return item


def _achar_pdf_por_palavras(pasta: Path, palavras: tuple[str, ...], excluir: tuple[str, ...] = ()):
    if not pasta.is_dir():
        return ""
    candidatos = []
    for f in pasta.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".pdf", ".PDF"):
            continue
        stem = normalizar(f.stem)
        if any(ex in stem for ex in excluir if ex):
            continue
        if any(p in stem for p in palavras):
            candidatos.append(f)
    if not candidatos:
        return ""
    # Prefere nome exato (Pauta.pdf) depois o menor nome
    candidatos.sort(key=lambda p: (0 if normalizar(p.stem) in palavras else 1, len(p.name), p.name.lower()))
    return str(candidatos[0])


def arquivos_da_pasta_sessao(pasta: Path) -> dict:
    return {
        "pauta": _achar_pdf_por_palavras(pasta, ("pauta",)),
        "ata": _achar_pdf_por_palavras(pasta, ("ata",), excluir=("pauta",)),
        "presenca": _achar_pdf_por_palavras(
            pasta, ("presenca", "lista de presenca", "lista_presenca", "frequencia")
        ),
        "votacoes_arquivo": _achar_pdf_por_palavras(
            pasta, ("votac", "votacoes", "votacao")
        ),
    }


def ler_pasta_sessoes(pasta_base) -> list:
    """
    Cada subpasta = 1 sessao.
    Esperado: Pauta.pdf, Ata.pdf, eventualmente Presenca/Votacoes.
    """
    root = Path(pasta_base)
    if not root.is_dir():
        print("[AVISO] Pasta de sessoes nao encontrada: {}".format(root))
        return []
    itens = []
    subdirs = sorted(
        [p for p in root.iterdir() if p.is_dir()],
        key=lambda p: p.name.lower(),
    )
    for i, sub in enumerate(subdirs, start=1):
        item = parse_nome_pasta_sessao(sub.name)
        arquivos = arquivos_da_pasta_sessao(sub)
        item.update(arquivos)
        item["linha"] = i
        item["pasta"] = str(sub)
        if not item.get("data") and not item.get("tipo"):
            print("[AVISO] Ignorando pasta sem meta: {}".format(sub.name))
            continue
        if not any(arquivos.values()):
            print("[AVISO] Pasta sem PDF (Pauta/Ata/...): {}".format(sub.name))
        itens.append(item)
    print("[INFO] {} sessao(oes) na pasta {}".format(len(itens), root))
    return itens


def ler_csv_fila(caminho):
    path = Path(caminho)
    if not path.is_file():
        print("[AVISO] CSV nao encontrado: {}".format(path))
        return []
    itens = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(fh, delimiter=delim)
        for i, row in enumerate(reader, start=2):
            if not row:
                continue
            item = _registro_vazio()
            mapa = {normalizar(k): v for k, v in row.items() if k}
            aliases = {
                "tipo": ("tipo",),
                "data": ("data", "data da sessao"),
                "numero": ("numero", "nº", "n", "sessao"),
                "pauta": ("pauta",),
                "ata": ("ata",),
                "presenca": ("presenca", "lista de presenca", "lista_presenca"),
                "votacoes_arquivo": (
                    "votacoes_arquivo",
                    "votacoes nominais arquivo",
                    "votacoes",
                ),
                "votacoes_link": (
                    "votacoes_link",
                    "votacoes nominais link",
                    "link",
                ),
            }
            for dest, keys in aliases.items():
                for k in keys:
                    if k in mapa and mapa[k] is not None:
                        item[dest] = str(mapa[k]).strip()
                        break
            if not (item["tipo"] or item["data"] or item["numero"]):
                continue
            item["linha"] = i
            itens.append(item)
    return itens


def montar_fila():
    if isinstance(REGISTRO_UNICO, dict) and any(
        str(REGISTRO_UNICO.get(k) or "").strip() for k in ("tipo", "data", "numero")
    ):
        item = _registro_vazio()
        for k in CSV_COLS:
            item[k] = str(REGISTRO_UNICO.get(k) or "").strip()
        item["linha"] = 1
        return [item]

    pasta = Path(PASTA_SESSOES) if PASTA_SESSOES else None
    if pasta and pasta.is_dir():
        itens = ler_pasta_sessoes(pasta)
        if itens:
            return itens

    return ler_csv_fila(CSV_FILA)


# ---------------------------------------------------------------------
#  Login / navegacao
# ---------------------------------------------------------------------

def credenciais_portal_configuradas():
    return bool((PORTAL_USUARIO or "").strip() and (PORTAL_SENHA or "").strip())


def navegar_para_url(page, url, etiqueta, pausa_apos_carregar=0.5):
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


def aguardar_barra_carregamento_topo(page, timeout_s=None, etiqueta=""):
    if timeout_s is None:
        timeout_s = TIMEOUT_LOADER_TOPO_S
    tag = " [{}]".format(etiqueta) if etiqueta else ""
    limite = time.monotonic() + float(timeout_s)
    viu = False
    js = """
        () => {
            function ativa(el) {
                if (!el) return false;
                var s = window.getComputedStyle(el);
                if (s.display === 'none' || parseFloat(s.opacity) < 0.08) return false;
                var r = el.getBoundingClientRect();
                if (r.top > 22 || r.height > 28) return false;
                return r.width > 12;
            }
            if (ativa(document.querySelector('#nprogress .bar'))) return true;
            if (ativa(document.querySelector('.turbo-progress-bar'))) return true;
            return false;
        }
    """
    while time.monotonic() < limite:
        try:
            ativo = page.evaluate(js)
        except Exception:
            ativo = False
        if ativo:
            viu = True
            time.sleep(0.14)
            continue
        return
    if viu:
        raise TimeoutError("Barra de progresso ativa apos {}s{}.".format(timeout_s, tag))


def _resolver_escopo_login(page):
    ultimo = None
    for _ in range(50):
        ordem = [page]
        try:
            for fr in page.frames:
                if fr != page.main_frame:
                    ordem.append(fr)
        except Exception:
            pass
        for scope in ordem:
            try:
                scope.locator("input[type='password']").first.wait_for(
                    state="visible", timeout=300
                )
                return scope
            except Exception as e:
                ultimo = e
        time.sleep(0.08)
    raise TimeoutError("Formulario de login nao pronto: {}".format(ultimo))


def login_automatico_portal(page):
    usuario = PORTAL_USUARIO.strip()
    senha = PORTAL_SENHA.strip()
    scope = _resolver_escopo_login(page)

    preenchido = False
    for rx in (
        re.compile(r"informe seu e-?\s*mail\s*:?", re.I),
        re.compile(r"seu e-?\s*mail", re.I),
    ):
        try:
            loc = scope.get_by_label(rx).first
            loc.wait_for(state="visible", timeout=3500)
            preencher_campo_rapido(page, loc, usuario)
            preenchido = True
            break
        except Exception:
            continue
    if not preenchido:
        for sel in (
            "input[type='email']",
            "input[autocomplete='username']",
            "input[autocomplete='email']",
            "input[type='text']",
        ):
            try:
                loc = scope.locator(sel).first
                loc.wait_for(state="visible", timeout=2500)
                preencher_campo_rapido(page, loc, usuario)
                preenchido = True
                break
            except Exception:
                continue
    if not preenchido:
        raise RuntimeError("Campo de usuario/email nao encontrado")

    try:
        loc = scope.get_by_label(re.compile(r"informe sua senha", re.I)).first
        loc.wait_for(state="visible", timeout=3500)
        preencher_campo_rapido(page, loc, senha)
    except Exception:
        campo = scope.locator("input[type='password']").first
        campo.wait_for(state="visible", timeout=10000)
        preencher_campo_rapido(page, campo, senha)

    time.sleep(0.07)
    clicou = False
    for rotulo in (
        (PORTAL_LOGIN_BOTAO or "").strip(),
        "Acessar",
        "Entrar",
        "Login",
    ):
        if not rotulo:
            continue
        try:
            b = scope.get_by_role("button", name=re.compile(re.escape(rotulo), re.I)).first
            b.wait_for(state="visible", timeout=3500)
            b.click(force=True)
            clicou = True
            break
        except Exception:
            continue
    if not clicou:
        scope.locator("button[type='submit'], input[type='submit']").first.click(force=True)


def aguardar_login_usuario(page, pular_enter=False):
    navegar_para_url(page, URL_LOGIN, "login", 0.15)
    if credenciais_portal_configuradas():
        try:
            login_automatico_portal(page)
            print("[INFO] Formulario de login enviado.")
            time.sleep(0.55)
        except Exception as e:
            print("[AVISO] Login automatico falhou ({})".format(str(e)[:160]))
    if pular_enter:
        time.sleep(1.25)
    else:
        input("[INFO] Quando estiver logado, pressione Enter...\n>>> ")


def garantir_pagina_portal(page, url_alvo, etiqueta_log):
    navegar_para_url(page, url_alvo, etiqueta_log, 0.55)
    path = (urlparse(url_alvo).path or "").strip("/")
    slug = path.split("/")[-1] if path else ""
    if slug and slug not in page.url:
        try:
            page.goto(url_alvo, wait_until="domcontentloaded", timeout=120000)
        except Exception:
            pass
        time.sleep(0.25)
    print("[INFO] URL atual: {}".format(page.url))
    try:
        page.locator("button:has-text('Criar Publicação')").wait_for(
            state="visible", timeout=45000
        )
        print("[INFO] Botao Criar Publicacao visivel.")
        aguardar_barra_carregamento_topo(page, etiqueta=etiqueta_log)
    except Exception as e:
        print("[AVISO] Criar Publicacao nao apareceu: {}".format(str(e)[:120]))


def criar_navegador_e_login(pular_enter_pos_login=False):
    verificar_playwright_instalado()
    opera = resolver_caminho_opera()
    pw = sync_playwright().start()
    launch_kwargs = {"headless": HEADLESS}
    if opera:
        print("[INFO] Abrindo Opera: {}".format(opera))
        launch_kwargs["executable_path"] = str(opera)
    else:
        print("[INFO] Opera nao encontrado — usando Chromium do Playwright.")
    try:
        browser = pw.chromium.launch(**launch_kwargs)
    except Exception as e:
        print("[ERRO] Falha ao iniciar navegador: {}".format(e))
        pw.stop()
        sys.exit(1)
    page = browser.new_context().new_page()
    if ABRIR_LOGIN_ANTES_DO_PORTAL:
        aguardar_login_usuario(page, pular_enter=pular_enter_pos_login)
    return pw, browser, page


# ---------------------------------------------------------------------
#  Modal Sessao
# ---------------------------------------------------------------------

def _loc_modal_titulo(page):
    return page.locator("text=/{}/i".format(MODAL_TITULO_REGEX)).first


def abrir_modal(page):
    btn = page.locator("button:has-text('Criar Publicação')").first
    btn.wait_for(state="visible", timeout=15000)
    btn.scroll_into_view_if_needed()
    time.sleep(0.08)
    btn.click()
    time.sleep(0.3)
    try:
        _loc_modal_titulo(page).wait_for(state="visible", timeout=10000)
    except Exception:
        # Fallback: alguns temas so mostram "Criar Publicação" no botao / titulo generico
        page.locator("button:has-text('Publicar')").first.wait_for(
            state="visible", timeout=10000
        )
    time.sleep(0.15)


def _modal_bubble_sessao(page):
    try:
        page.evaluate(
            """
            () => {
                document.querySelectorAll('[data-cr2-pub-modal-marker]').forEach(function (el) {
                    el.removeAttribute('data-cr2-pub-modal-marker');
                });
                var pubs = Array.from(
                    document.querySelectorAll('button, div[role="button"], .bubble-element.Button')
                ).filter(function (b) {
                    var t = ((b.innerText || b.textContent || '') + '').trim();
                    return (t === 'Publicar' || t.indexOf('Publicar') >= 0) && t.length < 48;
                });
                for (var i = pubs.length - 1; i >= 0; i--) {
                    var node = pubs[i];
                    var depth = 0;
                    while (node && depth < 28) {
                        depth++;
                        node = node.parentElement;
                        if (!node || !node.querySelectorAll) continue;
                        var txt = (node.innerText || '').slice(0, 6000);
                        var files = node.querySelectorAll('input[type=file]');
                        var temSessao = /Sess[aã]o/i.test(txt) || /Pauta/i.test(txt);
                        if (!temSessao) continue;
                        if (!files.length) continue;
                        if (txt.indexOf('Publicar') < 0) continue;
                        node.setAttribute('data-cr2-pub-modal-marker', '1');
                        return true;
                    }
                }
                return false;
            }
            """
        )
        root = page.locator('[data-cr2-pub-modal-marker="1"]').first
        root.wait_for(state="visible", timeout=8000)
        return root
    except Exception:
        pass
    try:
        cand = (
            page.locator("div.bubble-element.Group")
            .filter(has=page.locator("button:has-text('Publicar')"))
            .filter(has=page.locator("input[type=file]"))
        )
        if cand.count() > 0:
            root = cand.first
            root.wait_for(state="visible", timeout=8000)
            return root
    except Exception:
        pass
    return None


def fechar_modal(page):
    try:
        root = _modal_bubble_sessao(page)
        if root is not None:
            root.locator("button:has-text('Fechar')").first.click(timeout=4000)
            time.sleep(0.25)
            return
    except Exception:
        pass
    try:
        page.keyboard.press("Escape")
        time.sleep(0.22)
    except Exception:
        pass


def _preencher_tipo(page, modal_root, tipo_ui):
    if not (tipo_ui or "").strip():
        raise ValueError("Tipo e obrigatorio.")
    tipo_ui = tipo_ui.strip()
    scope = modal_root if modal_root is not None else page
    if modal_root is not None:
        try:
            selects = modal_root.locator("select")
            for i in range(selects.count()):
                sel = selects.nth(i)
                try:
                    sel.select_option(label=tipo_ui, timeout=3500)
                    print("    Tipo (select): {}".format(tipo_ui))
                    return
                except Exception:
                    try:
                        sel.select_option(
                            label=re.compile(re.escape(tipo_ui), re.I), timeout=3000
                        )
                        print("    Tipo (select regex): {}".format(tipo_ui))
                        return
                    except Exception:
                        continue
        except Exception:
            pass
    for lb in LABELS_TIPO:
        try:
            loc = scope.get_by_label(lb, exact=False).first
            loc.wait_for(state="visible", timeout=4000)
            tag = loc.evaluate("el => el.tagName")
            if tag == "SELECT":
                loc.select_option(label=tipo_ui, timeout=4000)
            else:
                loc.click()
                time.sleep(0.28)
                page.get_by_text(tipo_ui, exact=False).last.click(timeout=5000)
            print("    Tipo: {}".format(tipo_ui))
            return
        except Exception:
            continue
    raise RuntimeError("Campo Tipo nao encontrado (valor={!r})".format(tipo_ui))


def _preencher_data(page, modal_root, data_ui):
    if not (data_ui or "").strip():
        raise ValueError("Data e obrigatoria.")
    data_ui = data_ui.strip()
    scope = modal_root if modal_root is not None else page
    if _fill_by_label_candidates(scope, LABELS_DATA, data_ui, page):
        print("    Data: {}".format(data_ui))
        return
    for ph in (
        re.compile(r"01/01/2024|dd/mm|data", re.I),
        re.compile(r"\d{2}/\d{2}/\d{4}"),
    ):
        try:
            loc = scope.get_by_placeholder(ph).first
            loc.wait_for(state="visible", timeout=2500)
            preencher_campo(page, loc, data_ui)
            print("    Data (placeholder): {}".format(data_ui))
            return
        except Exception:
            continue
    raise RuntimeError("Campo Data nao encontrado")


def _preencher_numero(page, modal_root, numero_ui):
    if not (numero_ui or "").strip():
        raise ValueError("Numero e obrigatorio.")
    numero_ui = numero_ui.strip()
    scope = modal_root if modal_root is not None else page
    if _fill_by_label_candidates(scope, LABELS_NUMERO, numero_ui, page):
        print("    Numero: {}".format(numero_ui))
        return
    for ph in (
        re.compile(r"1[ªa]\s*Sess", re.I),
        re.compile(r"Sess[aã]o\s+Ordin", re.I),
        re.compile(r"Ex\.:", re.I),
    ):
        try:
            loc = scope.get_by_placeholder(ph).first
            loc.wait_for(state="visible", timeout=2500)
            preencher_campo(page, loc, numero_ui)
            print("    Numero (placeholder): {}".format(numero_ui))
            return
        except Exception:
            continue
    raise RuntimeError("Campo Numero nao encontrado")


def _revelar_inputs_file(page):
    try:
        page.evaluate(
            """
            () => {
                document.querySelectorAll('input[type=file]').forEach(function (el) {
                    el.style.display = 'block';
                    el.style.opacity = '1';
                    el.style.visibility = 'visible';
                    el.style.position = 'fixed';
                    el.style.top = '0';
                    el.style.left = '0';
                    el.style.zIndex = '99999';
                });
            }
            """
        )
    except Exception:
        pass


def _input_file_por_rotulo(scope, page, labels):
    """Localiza input[type=file] associado ao rotulo (label / texto proximo)."""
    for lb in labels:
        # 1) get_by_label -> ancestral com file
        try:
            loc = scope.get_by_label(lb, exact=False).first
            loc.wait_for(state="attached", timeout=2500)
            handle = loc.element_handle(timeout=2000)
            if handle:
                file_handle = handle.evaluate_handle(
                    """
                    (el) => {
                        if (el.tagName === 'INPUT' && el.type === 'file') return el;
                        var near = el.querySelector && el.querySelector('input[type=file]');
                        if (near) return near;
                        var p = el.parentElement;
                        for (var i = 0; i < 8 && p; i++) {
                            near = p.querySelector('input[type=file]');
                            if (near) return near;
                            p = p.parentElement;
                        }
                        var n = el.nextElementSibling;
                        for (var j = 0; j < 10 && n; j++) {
                            if (n.matches && n.matches('input[type=file]')) return n;
                            near = n.querySelector && n.querySelector('input[type=file]');
                            if (near) return near;
                            n = n.nextElementSibling;
                        }
                        return null;
                    }
                    """
                )
                el = file_handle.as_element() if file_handle else None
                if el:
                    return el
        except Exception:
            pass

        # 2) XPath pelo texto do rotulo
        try:
            needle = normalizar(lb)
            xp = (
                "xpath=.//*[contains(translate(normalize-space(.),"
                "'ÁÀÃÂÄáàãâäÉÈÊËéèêëÍÌÎÏíìîïÓÒÕÔÖóòõôöÚÙÛÜúùûüçÇ',"
                "'AAAAAaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuucC'), '{0}')]"
                "/following::input[@type='file'][1]"
            ).format(needle.replace("'", ""))
            loc = scope.locator(xp).first
            loc.wait_for(state="attached", timeout=2000)
            return loc
        except Exception:
            continue
    return None


def fazer_upload_por_rotulo(page, modal_root, labels, caminho):
    path = _caminho_arquivo(caminho)
    if path is None:
        print("    [INFO] Arquivo omitido ({})".format(labels[0]))
        return False
    scope = modal_root if modal_root is not None else page
    _revelar_inputs_file(page)
    time.sleep(0.08)

    alvo = _input_file_por_rotulo(scope, page, labels)
    if alvo is None:
        # Fallback por indice: ordem Pauta, Ata, Presenca, Votacoes
        ordem = [u[0] for u in UPLOADS]
        key = None
        for k, lbs in UPLOADS:
            if tuple(lbs) == tuple(labels) or labels[0] in lbs:
                key = k
                break
        idx = ordem.index(key) if key in ordem else -1
        if idx >= 0:
            try:
                alvo = scope.locator("input[type=file]").nth(idx)
                alvo.wait_for(state="attached", timeout=3000)
            except Exception:
                alvo = None

    if alvo is None:
        print("    [AVISO] Input file nao achado para '{}'".format(labels[0]))
        return False

    try:
        alvo.set_input_files(str(path))
        time.sleep(PAUSA_APOS_ANEXAR)
        print("    Upload {}: {}".format(labels[0], path.name))
        return True
    except Exception as e:
        print("    [Upload] Falhou {}: {}".format(labels[0], str(e)[:80]))
        return False


def _preencher_link_votacoes(page, modal_root, link):
    if not (link or "").strip():
        print("    [INFO] Link de votacoes omitido.")
        return
    link = link.strip()
    scope = modal_root if modal_root is not None else page
    if _fill_by_label_candidates(scope, LABELS_LINK_VOTACOES, link, page):
        print("    Link votacoes preenchido.")
        return
    for ph in (
        re.compile(r"https?://", re.I),
        re.compile(r"link", re.I),
        re.compile(r"url", re.I),
    ):
        try:
            loc = scope.get_by_placeholder(ph).first
            loc.wait_for(state="visible", timeout=2000)
            preencher_campo(page, loc, link)
            print("    Link votacoes (placeholder).")
            return
        except Exception:
            continue
    print("    [AVISO] Campo link de votacoes nao encontrado.")


def preencher_modal_sessao(page, item):
    modal_root = _modal_bubble_sessao(page)
    _preencher_tipo(page, modal_root, item.get("tipo", ""))
    time.sleep(0.08)
    _preencher_data(page, modal_root, item.get("data", ""))
    time.sleep(0.08)
    _preencher_numero(page, modal_root, item.get("numero", ""))
    time.sleep(0.1)
    for key, labels in UPLOADS:
        fazer_upload_por_rotulo(page, modal_root, labels, item.get(key, ""))
        time.sleep(0.12)
    _preencher_link_votacoes(page, modal_root, item.get("votacoes_link", ""))
    try:
        page.keyboard.press("Tab")
    except Exception:
        pass
    time.sleep(0.15)
    return modal_root


def aguardar_resultado_apos_publicar(page, modal_root):
    limite = time.monotonic() + TIMEOUT_RESULTADO_PUBLICACAO_S
    while time.monotonic() < limite:
        try:
            txt = ""
            if modal_root is not None:
                txt = modal_root.inner_text(timeout=1500)
            else:
                txt = page.locator("body").inner_text(timeout=1500)
            if _TEXTO_ERRO_APOS_PUBLICAR_RX.search(txt or ""):
                raise RuntimeError("Portal indicou erro apos Publicar.")
            if _TEXTO_SUCESSO_MODAL_RX.search(txt or ""):
                return
            # Modal sumiu = sucesso tipico
            if not page.locator("button:has-text('Publicar')").first.is_visible():
                return
        except RuntimeError:
            raise
        except Exception:
            pass
        time.sleep(0.35)


def clicar_publicar(page):
    modal_root = _modal_bubble_sessao(page)
    if modal_root is not None:
        btn = modal_root.locator("button:has-text('Publicar')").first
    else:
        btn = page.locator("button:has-text('Publicar')").first
    btn.wait_for(state="visible", timeout=15000)
    btn.scroll_into_view_if_needed()
    limite = time.monotonic() + TIMEOUT_PUBLICAR_HABILITADO_S
    while time.monotonic() < limite:
        try:
            if btn.is_enabled():
                break
        except Exception:
            pass
        time.sleep(0.35)
    else:
        salvar_screenshot(page, "TIMEOUT_PUBLICAR_SESSAO")
        raise TimeoutError("Botao Publicar desabilitado por demais tempo.")
    aguardar_barra_carregamento_topo(page, etiqueta="antes de Publicar")
    try:
        btn.click(timeout=15000)
    except Exception:
        btn.click(force=True, timeout=15000)
    time.sleep(0.2)
    aguardar_resultado_apos_publicar(page, modal_root)
    time.sleep(PAUSA_APOS_CLICAR_PUBLICAR)


def publicar_um(page, item, idx, total):
    _abortar_se_cancelado()
    rotulo = item.get("numero") or item.get("data") or "sessao"
    print("[{}/{}] {} | {} | {}".format(idx, total, item.get("tipo"), item.get("data"), rotulo))
    abrir_modal(page)
    preencher_modal_sessao(page, item)
    salvar_screenshot(page, "sessao_antes_{}_{}".format(idx, normalizar(rotulo)[:40]))
    clicar_publicar(page)
    salvar_screenshot(page, "sessao_apos_{}_{}".format(idx, normalizar(rotulo)[:40]))
    try:
        if page.locator("button:has-text('Publicar')").first.is_visible():
            fechar_modal(page)
    except Exception:
        fechar_modal(page)
    print("    Concluido.")
    time.sleep(0.2)


# ---------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Publicacao de Sessao — portal CR2")
    p.add_argument("--test", action="store_true", help="Publica so a 1a sessao da fila")
    p.add_argument("--yes", action="store_true", help="Pula Enter pos-login")
    p.add_argument("--headless", action="store_true")
    p.add_argument(
        "--pasta",
        type=str,
        default="",
        help="Pasta com subpastas de sessao (ex.: ...\\sessoes_2021)",
    )
    p.add_argument("--csv", type=str, default="", help="Caminho do CSV da fila (fallback)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    global HEADLESS, MODO_TESTE, CSV_FILA, PASTA_SESSOES
    if args.headless:
        HEADLESS = True
    if args.test:
        MODO_TESTE = True
    if args.pasta:
        PASTA_SESSOES = Path(args.pasta)
    if args.csv:
        CSV_FILA = Path(args.csv)

    if not url_portal_ativa(URL_PORTAL_SESSAO):
        raise ValueError(
            "URL_PORTAL_SESSAO vazia. Informe a URL admin do modulo Sessao "
            "(ex.: https://www.portalcr2.com.br/sessoes/...)."
        )

    fila = montar_fila()
    if not fila:
        raise ValueError(
            "Nenhuma sessao na fila. Informe PASTA_SESSOES "
            "(ex.: ...\\sessoes_2021), REGISTRO_UNICO ou CSV ({}).".format(CSV_FILA)
        )
    if MODO_TESTE:
        fila = fila[:1]
        print("[INFO] Modo teste: 1 sessao.")

    print("=" * 60)
    print("  PUBLICACAO DE SESSAO — portal CR2")
    print("  Total: {}".format(len(fila)))
    print("  Pasta: {}".format(PASTA_SESSOES))
    print("  URL: {}".format(URL_PORTAL_SESSAO))
    print("=" * 60)

    pw = browser = page = None
    ok = erros = 0
    try:
        pw, browser, page = criar_navegador_e_login(pular_enter_pos_login=args.yes)
        garantir_pagina_portal(page, URL_PORTAL_SESSAO, "Sessao")
        for i, item in enumerate(fila, 1):
            try:
                publicar_um(page, item, i, len(fila))
                ok += 1
            except Cancelado:
                raise
            except Exception as e:
                erros += 1
                print("    [ERRO] {}".format(e))
                salvar_screenshot(page, "sessao_erro_{}".format(i))
                try:
                    fechar_modal(page)
                except Exception:
                    pass
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass

    print("")
    print("=" * 60)
    print("  CONCLUIDO! OK: {} | Erros: {} | Total: {}".format(ok, erros, len(fila)))
    print("=" * 60)
    if erros:
        raise RuntimeError("Publicacao de sessao com {} erro(s).".format(erros))


if __name__ == "__main__":
    main()
