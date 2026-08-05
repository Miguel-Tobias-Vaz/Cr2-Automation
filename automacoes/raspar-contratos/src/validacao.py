"""Validação final e montagem do relatório."""

from __future__ import annotations

from typing import Any

from src.logger import get_logger

logger = get_logger()


def montar_resumo(
    *,
    meta_listagem: dict[str, Any],
    registros: list[dict[str, Any]],
    arquivos_flat: list[dict[str, Any]],
) -> list[tuple[str, Any]]:
    total_esperado = meta_listagem.get("total_esperado")
    total_coletado = meta_listagem.get("total_coletado")
    ok = sum(1 for r in registros if r.get("status") == "ok")
    erros = sum(1 for r in registros if r.get("status") == "erro")

    encontrados = len(arquivos_flat)
    baixados = sum(1 for a in arquivos_flat if a.get("status_download") == "baixado")
    reaproveitados = sum(1 for a in arquivos_flat if a.get("status_download") == "reaproveitado")
    falhas_dl = sum(1 for a in arquivos_flat if a.get("status_download") == "falha")

    sem_arquivos = [
        r.get("numero_contrato")
        for r in registros
        if r.get("status") == "ok"
        and not any(a.get("id_registro") == r.get("id_registro") for a in arquivos_flat)
    ]

    ids = [r.get("id_registro") for r in registros]
    duplicados = len(ids) - len(set(ids))

    linhas: list[tuple[str, Any]] = [
        ("registros_esperados_site", total_esperado),
        ("registros_linhas_brutas", meta_listagem.get("total_linhas_brutas")),
        ("registros_unicos_coletados", total_coletado),
        ("duplicados_paginacao", ", ".join(meta_listagem.get("duplicados_listagem") or []) or "0"),
        ("registros_processados", len(registros)),
        ("registros_ok", ok),
        ("registros_erro", erros),
        ("arquivos_encontrados", encontrados),
        ("arquivos_baixados", baixados),
        ("arquivos_reaproveitados", reaproveitados),
        ("downloads_com_erro", falhas_dl),
        ("contratos_sem_arquivos", len(sem_arquivos)),
        ("lista_contratos_sem_arquivos", ", ".join(sem_arquivos) if sem_arquivos else ""),
        ("id_registro_duplicados", duplicados),
    ]

    for p in meta_listagem.get("paginas") or []:
        linhas.append(
            (
                f"pagina_{p.get('pagina')}",
                f"{p.get('status')} ({p.get('registros')} registros)",
            )
        )

    return linhas


def imprimir_relatorio(resumo: list[tuple[str, Any]]) -> None:
    d = dict(resumo)
    texto = f"""
Processamento concluído
Registros no site (rótulo): {d.get('registros_esperados_site')}
Registros únicos coletados: {d.get('registros_unicos_coletados')}
Duplicados na paginação: {d.get('duplicados_paginacao')}
Registros processados: {d.get('registros_processados')}
Registros com erro: {d.get('registros_erro')}

Arquivos encontrados (referências nas páginas): {d.get('arquivos_encontrados')}
Arquivos baixados (novos): {d.get('arquivos_baixados')}
Arquivos reaproveitados (deduplicados): {d.get('arquivos_reaproveitados')}
Downloads com erro: {d.get('downloads_com_erro')}

Contratos sem arquivos: {d.get('contratos_sem_arquivos')}
""".strip()

    logger.info("\n%s", texto)
    for campo, valor in resumo:
        if str(campo).startswith("pagina_"):
            logger.info("%s: %s", campo.replace("_", " ").title(), valor)
