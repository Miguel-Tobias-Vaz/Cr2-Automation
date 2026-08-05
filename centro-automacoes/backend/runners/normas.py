from __future__ import annotations

from pathlib import Path

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs

_MODOS = ("categoria", "hub_anos", "pagina")


def _parse_linhas(texto: str, modo: str) -> list[dict]:
    """Lê linhas no formato 'url' ou 'url | pasta' (pasta opcional = título/URL)."""
    itens: list[dict] = []
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = [p.strip() for p in linha.split("|")]
        url = partes[0] if partes else ""
        if not url.startswith("http"):
            continue
        pasta = partes[1] if len(partes) >= 2 and partes[1] else ""
        # Compat: se alguém ainda colar "url | modo | pasta" neste campo
        if pasta.lower() in _MODOS:
            modo_linha = pasta.lower()
            pasta = partes[2] if len(partes) >= 3 and partes[2] else ""
            itens.append({"url": url, "modo": modo_linha, "pasta": pasta})
        else:
            itens.append({"url": url, "modo": modo, "pasta": pasta})
    return itens


def _parse_fontes_legado(texto: str) -> list[dict]:
    """Formato antigo: url | modo | pasta."""
    itens: list[dict] = []
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = [p.strip() for p in linha.split("|")]
        if not partes or not partes[0].startswith("http"):
            continue
        item = {
            "url": partes[0],
            "modo": "categoria",
            "pasta": "",
        }
        if len(partes) >= 2 and partes[1]:
            if partes[1].lower() in _MODOS:
                item["modo"] = partes[1].lower()
                if len(partes) >= 3 and partes[2]:
                    item["pasta"] = partes[2]
            else:
                item["pasta"] = partes[1]
        if len(partes) >= 3 and partes[2] and partes[1].lower() in _MODOS:
            item["pasta"] = partes[2]
        itens.append(item)
    return itens


def run(job) -> None:
    cfg = job.config
    pasta = (cfg.get("pasta_base") or r"C:\Downloads\Inhangapi").strip()
    site = (cfg.get("site") or "").strip()
    ler_pdf = bool(cfg.get("ler_pdf", True))
    limite = int(cfg.get("limite_posts") or 0)
    anos_raw = (cfg.get("anos") or "").strip()
    anos_filtro = [a.strip() for a in anos_raw.split(",") if a.strip()] if anos_raw else []

    fontes: list[dict] = []
    fontes.extend(_parse_linhas(cfg.get("fontes_categoria") or "", "categoria"))
    # Fora do catálogo: pasta vazia → título da página / slug da URL
    fontes.extend(_parse_linhas(cfg.get("fontes_outros") or "", "categoria"))
    fontes.extend(_parse_linhas(cfg.get("fontes_hub_anos") or "", "hub_anos"))
    fontes.extend(_parse_linhas(cfg.get("fontes_pagina") or "", "pagina"))

    # Compatibilidade com formulário antigo (um único textarea)
    if not fontes and (cfg.get("fontes") or "").strip():
        fontes = _parse_fontes_legado(cfg.get("fontes") or "")

    if not fontes:
        raise ValueError(
            "Informe ao menos um link em Categoria, Hub de anos ou Página."
        )

    por_modo = {}
    for f in fontes:
        por_modo[f["modo"]] = por_modo.get(f["modo"], 0) + 1
    for modo, n in por_modo.items():
        job.emit("info", "Fontes {0}: {1}".format(modo, n))

    mod = load_module("download_normas", SCRIPTS["normas"])
    mapping = {
        "PASTA_BASE": pasta,
        "LER_PDF": ler_pdf,
        "LIMITE_POSTS": limite,
        "ANOS_FILTRO": anos_filtro,
        "FONTES": fontes,
        "REFINAR_IA": bool(cfg.get("refinar_ia", False)),
        "MODELO_IA": (cfg.get("modelo_ia") or "llama3.2:3b").strip() or "llama3.2:3b",
        "OLLAMA_URL": (cfg.get("ollama_url") or "http://127.0.0.1:11434").strip()
        or "http://127.0.0.1:11434",
        "IA_SEMPRE": bool(cfg.get("ia_sempre", False)),
        "EXTRAI_DIARIAS": True,  # regra geral (fonte/PDF de diárias → planilha)
    }
    if site:
        mapping["SITE"] = site.rstrip("/")
    apply_globals(mod, mapping)
    if anos_filtro:
        job.emit("info", "Filtro de anos: {0}".format(", ".join(anos_filtro)))
    else:
        job.emit("info", "Filtro de anos: todos")
    if mapping["REFINAR_IA"]:
        job.emit(
            "info",
            "IA local: Ollama / {0} @ {1} (nome + confirmação de Diárias)".format(
                mapping["MODELO_IA"], mapping["OLLAMA_URL"]
            ),
        )
    else:
        job.emit("info", "IA local: desligada")
    if mapping.get("EXTRAI_DIARIAS", True):
        job.emit(
            "info",
            "Diárias: regra automática quando a URL/pasta/PDF for de diárias"
            + (" (+ IA confirma)" if mapping["REFINAR_IA"] else ""),
        )
    job.emit(
        "info",
        "Sessões: Pautas/Atas/Presença/Votações → pasta por sessão (ex. 17ª Sessão Ordinária)",
    )
    run_main_with_logs(job, mod)
    regs = getattr(mod, "REGISTROS_DIARIAS", None) or []
    if regs:
        job.result["diarias"] = len(regs)
        job.result["planilha_diarias"] = str(
            Path(pasta) / "Diarias.xlsx"
        )
    job.result["pasta"] = pasta
    job.result["mensagem"] = "Extração Pro concluída em {0}".format(pasta)
