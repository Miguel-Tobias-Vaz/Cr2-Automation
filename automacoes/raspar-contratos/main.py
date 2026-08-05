"""
Automação de coleta de contratos/aditivos — Governo Transparente
Portal: https://www.governotransparente.com.br
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import config
from src import checkpoint as ckpt
from src.browser import iniciar_navegador
from src.detalhes import processar_pagina_detalhe
from src.downloads import processar_arquivos_registro
from src.listagem import descobrir_registros
from src.logger import configurar_logging, get_logger
from src.planilha import gerar_planilha
from src.storage import garantir_dirs
from src.validacao import imprimir_relatorio, montar_resumo


class Cancelado(Exception):
    """Fila cancelada pelo usuario / painel."""


def pedido_cancelado() -> bool:
    """Sobrescrito pelo runner do painel quando ha cancelamento."""
    return False


def _checar_cancelamento() -> None:
    if pedido_cancelado():
        get_logger().warning("Cancelamento solicitado — interrompendo a fila.")
        raise Cancelado()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Coleta contratos/aditivos do Governo Transparente"
    )
    p.add_argument(
        "--orgao",
        default="",
        help="ID do órgão no portal (ex.: 43559588)",
    )
    p.add_argument(
        "--inicio",
        default="",
        help="Data inicial da consulta (dd/mm/aaaa)",
    )
    p.add_argument(
        "--fim",
        default="",
        help="Data final da consulta (dd/mm/aaaa)",
    )
    p.add_argument(
        "--ano",
        default="",
        help="Valor do parâmetro 'ano' da URL do portal (opcional)",
    )
    p.add_argument(
        "--datainfo",
        default="",
        help="Token datainfo da URL (opcional; deixe vazio para o padrão)",
    )
    p.add_argument(
        "--saida",
        default="",
        help="Pasta base de saída (dados/, contratos/, logs/, checkpoint/)",
    )
    p.add_argument(
        "--headed",
        action="store_true",
        help="Exibe o navegador (não headless)",
    )
    p.add_argument(
        "--sem-retry-erros",
        action="store_true",
        help="Não retenta registros marcados como erro no checkpoint",
    )
    p.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Apaga o checkpoint e recomeça do zero",
    )
    p.add_argument(
        "--apenas-listagem",
        action="store_true",
        help="Só varre a listagem (não processa detalhes/downloads)",
    )
    p.add_argument(
        "--limite",
        type=int,
        default=0,
        help="Processa no máximo N registros (0 = todos; útil para teste)",
    )
    return p.parse_args(argv)


def _aplicar_args(args: argparse.Namespace) -> None:
    if args.orgao:
        config.aplicar_orgao(args.orgao)
    if args.inicio or args.fim or args.ano:
        config.aplicar_periodo(
            inicio=args.inicio or None,
            fim=args.fim or None,
            ano=args.ano or None,
        )
    if args.datainfo:
        config.aplicar_datainfo(args.datainfo)
    if args.saida:
        config.aplicar_pasta_saida(args.saida)


def _snapshot_registro(registro: dict[str, Any]) -> dict[str, Any]:
    """Cópia serializável do registro para retomada/planilha."""
    campos = [
        "id_registro",
        "contract_id",
        "aditivo_index",
        "numero_contrato",
        "numero_contrato_slug",
        "tipo_registro",
        "data_listagem",
        "origem",
        "contratante",
        "contratada",
        "cnpj_cpf_contratada",
        "fiscal_responsavel",
        "valor",
        "inicio_vigencia",
        "fim_vigencia",
        "objeto",
        "numero_anexos_listagem",
        "contrato_original_url",
        "url_detalhes",
        "pasta_local",
        "status",
        "mensagem_erro",
        "itens",
    ]
    return {k: registro.get(k) for k in campos}


def processar_registro(
    page,
    context,
    registro: dict[str, Any],
    checkpoint: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Processa um registro completo: detalhe + downloads."""
    try:
        processar_pagina_detalhe(page, registro)
        arquivos = processar_arquivos_registro(page, context, registro, checkpoint)
        registro["status"] = "ok"
        registro["mensagem_erro"] = ""
        ckpt.marcar_registro(
            checkpoint,
            registro["id_registro"],
            status="ok",
            numero_contrato=registro.get("numero_contrato", ""),
            snapshot=_snapshot_registro(registro),
            arquivos=arquivos,
        )
        return registro, arquivos
    except Cancelado:
        raise
    except Exception as exc:  # noqa: BLE001
        registro["status"] = "erro"
        registro["mensagem_erro"] = str(exc)
        registro.setdefault("itens", [])
        registro.setdefault("arquivos", [])
        ckpt.marcar_registro(
            checkpoint,
            registro["id_registro"],
            status="erro",
            numero_contrato=registro.get("numero_contrato", ""),
            mensagem_erro=str(exc),
        )
        get_logger().error(
            "Erro no registro %s: %s",
            registro.get("id_registro"),
            exc,
        )
        return registro, []


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _aplicar_args(args)
    garantir_dirs()
    logger = configurar_logging()

    retry_erros = not args.sem_retry_erros
    headless = not args.headed

    if args.reset_checkpoint:
        checkpoint = ckpt.resetar_checkpoint()
    else:
        checkpoint = ckpt.carregar_checkpoint()

    logger.info(
        "Iniciando coleta — orgao=%s periodo=%s..%s saida=%s headless=%s",
        config.ORGAO_ID,
        config.LISTAGEM_PARAMS.get("inicio"),
        config.LISTAGEM_PARAMS.get("fim"),
        config.CONTRATOS_DIR.parent,
        headless,
    )

    registros_finais: list[dict[str, Any]] = []
    arquivos_flat: list[dict[str, Any]] = []
    meta_listagem: dict[str, Any] = {}

    try:
        with iniciar_navegador(headless=headless) as (_pw, _browser, context, page):
            _checar_cancelamento()
            pendentes, meta_listagem = descobrir_registros(page)
            checkpoint["total_esperado"] = meta_listagem.get("total_esperado")
            checkpoint["paginas_processadas"] = [
                p["pagina"] for p in meta_listagem.get("paginas") or []
            ]
            ckpt.salvar_checkpoint(checkpoint)

            if args.apenas_listagem:
                logger.info(
                    "Modo --apenas-listagem: %d registros descobertos",
                    len(pendentes),
                )
                for r in pendentes:
                    r["status"] = "pendente"
                    r["mensagem_erro"] = ""
                    r["itens"] = []
                    r["arquivos"] = []
                registros_finais = pendentes
            else:
                total = len(pendentes)
                if args.limite and args.limite > 0:
                    pendentes = pendentes[: args.limite]
                    logger.info(
                        "Limite ativo: processando %d de %d",
                        len(pendentes),
                        total,
                    )

                for idx, reg in enumerate(pendentes, start=1):
                    _checar_cancelamento()
                    id_reg = reg["id_registro"]
                    logger.info(
                        "Processando registro %d/%d — %s (%s)",
                        idx,
                        len(pendentes),
                        id_reg,
                        reg.get("numero_contrato"),
                    )

                    if not ckpt.deve_processar(checkpoint, id_reg, retry_erros=retry_erros):
                        logger.info("Já processado (checkpoint ok) — pulando %s", id_reg)
                        info = checkpoint["registros"].get(id_reg, {})
                        snap = info.get("snapshot") or {}
                        if snap:
                            reg.update(snap)
                        reg["status"] = info.get("status", "ok")
                        reg["mensagem_erro"] = info.get("mensagem_erro", "")
                        reg.setdefault("itens", snap.get("itens") or [])
                        arqs = info.get("arquivos") or []
                        arquivos_flat.extend(arqs)
                        registros_finais.append(reg)
                        continue

                    reg_out, arqs = processar_registro(page, context, reg, checkpoint)
                    registros_finais.append(reg_out)
                    arquivos_flat.extend(arqs)
                    time.sleep(config.DELAY_ENTRE_REQUISICOES_SEC)

        resumo = montar_resumo(
            meta_listagem=meta_listagem,
            registros=registros_finais,
            arquivos_flat=arquivos_flat,
        )
        imprimir_relatorio(resumo)

        if not args.apenas_listagem or registros_finais:
            gerar_planilha(registros_finais, arquivos_flat, resumo)

        logger.info("Concluído.")
        erros = sum(1 for r in registros_finais if r.get("status") == "erro")
        return 1 if erros else 0
    except Cancelado:
        if registros_finais:
            try:
                resumo = montar_resumo(
                    meta_listagem=meta_listagem,
                    registros=registros_finais,
                    arquivos_flat=arquivos_flat,
                )
                gerar_planilha(registros_finais, arquivos_flat, resumo)
            except Exception as exc:  # noqa: BLE001
                get_logger().warning("Planilha parcial não gerada: %s", exc)
        raise


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Cancelado:
        sys.exit(130)
