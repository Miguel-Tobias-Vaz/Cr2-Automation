# -*- coding: utf-8 -*-
"""IA local confirma campos de Diárias lendo o texto do PDF (Ollama)."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

CHAVES = [
    "numero_portaria",
    "data_portaria",
    "inicio_viagem",
    "fim_viagem",
    "quantidade_diarias",
    "nome",
    "cargo",
    "motivo",
    "destino",
    "valor_total",
    "arquivo",
]

CAMPOS_DIARIAS = [
    ("numero_portaria", "Número da Portaria"),
    ("data_portaria", "Data da Portaria"),
    ("inicio_viagem", "Início da Viagem"),
    ("fim_viagem", "Fim da Viagem"),
    ("quantidade_diarias", "Quantidade de Diárias"),
    ("nome", "Nome"),
    ("cargo", "Cargo"),
    ("motivo", "Motivo da Viagem"),
    ("destino", "Destino da Viagem"),
    ("valor_total", "Valor Total"),
    ("arquivo", "Arquivo"),
]

LIMITE_TEXTO = 12_000

_SYSTEM = """Você confere campos de PORTARIAS / atos de DIÁRIAS (administração pública brasileira).

Receberá a leitura local (regras regex) e o texto do PDF.
Sua tarefa: CONFIRMAR ou CORRIGIR cada campo com base no documento.

Campos JSON (use exatamente estas chaves):
  numero_portaria, data_portaria, inicio_viagem, fim_viagem,
  quantidade_diarias, nome, cargo, motivo, destino, valor_total

Regras:
- Extraia APENAS o que estiver no documento. Não invente.
- Prefira manter a leitura local quando ela estiver correta.
- datas: dd/mm/aaaa
- numero_portaria: formato 045/2025 (número/ano)
- quantidade_diarias: só o número (ex. "3")
- valor_total: formato R$ 1.350,00
- nome: pessoa que viajou (beneficiário), não o prefeito/autoridade que assina
- cargo: cargo dessa pessoa
- motivo: finalidade da viagem
- destino: cidade/local da viagem
- Se não puder afirmar um campo, deixe "" (string vazia)
- Responda APENAS JSON válido, sem markdown
"""


def _import_ollama():
    automacoes = Path(__file__).resolve().parents[1]
    if str(automacoes) not in sys.path:
        sys.path.insert(0, str(automacoes))
    from _comum.ia_ollama import ErroOllama, chamar_json, ollama_disponivel  # noqa: WPS433

    return chamar_json, ollama_disponivel, ErroOllama


def _norm(txt: str) -> str:
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


def _evidencia_ok(valor: str, fonte: str) -> bool:
    """Aceita valor da IA só se houver eco no texto (anti-alucinação)."""
    if not valor or not fonte:
        return False
    v = _norm(valor)
    f = _norm(fonte)
    if len(v) < 2:
        return False
    if re.fullmatch(r"\d{1,4}", v):
        return bool(re.search(r"(?<!\d)" + re.escape(v) + r"(?!\d)", f))
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", valor.strip()):
        alt = valor.strip().replace("/", ".")
        return valor.strip() in fonte or alt in fonte or _norm(valor)[:10] in f
    digitos = re.sub(r"\D", "", valor)
    if digitos and len(digitos) >= 3 and digitos in re.sub(r"\D", "", fonte):
        return True
    trecho = v[:48] if len(v) > 8 else v
    if trecho and trecho in f:
        return True
    palavras = [p for p in re.findall(r"[a-z0-9]{4,}", v) if p not in ("para", "com", "dias")]
    if not palavras:
        return False
    hits = sum(1 for p in palavras if p in f)
    return hits >= max(1, (len(palavras) + 1) // 2)


def _montar_prompt(leitura_local: dict[str, Any], texto: str) -> str:
    local = {k: leitura_local.get(k, "") for k in CHAVES if k != "arquivo"}
    rotulos = {k: r for k, r in CAMPOS_DIARIAS if k != "arquivo"}
    return (
        f"{_SYSTEM}\n\n"
        f"Rótulos: {json.dumps(rotulos, ensure_ascii=False)}\n\n"
        f"LEITURA LOCAL (regras):\n{json.dumps(local, ensure_ascii=False, indent=2)}\n\n"
        f"DOCUMENTO:\n{(texto or '')[:LIMITE_TEXTO]}\n\n"
        "Confirme ou corrija. Responda só JSON com as chaves listadas."
    )


def _mesclar(ia: dict[str, Any], base: dict[str, Any], texto: str) -> dict[str, Any]:
    out = dict(base)
    alterados = []
    for k in CHAVES:
        if k == "arquivo":
            continue
        if k not in ia:
            continue
        val = ia.get(k)
        if val is None:
            continue
        s = str(val).strip()
        if not s or s.lower() in ("nao informado", "não informado", "null", "none", "-"):
            continue
        if k == "quantidade_diarias":
            m = re.search(r"\d{1,3}", s)
            s = m.group(0) if m else s
        if k == "valor_total" and s and not s.upper().startswith("R$"):
            if re.search(r"\d", s):
                s = "R$ " + s.lstrip()
        if not _evidencia_ok(s, texto):
            continue
        if s != (base.get(k) or "").strip():
            alterados.append(k)
        out[k] = s
    out["arquivo"] = base.get("arquivo") or ""
    out["_ia_alterou"] = ",".join(alterados)
    return out


def confirmar_diarias_ia(
    leitura_local: dict[str, Any],
    texto: str,
    *,
    modelo: str = "llama3.2:3b",
    ollama_url: str = "http://127.0.0.1:11434",
) -> dict[str, Any]:
    """
    Pede à IA para confirmar/corrigir campos com base no texto do PDF.
    Em falha/offline devolve a leitura local.
    """
    if not (texto or "").strip() or len(texto.strip()) < 40:
        return leitura_local

    try:
        chamar_json, ollama_disponivel, _Erro = _import_ollama()
    except Exception as exc:
        print("    [IA-DIARIAS] pacote indisponível ({0})".format(exc))
        return leitura_local

    if not ollama_disponivel(ollama_url):
        print("    [IA-DIARIAS] Ollama offline — mantendo regras")
        return leitura_local

    prompt = _montar_prompt(leitura_local, texto)
    try:
        ia = chamar_json(
            prompt,
            modelo=modelo,
            base_url=ollama_url,
            temperatura=0.05,
            timeout=180,
        )
    except Exception as exc:
        print("    [IA-DIARIAS] falha: {0}".format(str(exc)[:120]))
        return leitura_local

    if not isinstance(ia, dict):
        return leitura_local

    out = _mesclar(ia, leitura_local, texto)
    alterou = out.pop("_ia_alterou", "") or ""
    if alterou:
        print("    [IA-DIARIAS] confirmou/corrigiu: {0}".format(alterou))
    else:
        print("    [IA-DIARIAS] confirmou leitura local")
    return out
