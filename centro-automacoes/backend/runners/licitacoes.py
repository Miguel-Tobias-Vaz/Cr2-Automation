from __future__ import annotations

import os
import sys
from pathlib import Path

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs


def _resolver_modo(cfg: dict) -> tuple[str, bool, bool]:
    """Retorna (modo, so_planilha, sem_extracao)."""
    modo = (cfg.get("modo") or "").strip().lower()
    # legado: so_contratos → so_planilha (separar contratos é automático)
    if modo == "so_contratos":
        modo = "so_planilha"
    if modo in ("completo", "so_baixar", "so_planilha"):
        return modo, modo == "so_planilha", modo == "so_baixar"

    so_planilha = bool(cfg.get("so_planilha", False)) or bool(cfg.get("so_contratos", False))
    sem_extracao = bool(cfg.get("sem_extracao", False))
    if so_planilha and sem_extracao:
        return "completo", False, False
    if sem_extracao:
        return "so_baixar", False, True
    if so_planilha:
        return "so_planilha", True, False
    return "completo", False, False


def run(job) -> None:
    cfg = job.config
    modo, so_planilha, sem_extracao = _resolver_modo(cfg)

    listagem = (cfg.get("listagem") or "").strip()
    planilha_fonte = (cfg.get("planilha_fonte") or "").strip()
    if not listagem and not planilha_fonte:
        raise ValueError(
            "Informe a URL da listagem ou o link da planilha Google (Documentos)."
        )

    saida = (cfg.get("pasta_saida") or r"C:\Downloads\Licitacoes").strip()

    anos = (cfg.get("anos") or "").strip()
    planilha_modelo = (cfg.get("planilha_modelo") or "").strip()
    planilha_saida = (cfg.get("planilha_saida") or "").strip()
    ocr = bool(cfg.get("ocr", False))
    incluir_sub = bool(cfg.get("incluir_subcategorias", False))
    so_html = bool(cfg.get("so_html", False))
    ignorar_ssl = bool(cfg.get("ignorar_ssl", False))
    sem_renomear = bool(cfg.get("sem_renomear", False))
    motor_ocr = (cfg.get("motor_ocr") or "tesseract").strip().lower() or "tesseract"
    if motor_ocr in ("docling", "surya", "easyocr", "auto"):
        if motor_ocr != "auto":
            job.emit("info", "Motor OCR '{0}' removido — usando tesseract.".format(motor_ocr))
        motor_ocr = "tesseract"
    link_pasta_base = (cfg.get("link_pasta_base") or "").strip()
    refinar_ia = bool(cfg.get("refinar_ia", False))
    modelo_ia = (cfg.get("modelo_ia") or "llama3.2:3b").strip() or "llama3.2:3b"
    ollama_url = (cfg.get("ollama_url") or "http://127.0.0.1:11434").strip()
    ia_sempre = True  # IA sempre confirma as informações (não só valores)
    limite = cfg.get("limite")
    try:
        limite = int(limite) if limite not in (None, "") else 0
    except (TypeError, ValueError):
        limite = 0
    amostra_mensal = bool(cfg.get("amostra_mensal", False))
    amostra_por_mes = cfg.get("amostra_por_mes", 5)
    try:
        amostra_por_mes = int(amostra_por_mes) if amostra_por_mes not in (None, "") else 5
    except (TypeError, ValueError):
        amostra_por_mes = 5
    if amostra_por_mes < 1:
        amostra_por_mes = 5

    labels = {
        "completo": "Completo (baixar + extrair + planilha)",
        "so_baixar": "Só baixar (sem extrair / sem planilha)",
        "so_planilha": "Só planilha (sem rebaixar anexos)",
    }
    job.emit("info", "Modo: {0}".format(labels.get(modo, modo)))
    if amostra_mensal:
        job.emit(
            "info",
            "Amostra mensal: até {0} por mês (modalidades diversificadas); "
            "demais → Nao_migradas_links.xlsx".format(amostra_por_mes),
        )
    if ocr:
        job.emit("info", "OCR: ligado ({0})".format(motor_ocr))
    else:
        job.emit("info", "OCR: desligado")
    if incluir_sub:
        job.emit("info", "Subcategorias fracassadas/desertas: ligadas")
    if link_pasta_base:
        job.emit("info", "LinkDaPasta base: {0}".format(link_pasta_base))
    if refinar_ia:
        job.emit(
            "info",
            "IA local (Ollama): confirma nº/objeto/situação/datas/valores — {0} @ {1}".format(
                modelo_ia, ollama_url
            ),
        )
    else:
        job.emit("info", "IA local: desligada")

    argv = [
        "download_licitacoes",
        "--saida",
        saida,
    ]
    if planilha_fonte:
        argv += ["--planilha-fonte", planilha_fonte]
    if listagem:
        argv += ["--listagem", listagem]
    if planilha_modelo:
        argv += ["--planilha-modelo", planilha_modelo]
    else:
        argv += ["--planilha-modelo", ""]
    if planilha_saida:
        argv += ["--planilha-saida", planilha_saida]
    if anos:
        argv += ["--anos", anos]
    if incluir_sub:
        argv.append("--incluir-subcategorias")
    if so_planilha:
        argv.append("--so-planilha")
    if sem_extracao:
        argv.append("--sem-extracao")
    if so_html:
        argv.append("--so-html")
    if ignorar_ssl:
        argv.append("--ignorar-ssl")
    if sem_renomear:
        argv.append("--sem-renomear")
    if link_pasta_base:
        argv += ["--link-pasta-base", link_pasta_base]
    if limite and limite > 0:
        argv += ["--limite", str(limite)]
    if amostra_mensal:
        argv.append("--amostra-mensal")
        argv += ["--amostra-por-mes", str(amostra_por_mes)]
    if ocr:
        argv.append("--ocr")
        argv += ["--motor-ocr", motor_ocr or "tesseract"]
    if refinar_ia:
        argv.append("--refinar-ia")
        argv += ["--modelo-ia", modelo_ia]
        argv += ["--ollama-url", ollama_url]
        argv.append("--ia-sempre")  # confirma todas as informações

    # Garante import de gestor_regras/ e evita cache velho de ia_local/
    scripts_dir = str(Path(SCRIPTS["licitacoes"]).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    # Recarrega pacotes locais a cada job (senão TIPOS_*/funções novas não entram)
    for key in list(sys.modules):
        if (
            key == "ia_local"
            or key.startswith("ia_local.")
            or key == "gestor_regras"
            or key.startswith("gestor_regras.")
            or key == "_comum"
            or key.startswith("_comum.")
        ):
            sys.modules.pop(key, None)

    mod = load_module("download_licitacoes", SCRIPTS["licitacoes"])
    mapping = {}
    # Painel: anos vazio = todos (não usa o ANOS_FILTRO hardcoded do script)
    if not anos:
        mapping["ANOS_FILTRO"] = []
    apply_globals(mod, mapping)
    # Sempre um dict vazio (nunca None — main() faz .clear()/.update())
    setattr(mod, "ULTIMO_RESULTADO_UPLOAD", {})

    old_argv = sys.argv
    sys.argv = argv
    try:
        run_main_with_logs(job, mod)
    finally:
        sys.argv = old_argv

    job.result["pasta"] = saida
    job.result["ia"] = "ollama" if refinar_ia else "off"
    upload = getattr(mod, "ULTIMO_RESULTADO_UPLOAD", None) or {}
    if upload.get("planilha_licitacoes"):
        job.result["planilha_licitacoes"] = upload["planilha_licitacoes"]
    if upload.get("planilha_documentos"):
        job.result["planilha_documentos"] = upload["planilha_documentos"]
    if upload.get("planilha_preenchida"):
        job.result["planilha_preenchida"] = upload["planilha_preenchida"]
        job.emit(
            "info",
            "Auditoria (origem dos dados): aba 'Auditoria' em {0}".format(
                upload["planilha_preenchida"]
            ),
        )
    if upload.get("planilha_nao_migradas"):
        job.result["planilha_nao_migradas"] = upload["planilha_nao_migradas"]
        job.emit(
            "info",
            "Não migradas (controle de links): {0} → {1}".format(
                upload.get("nao_migradas", "?"),
                upload["planilha_nao_migradas"],
            ),
        )
    if upload.get("pendentes_relatorio"):
        job.result["pendentes_relatorio"] = upload["pendentes_relatorio"]
    if upload.get("pasta_contratos"):
        job.result["pasta_contratos"] = upload["pasta_contratos"]
    if upload.get("contratos_movidos"):
        job.result["contratos_movidos"] = upload["contratos_movidos"]
        job.emit(
            "info",
            "Contratos separados: {0} arquivo(s) → {1}".format(
                upload["contratos_movidos"],
                upload.get("pasta_contratos") or (os.path.join(saida, "Contratos")),
            ),
        )

    # Fallback: procura na pasta de saída mesmo se o módulo não expôs o dict
    if not job.result.get("planilha_licitacoes"):
        p1 = os.path.join(saida, "subirLicitacoes.xlsx")
        p2 = os.path.join(saida, "subirDocumentosLicitacoes.xlsx")
        if os.path.isfile(p1):
            job.result["planilha_licitacoes"] = p1
        if os.path.isfile(p2):
            job.result["planilha_documentos"] = p2

    if modo == "so_baixar":
        job.result["mensagem"] = "Anexos baixados em {0} (sem planilha).".format(saida)
    elif upload:
        job.result["mensagem"] = (
            "Licitações: {0} prontas, {1} pendentes — {2}".format(
                upload.get("prontas", "?"),
                upload.get("pendentes", "?"),
                saida,
            )
        )
    elif modo == "so_planilha":
        job.result["mensagem"] = "Planilha atualizada a partir de {0}.".format(saida)
    else:
        job.result["mensagem"] = "Licitações processadas em {0}".format(saida)
