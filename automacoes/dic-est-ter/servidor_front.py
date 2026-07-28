# =====================================================================
#  Worker Dic/Est/Ter — validação, publicação e estado de job
#  (sem HTTP; importado pelo Opto Automações / milagre_routes)
# =====================================================================

from __future__ import annotations

import csv
import io
import re
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

import publicar_estagiario_terceirizado_divida as pub
import job_runtime as jobrt

# Estado compartilhado com job_runtime (SSE, persistência, cancelamento)
_job_lock = jobrt._lock
_job = jobrt._estado

jobrt.restaurar_ao_subir()

# ---------------------------------------------------------------------
#  Constantes
# ---------------------------------------------------------------------

MAX_ERROS_LISTAGEM = 48
MAX_ERROS_OMITIDOS_AVISO = 1
LABELS_FLUXO = {
    "estagiario": "Estagiários",
    "terceirizado": "Terceirizados",
    "divida": "Dívida ativa",
}

MAP_COLUNAS = {
    "estagiario": pub.COLUNAS_ESTAGIARIO,
    "terceirizado": pub.COLUNAS_TERCEIRIZADO,
    "divida": pub.COLUNAS_DIVIDA,
}

OBRIGATORIOS = {
    "estagiario": (
        ("nome", "Nome"),
        ("inicio", "Início do Contrato"),
        ("fim", "Fim do Contrato"),
        ("situacao", "Situação"),
    ),
    "terceirizado": (
        ("mes_ano", "Mês e ano"),
        ("nome", "Nome Completo"),
        ("empresa", "Empresa"),
        ("funcao", "Função"),
    ),
    "divida": (
        ("ano", "Ano"),
        ("nome", "Nome"),
        ("valor", "Valor"),
    ),
}

CAMPOS_MODO = {
    "inicio": "data",
    "fim": "data",
    "mes_ano": "mes_ano",
    "ano": "ano",
}

PLANILHA_LOCAL = {
    "estagiario": pub.PLANILHA_ESTAGIARIO,
    "terceirizado": pub.PLANILHA_TERCEIRIZADO,
    "divida": pub.PLANILHA_DIVIDA,
}

_DRIVE_URL_RX = re.compile(
    r"(docs\.google\.com/(spreadsheets|document)|drive\.google\.com)",
    re.I,
)
_HTTP_URL_RX = re.compile(r"^https?://", re.I)


# ---------------------------------------------------------------------
#  Utilitários de configuração / URL
# ---------------------------------------------------------------------


def _strip(v):
    return (v or "").strip()


def _is_drive_url(v):
    return bool(_DRIVE_URL_RX.search(_strip(v)))


def _is_http_url(v):
    return bool(_HTTP_URL_RX.match(_strip(v)))


def _meta_resumida(body):
    return {
        "teste": bool((body or {}).get("teste")),
        "fluxos": [
            k
            for k in ("estagiario", "terceirizado", "divida")
            if _strip((body or {}).get(k))
        ],
    }


def _aplicar_config(body):
    """Aplica parâmetros do painel no módulo pub (Playwright)."""
    body = body or {}
    pub.PORTAL_USUARIO = _strip(body.get("usuario"))
    pub.PORTAL_SENHA = _strip(body.get("senha"))
    pub.PLANILHA_DRIVE_ESTAGIARIO = _strip(body.get("estagiario"))
    pub.PLANILHA_DRIVE_TERCEIRIZADO = _strip(body.get("terceirizado"))
    pub.PLANILHA_DRIVE_DIVIDA = _strip(body.get("divida"))
    pub.URL_PORTAL_ESTAGIARIO = _strip(body.get("portal_estagiario"))
    pub.URL_PORTAL_TERCEIRIZADO = _strip(body.get("portal_terceirizado"))
    pub.URL_PORTAL_DIVIDA = _strip(body.get("portal_divida"))
    pub.MODO_TESTE = bool(body.get("teste"))


def _fluxos_do_body(body):
    """Retorna dict tipo -> {ativo, url_planilha, url_portal}."""
    body = body or {}
    out = {}
    for tipo in ("estagiario", "terceirizado", "divida"):
        url_plan = _strip(body.get(tipo))
        url_portal = _strip(body.get("portal_" + tipo))
        ativo = bool(url_plan) and bool(url_portal)
        out[tipo] = {
            "tipo": tipo,
            "ativo": ativo,
            "url_planilha": url_plan,
            "url_portal": url_portal,
        }
    return out


def _validar_campos_painel(body):
    erros = []
    body = body or {}
    if not _strip(body.get("usuario")):
        erros.append("Informe o usuário / e-mail do portal.")
    if not _strip(body.get("senha")):
        erros.append("Informe a senha do portal.")

    fluxos = _fluxos_do_body(body)
    ativos = [f for f in fluxos.values() if f["ativo"]]
    if not ativos:
        algum_plan = any(_strip(body.get(k)) for k in ("estagiario", "terceirizado", "divida"))
        if not algum_plan:
            erros.append(
                "Informe ao menos uma planilha (estagiários, terceirizados ou dívida)."
            )
        else:
            for tipo, fx in fluxos.items():
                plan = _strip(body.get(tipo))
                portal = _strip(body.get("portal_" + tipo))
                if plan and not portal:
                    erros.append(
                        "{}: informe a URL do local de publicação no portal.".format(
                            LABELS_FLUXO[tipo]
                        )
                    )
                elif portal and not plan:
                    erros.append(
                        "{}: informe o link da planilha no Drive/Sheets.".format(
                            LABELS_FLUXO[tipo]
                        )
                    )
                if plan and not _is_drive_url(plan):
                    erros.append(
                        "{}: link da planilha inválido (use Google Sheets ou Drive).".format(
                            LABELS_FLUXO[tipo]
                        )
                    )
                if portal and not _is_http_url(portal):
                    erros.append(
                        "{}: URL do portal inválida.".format(LABELS_FLUXO[tipo])
                    )
    else:
        for fx in ativos:
            if not _is_drive_url(fx["url_planilha"]):
                erros.append(
                    "{}: link da planilha inválido.".format(LABELS_FLUXO[fx["tipo"]])
                )
            if not _is_http_url(fx["url_portal"]):
                erros.append(
                    "{}: URL do portal inválida.".format(LABELS_FLUXO[fx["tipo"]])
                )
    return erros


# ---------------------------------------------------------------------
#  Download CSV (validação rápida — cache job_runtime)
# ---------------------------------------------------------------------


def _extrair_gid_sheets(url):
    url = _strip(url)
    m = re.search(r"[?&#]gid=(\d+)", url)
    return m.group(1) if m else None


def _export_csv_url(url_planilha):
    file_id = pub.extrair_id_drive(url_planilha)
    if not file_id:
        return None, None
    base = "https://docs.google.com/spreadsheets/d/{}/export?format=csv".format(
        file_id
    )
    gid = _extrair_gid_sheets(url_planilha)
    if gid:
        base += "&gid={}".format(gid)
    return base, file_id


def _baixar_bytes_url(url, timeout=180):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def baixar_csv_drive(url_planilha, forcar=False):
    """
    Baixa CSV do Google Sheets/Drive com cache (job_runtime).
    Retorna Path local ou None.
    """
    url_planilha = _strip(url_planilha)
    if not url_planilha:
        return None

    export_url, file_id = _export_csv_url(url_planilha)
    if not export_url:
        return None

    if not forcar:
        cached = jobrt.obter_csv_cache(url_planilha, file_id)
        if cached is not None:
            return cached

    try:
        data = _baixar_bytes_url(export_url)
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            "HTTP {} ao baixar planilha — confira compartilhamento (qualquer pessoa com o link).".format(
                e.code
            )
        ) from e
    except Exception as e:
        raise RuntimeError(
            "Falha ao baixar CSV: {}".format(str(e)[:200])
        ) from e

    if not data or len(data) < 4:
        raise RuntimeError("Download da planilha veio vazio.")

    # HTML de login/erro do Google
    inicio = data[:200].lstrip().lower()
    if inicio.startswith(b"<!doctype") or inicio.startswith(b"<html"):
        raise RuntimeError(
            "Planilha não acessível — compartilhe como 'qualquer pessoa com o link'."
        )

    return jobrt.salvar_csv_cache(url_planilha, file_id, data)


def _decodificar_csv(data_bytes):
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return data_bytes.decode("utf-8", errors="replace")


def _iter_linhas_csv(csv_path):
    raw = Path(csv_path).read_bytes()
    text = _decodificar_csv(raw)
    # Sniffer ajuda com separador , ou ;
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    for row in reader:
        yield row


def _celula_csv(row, idx, modo=None):
    if idx is None or idx >= len(row):
        return ""
    return pub._celula_str(row[idx], modo=modo)


def _linha_vazia(row):
    return not row or all(not _strip(c) for c in row)


# ---------------------------------------------------------------------
#  Validação de cabeçalho / contagem via CSV
# ---------------------------------------------------------------------


def _validar_cabecalho_csv(headers, tipo):
    mapa = MAP_COLUNAS[tipo]
    cols = pub._mapear_colunas(headers, mapa)
    faltando = []
    for chave, rotulo in OBRIGATORIOS[tipo]:
        if chave not in cols:
            faltando.append(rotulo)
    return cols, faltando


def _validar_fluxo_csv(tipo, url_planilha, emit_progresso=False):
    """
    Valida planilha via CSV em cache.
    Retorna dict fluxo para resposta JSON.
    """
    t0 = time.time()
    rotulo = LABELS_FLUXO[tipo]
    resultado = {
        "ativo": True,
        "total": 0,
        "itens_ok": 0,
        "erros": [],
        "linhas_a_pular": 0,
        "erros_omitidos": 0,
        "segundos": 0,
    }

    try:
        csv_path = baixar_csv_drive(url_planilha)
    except Exception as e:
        resultado["erros"].append(
            {"linha": 1, "msg": "Download: {}".format(str(e)[:240]), "level": "error"}
        )
        resultado["segundos"] = round(time.time() - t0, 2)
        return resultado

    if csv_path is None or not Path(csv_path).is_file():
        resultado["erros"].append(
            {
                "linha": 1,
                "msg": "Não foi possível baixar a planilha de {}.".format(rotulo),
                "level": "error",
            }
        )
        resultado["segundos"] = round(time.time() - t0, 2)
        return resultado

    linhas = _iter_linhas_csv(csv_path)
    try:
        header_row = next(linhas)
    except StopIteration:
        resultado["erros"].append(
            {"linha": 1, "msg": "Planilha vazia.", "level": "error"}
        )
        resultado["segundos"] = round(time.time() - t0, 2)
        return resultado

    headers = [_strip(pub._celula_str(c)) for c in header_row]
    cols, faltando = _validar_cabecalho_csv(headers, tipo)
    if faltando:
        resultado["erros"].append(
            {
                "linha": 1,
                "msg": "Colunas obrigatórias ausentes: {}. Cabeçalhos: {}".format(
                    ", ".join(faltando), ", ".join(h for h in headers if h)
                ),
                "level": "error",
            }
        )
        resultado["segundos"] = round(time.time() - t0, 2)
        return resultado

    total = 0
    ok = 0
    puladas = 0
    erros = []
    erros_omitidos = 0
    processadas = 0

    for n_linha, row in enumerate(linhas, start=2):
        if _linha_vazia(row):
            continue
        total += 1
        processadas += 1

        faltam = []
        for chave, rotulo in OBRIGATORIOS[tipo]:
            modo = CAMPOS_MODO.get(chave)
            idx = cols.get(chave)
            val = _celula_csv(row, idx, modo=modo)
            if not val:
                faltam.append(rotulo)

        if faltam:
            puladas += 1
            msg = "Campos obrigatórios em branco: {}".format(", ".join(faltam))
            if len(erros) < MAX_ERROS_LISTAGEM:
                erros.append({"linha": n_linha, "msg": msg, "level": "warn"})
            else:
                erros_omitidos += 1
        else:
            ok += 1

        if emit_progresso:
            jobrt.emit_progresso_linhas(processadas, total=total)

    resultado.update(
        {
            "total": total,
            "itens_ok": ok,
            "erros": erros,
            "linhas_a_pular": puladas,
            "erros_omitidos": erros_omitidos,
            "segundos": round(time.time() - t0, 2),
        }
    )
    return resultado


def _montar_resumo_linhas(fluxos_result):
    total = ok = com_erro = 0
    for fx in fluxos_result.values():
        if not fx.get("ativo"):
            continue
        total += fx.get("total") or 0
        ok += fx.get("itens_ok") or 0
        com_erro += fx.get("linhas_a_pular") or 0
    return {"total": total, "ok": ok, "com_erro": com_erro}


def _fluxo_tem_bloqueio(fx):
    return any(e.get("level") != "warn" for e in (fx.get("erros") or []))


def validar_pedido(body):
    """
    Valida credenciais, links e cabeçalhos (CSV cache).
    Retorna dict consumido pelo front dic-est-ter.js.
    """
    body = body or {}
    erros_gerais = _validar_campos_painel(body)
    fluxos_cfg = _fluxos_do_body(body)
    fluxos = {}

    for tipo, cfg in fluxos_cfg.items():
        if not cfg["ativo"]:
            fluxos[tipo] = {
                "ativo": False,
                "total": 0,
                "itens_ok": 0,
                "erros": [],
                "linhas_a_pular": 0,
                "erros_omitidos": 0,
                "segundos": 0,
            }
            continue
        fluxos[tipo] = _validar_fluxo_csv(tipo, cfg["url_planilha"])

    resumo_linhas = _montar_resumo_linhas(fluxos)
    bloqueios = erros_gerais[:]
    for tipo, fx in fluxos.items():
        if fx.get("ativo") and _fluxo_tem_bloqueio(fx):
            bloqueios.append(
                "{}: cabeçalho ou download inválido.".format(LABELS_FLUXO[tipo])
            )

    ok = not bloqueios and resumo_linhas.get("ok", 0) > 0
    aviso_pular = None
    if resumo_linhas.get("com_erro", 0) > 0:
        aviso_pular = (
            "Linhas com campo obrigatório em branco serão puladas na publicação."
        )

    return {
        "ok": ok,
        "erros_gerais": bloqueios,
        "fluxos": fluxos,
        "resumo_linhas": resumo_linhas,
        "aviso_publicacao": (
            "Igual ao RGF: botão Criar Publicação, uma linha por vez."
        ),
        "aviso_pular": aviso_pular,
    }


# ---------------------------------------------------------------------
#  Stdout → SSE (tee)
# ---------------------------------------------------------------------


def _nivel_log_linha(linha):
    s = (linha or "").strip()
    if not s:
        return "info"
    if "[ERRO]" in s or s.startswith("Erro"):
        return "error"
    if "[AVISO]" in s or "[PULO]" in s or "pulando" in s.lower():
        return "warn"
    if "[OK]" in s or "Resumo:" in s:
        return "ok"
    if s.startswith("[->"):
        return "info"
    if "— fim —" in s:
        return "info"
    return "info"


class _StdoutTee:
    """Redireciona stdout/stderr para jobrt.emit mantendo console."""

    def __init__(self, original, level_fn=None):
        self._original = original
        self._level_fn = level_fn or _nivel_log_linha
        self._buf = ""

    def write(self, s):
        if not s:
            return
        if self._original is not None:
            try:
                self._original.write(s)
            except UnicodeEncodeError:
                try:
                    self._original.write(
                        s.encode("ascii", errors="replace").decode("ascii")
                    )
                except Exception:
                    pass
            except Exception:
                pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():
                jobrt.emit(self._level_fn(line), line)

    def flush(self):
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass

    def isatty(self):
        if self._original is not None and hasattr(self._original, "isatty"):
            try:
                return self._original.isatty()
            except Exception:
                pass
        return False

    def fileno(self):
        if self._original is not None and hasattr(self._original, "fileno"):
            return self._original.fileno()
        raise OSError("fileno")

    def flush_tail(self):
        tail = self._buf.strip()
        if tail:
            jobrt.emit(self._level_fn(tail), tail)
            self._buf = ""


# ---------------------------------------------------------------------
#  Cancelamento / liberação
# ---------------------------------------------------------------------


def _liberar_publicacao():
    return jobrt.liberar()


# ---------------------------------------------------------------------
#  Montagem de filas (xlsx) para publicação
# ---------------------------------------------------------------------


def _baixar_planilha_publicacao(tipo, url_planilha):
    destino = PLANILHA_LOCAL[tipo]
    path = pub.baixar_planilha_drive(url_planilha, destino)
    if path is None or not Path(path).is_file():
        raise RuntimeError(
            "Não foi possível baixar planilha de {}.".format(LABELS_FLUXO[tipo])
        )
    return Path(path)


def _ler_filas_publicacao(modo_teste=False):
    """Lê filas a partir dos paths locais já configurados em pub."""
    filas = {}
    puladas = []

    if pub.url_portal_ativa(pub.URL_PORTAL_ESTAGIARIO) and _strip(
        pub.PLANILHA_DRIVE_ESTAGIARIO
    ):
        path = pub.PLANILHA_ESTAGIARIO
        if path.is_file():
            est, p_est = pub.ler_fila_estagiario(path, retornar_puladas=True)
            filas["estagiario"] = est
            puladas.extend(p_est)

    if pub.url_portal_ativa(pub.URL_PORTAL_TERCEIRIZADO) and _strip(
        pub.PLANILHA_DRIVE_TERCEIRIZADO
    ):
        path = pub.PLANILHA_TERCEIRIZADO
        if path.is_file():
            ter, p_ter = pub.ler_fila_terceirizado(path, retornar_puladas=True)
            filas["terceirizado"] = ter
            puladas.extend(p_ter)

    if pub.url_portal_ativa(pub.URL_PORTAL_DIVIDA) and _strip(pub.PLANILHA_DRIVE_DIVIDA):
        path = pub.PLANILHA_DIVIDA
        if path.is_file():
            div, p_div = pub.ler_fila_divida(path, retornar_puladas=True)
            filas["divida"] = div
            puladas.extend(p_div)

    if modo_teste:
        for k in filas:
            filas[k] = filas[k][:1]

    # Retomada por checkpoint
    for k in list(filas.keys()):
        antes = len(filas[k])
        filas[k] = jobrt.filtrar_fila_apos_checkpoint(filas[k], k)
        depois = len(filas[k])
        if antes > depois:
            jobrt.emit(
                "info",
                "{}: retomando após checkpoint — {} linha(s) já publicada(s).".format(
                    LABELS_FLUXO.get(k, k), antes - depois
                ),
            )

    return filas, puladas


def _preparar_planilhas_publicacao(body):
    fluxos = _fluxos_do_body(body)
    for tipo, cfg in fluxos.items():
        if not cfg["ativo"]:
            continue
        jobrt.emit(
            "info",
            "Baixando planilha {}…".format(LABELS_FLUXO[tipo]),
        )
        _baixar_planilha_publicacao(tipo, cfg["url_planilha"])


def _contar_total_filas(filas):
    return sum(len(f) for f in filas.values())


# ---------------------------------------------------------------------
#  Worker de publicação
# ---------------------------------------------------------------------


def _callback_publicacao(retry_counter):
    def on_item(ok=None, item=None, kind=None, publicadas=0, erros=0, fase=None):
        if jobrt.pedido_cancelado():
            return False

        prog = {
            "publicadas": publicadas or 0,
            "erros": erros or 0,
            "retries": retry_counter["n"],
            "fase": "publicando",
        }
        total = retry_counter.get("total") or 0
        if total > 0:
            prog["chunk_total"] = total
            prog["chunk_atual"] = min(total, (publicadas or 0) + (erros or 0))
            prog["linhas_processadas"] = prog["chunk_atual"]

        if fase == "ok":
            prog["msg"] = "Publicada L{} ({})".format(
                (item or {}).get("linha"), kind or "?"
            )
        elif fase == "erro":
            prog["msg"] = "Erro L{} ({})".format(
                (item or {}).get("linha"), kind or "?"
            )
        elif fase == "antes":
            prog["msg"] = "Publicando L{} ({})".format(
                (item or {}).get("linha"), kind or "?"
            )

        jobrt.atualizar_progresso(**prog)
        return True

    return on_item


def _executar_publicacao(body):
    _aplicar_config(body)
    modo_teste = bool(body.get("teste"))

    jobrt.emit("info", "Validando planilhas antes de publicar…")
    val = validar_pedido(body)
    if not val.get("ok"):
        msgs = list(val.get("erros_gerais") or [])
        for tipo, fx in (val.get("fluxos") or {}).items():
            for err in fx.get("erros") or []:
                if err.get("level") != "warn":
                    msgs.append(
                        "{} L{}: {}".format(
                            LABELS_FLUXO.get(tipo, tipo),
                            err.get("linha"),
                            err.get("msg"),
                        )
                    )
        msg = msgs[0] if msgs else "Validação falhou."
        jobrt.emit("error", msg)
        jobrt.finalizar({"ok": False, "validacao": val, "erro": msg})
        return

    jobrt.atualizar_progresso(fase="baixando", msg="Baixando planilhas (.xlsx)…")
    _preparar_planilhas_publicacao(body)

    filas, puladas_previas = _ler_filas_publicacao(modo_teste=modo_teste)
    fila_est = filas.get("estagiario") or []
    fila_ter = filas.get("terceirizado") or []
    fila_div = filas.get("divida") or []
    total = _contar_total_filas(filas)

    if total == 0:
        jobrt.emit("warn", "Nenhuma linha válida na fila para publicar.")
        jobrt.finalizar(
            {
                "ok": False,
                "erro": "Nenhuma linha válida na fila.",
                "nao_publicadas": puladas_previas,
            }
        )
        return

    if modo_teste:
        jobrt.emit("warn", "Modo teste — no máximo 1 linha por fluxo ativo.")

    jobrt.atualizar_progresso(
        total=total,
        publicadas=0,
        erros=len(puladas_previas),
        chunk_total=total,
        chunk_atual=0,
        fase="iniciando_playwright",
        msg="{} linha(s) na fila".format(total),
    )

    jobrt.emit(
        "info",
        "Fila: {} estagiário(s), {} terceirizado(s), {} dívida(s).".format(
            len(fila_est), len(fila_ter), len(fila_div)
        ),
    )

    retry_counter = {"n": 0, "total": total}
    on_item = _callback_publicacao(retry_counter)

    pub.garantir_playwright_pronto()

    publicadas, nao_publicadas = pub.publicar_filas(
        fila_est,
        fila_ter,
        fila_div,
        pular_enter_pos_login=True,
        on_item=on_item,
    )

    cancelado = jobrt.pedido_cancelado()

    todas_nao = list(puladas_previas) + list(nao_publicadas or [])
    arquivo_np = None
    if todas_nao:
        try:
            arquivo_np = pub.gerar_planilha_nao_publicadas(todas_nao)
            if arquivo_np:
                jobrt.set_arquivo_nao_publicadas(arquivo_np)
                jobrt.emit(
                    "warn",
                    "{} linha(s) nao publicada(s) - planilha de correcao gerada.".format(
                        len(todas_nao)
                    ),
                )
        except Exception as e:
            jobrt.emit(
                "error",
                "Falha ao gerar planilha de nao publicadas: {}".format(str(e)[:200]),
            )

    resumo = {
        "ok": (not cancelado) and publicadas > 0,
        "cancelado": cancelado,
        "publicadas": publicadas,
        "nao_publicadas": [
            {
                "kind": x.get("kind"),
                "linha": x.get("linha"),
                "nome": x.get("nome"),
                "motivo": x.get("motivo"),
            }
            for x in todas_nao
        ],
        "download_nao_publicadas": (
            "/api/download/nao-publicadas" if todas_nao else None
        ),
        "arquivo_nao_publicadas": str(arquivo_np) if arquivo_np else None,
        "modo_teste": modo_teste,
    }

    if cancelado:
        jobrt.atualizar_progresso(
            publicadas=publicadas,
            erros=len(todas_nao),
            fase="cancelado",
            msg="Fila cancelada — {} publicada(s) antes de parar".format(publicadas),
        )
        jobrt.emit("warn", "CANCELADO — fila deste processo interrompida.")
        jobrt.finalizar(resumo)
        return

    jobrt.atualizar_progresso(
        publicadas=publicadas,
        erros=len(todas_nao),
        chunk_atual=total,
        chunk_total=total,
        fase="concluido",
        msg="Concluido — {} publicada(s)".format(publicadas),
    )

    if publicadas > 0 and not todas_nao:
        try:
            jobrt.limpar_checkpoint()
        except Exception:
            pass

    jobrt.emit(
        "ok",
        "Resumo: {} publicada(s) | {} não publicada(s)".format(
            publicadas, len(todas_nao)
        ),
    )
    jobrt.finalizar(resumo)


def _rodar_publicacao(body):
    """Entry point do worker (thread daemon)."""
    if not jobrt.iniciar_job(body_meta=_meta_resumida(body)):
        jobrt.emit("warn", "Já existe publicação em andamento.")
        return

    old_out = sys.stdout
    old_err = sys.stderr
    tee_out = _StdoutTee(old_out)
    tee_err = _StdoutTee(old_err)
    sys.stdout = tee_out
    sys.stderr = tee_err

    try:
        if jobrt.pedido_cancelado():
            jobrt.finalizar({"ok": False, "cancelado": True})
            return
        _executar_publicacao(body or {})
    except Exception as exc:
        tb = traceback.format_exc()
        jobrt.emit("error", "Erro fatal: {}".format(str(exc)[:300]))
        jobrt.emit("error", tb[-800:])
        jobrt.finalizar({"ok": False, "erro": str(exc)})
    finally:
        tee_out.flush_tail()
        tee_err.flush_tail()
        sys.stdout = old_out
        sys.stderr = old_err
        with _job_lock:
            if _job.get("running"):
                jobrt.finalizar(
                    _job.get("resumo") or {"ok": False, "erro": "Worker encerrado"}
                )
