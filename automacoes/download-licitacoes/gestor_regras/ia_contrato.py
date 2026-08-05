# -*- coding: utf-8 -*-
"""IA local confirma campos do contrato lendo TODOS os documentos da pasta."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .config_front import CHAVES_CONTRATO
from .extrair_contrato import (
    _moeda_para_front,
    aplicar_regra_14,
    aplicar_regra_vigencia,
)

LIMITE_TOTAL = 160_000
LIMITE_POR_DOC = 80_000

_SYSTEM = """Você confere campos de CONTRATOS administrativos brasileiros (portal CR2).

Receberá a leitura local (regras) e o texto INTEIRO de todos os PDFs da pasta
do contrato (contrato assinado, extrato, portaria de fiscal, etc.).

Campos (JSON):
  licitacaoOrigem, ano, tipoContrato, numero, objeto, nomeRazaoSocial,
  cpfCnpj, dataVigenciaIN, dataVigenciaFIM, valor, fiscalContrato, documento

Regras:
- Extraia APENAS o que estiver nos documentos. Não invente.
- tipoContrato: use "Contrato" (aditivo não entra nesta planilha).
- numero: número do CONTRATO (ex. 055/2026), não o da licitação.
- licitacaoOrigem: mantenha o informado (número da licitação com sigla).
- nomeRazaoSocial e cpfCnpj: da CONTRATADA (empresa), NUNCA do município.
- datas: dd/mm/aaaa.
- valor: total/global do contrato, formato 68069,00 (vírgula nos centavos).
  Se houver itens, some ou use o valor total final.
- fiscalContrato: nome completo do fiscal/gestor do contrato.
- documento: sempre string vazia "".
- Se não puder afirmar um campo, deixe "" (exceto nome/CNPJ: se ambos
  faltarem, use nome "Aguardando informação" e CNPJ "00.000.000/0000-00").
- Prefira confirmar a leitura local quando correta.
- Responda APENAS JSON válido, sem markdown.
"""


def _import_ollama():
    automacoes = Path(__file__).resolve().parents[2]
    if str(automacoes) not in sys.path:
        sys.path.insert(0, str(automacoes))
    from _comum.ia_ollama import chamar_json  # noqa: WPS433
    return chamar_json


def _montar_prompt(
    leitura_local: dict[str, Any],
    docs: list[dict[str, str]],
) -> str:
    blocos = []
    total = 0
    for d in docs:
        texto = (d.get("texto") or "")[:LIMITE_POR_DOC]
        if not texto.strip():
            continue
        nome = d.get("nome") or "documento.pdf"
        bloco = f'<documento nome="{nome}">\n{texto}\n</documento>'
        if total + len(bloco) > LIMITE_TOTAL:
            sobra = LIMITE_TOTAL - total - 80
            if sobra > 5000:
                bloco = f'<documento nome="{nome}">\n{texto[:sobra]}\n</documento>'
                blocos.append(bloco)
            break
        blocos.append(bloco)
        total += len(bloco)

    local = {k: leitura_local.get(k, "") for k in CHAVES_CONTRATO}
    docs_txt = "\n\n".join(blocos) if blocos else "(sem texto)"
    return (
        f"{_SYSTEM}\n\n"
        f"LEITURA LOCAL (regras):\n{json.dumps(local, ensure_ascii=False, indent=2)}\n\n"
        f"DOCUMENTOS (leia TODOS para confirmar):\n{docs_txt}\n\n"
        "Confirme ou corrija os campos. Responda só JSON."
    )


def _normalizar_saida(ia: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k in CHAVES_CONTRATO:
        if k == "documento":
            out[k] = ""
            continue
        if k not in ia:
            continue
        val = ia.get(k)
        if val is None:
            continue
        s = str(val).strip()
        if not s or s.lower() in ("nao informado", "não informado", "null", "none"):
            continue
        if k == "valor":
            s = _moeda_para_front(s) or s
        if k == "tipoContrato":
            s = "Contrato"
        out[k] = s
    out["documento"] = ""
    if not (out.get("licitacaoOrigem") or "").strip():
        out["licitacaoOrigem"] = base.get("licitacaoOrigem") or ""
    aplicar_regra_14(out)
    aplicar_regra_vigencia(out)
    return out


def refinar_contrato_ia(
    leitura_local: dict[str, Any],
    docs: list[dict[str, str]],
    *,
    modelo: str = "llama3.2:3b",
    ollama_url: str = "http://127.0.0.1:11434",
) -> dict[str, Any]:
    """Confirma campos com Ollama lendo todos os docs. Em falha, devolve local."""
    try:
        chamar_json = _import_ollama()
    except Exception:
        return leitura_local

    prompt = _montar_prompt(leitura_local, docs)
    try:
        ia = chamar_json(
            prompt,
            modelo=modelo,
            base_url=ollama_url,
            temperatura=0.05,
            timeout=300,
        )
    except Exception:
        return leitura_local
    if not isinstance(ia, dict):
        return leitura_local
    return _normalizar_saida(ia, leitura_local)
