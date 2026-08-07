# -*- coding: utf-8 -*-
"""
Confirmação por IA dos campos da licitação.

Padrão: Ollama LOCAL (grátis, roda no PC).
Confirma: número, objeto, situação, datas e valores (não só valores).

Integração Cr2 (flag --refinar-ia).
- Só recebe texto já extraído (título + PDFs prioritários).
- Exige trecho literal (anti-alucinação).
- Cache em disco para não repetir a mesma consulta.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import requests

from .regras_titulo import SITUACOES_FRONT, normaliza

LIMITE_CABECALHO = 12_000  # docs comuns no prompt
LIMITE_TOTAL = 140_000     # Edital+DFD+TR+Homologação íntegros

# Quanto de cada tipo entra no prompt (docs íntegros pesam mais)
LIMITE_PROMPT_POR_TIPO = {
    "edital": 55_000,
    "dfd": 40_000,
    "termo_referencia": 45_000,
    "homologacao": 30_000,
    "orcamento": 20_000,
    "etp": 12_000,
    "contrato": 14_000,
    "ata": 14_000,
    "adjudicacao": 8_000,
    "aviso": 8_000,
    "dispensa_inexig": 12_000,
}

OLLAMA_URL_PADRAO = "http://127.0.0.1:11434"
MODELO_LOCAL_PADRAO = "llama3.2:3b"

_ESQUEMA_KEYS = (
    "numero", "ano", "objeto", "situacao",
    "data_publicacao", "data_abertura",
    "valor_estimado", "valor_homologado",
    "confianca",
    "trecho_numero", "trecho_objeto", "motivo_situacao",
    "trecho_data_publicacao", "trecho_data_abertura",
    "trecho_valor_estimado", "trecho_valor_homologado",
    "observacao",
)

_ESQUEMA = {
    "type": "object",
    "properties": {
        "numero": {
            "type": "string",
            "description": "Número do certame no formato 000/AAAA, ou 'Não informado'.",
        },
        "ano": {"type": "string"},
        "objeto": {
            "type": "string",
            "description": "Objeto da contratação em uma linha, ou 'Não informado'.",
        },
        "situacao": {
            "type": "string",
            "description": "Uma das situações do Front, ou 'Não informado'.",
        },
        "data_publicacao": {
            "type": "string",
            "description": "Data de publicação dd/mm/aaaa, ou 'Não informado'.",
        },
        "data_abertura": {
            "type": "string",
            "description": "Data de abertura da sessão/licitação dd/mm/aaaa, ou 'Não informado'.",
        },
        "valor_estimado": {
            "type": "string",
            "description": (
                "Valor estimado/global/máximo do Edital, DFD ou "
                "Termo de Referência no formato 1720000.00, ou 'Não informado'."
            ),
        },
        "valor_homologado": {
            "type": "string",
            "description": (
                "Valor homologado TOTAL (Termo de Homologação: use o total "
                "final, ou some itens/lotes se não houver total). "
                "Formato 1720000.00, ou 'Não informado'."
            ),
        },
        "confianca": {
            "type": "string",
            "enum": ["alta", "media", "baixa"],
        },
        "trecho_numero": {
            "type": "string",
            "description": "Trecho LITERAL onde o número aparece. Vazio se não houver.",
        },
        "trecho_objeto": {
            "type": "string",
            "description": "Trecho LITERAL do objeto. Vazio se veio só do título.",
        },
        "motivo_situacao": {
            "type": "string",
            "description": "Evidência curta da situação (nome do ato ou trecho).",
        },
        "trecho_data_publicacao": {
            "type": "string",
            "description": "Trecho LITERAL da data de publicação.",
        },
        "trecho_data_abertura": {
            "type": "string",
            "description": "Trecho LITERAL da data de abertura.",
        },
        "trecho_valor_estimado": {
            "type": "string",
            "description": "Trecho LITERAL do valor estimado.",
        },
        "trecho_valor_homologado": {
            "type": "string",
            "description": "Trecho LITERAL do valor homologado/contrato.",
        },
        "observacao": {"type": "string"},
    },
    "required": list(_ESQUEMA_KEYS),
    "additionalProperties": False,
}

_SYSTEM = """Você CONFIRMA campos de licitações públicas brasileiras para o portal CR2.

Receberá:
1) o título da publicação no site;
2) a leitura local (regras) já feita;
3) documentos prioritários (Edital, DFD, TR, Homologação, etc.).

Sua missão é VERIFICAR e, se necessário, CORRIGIR TODOS estes campos — não só valores:
numero, ano, objeto, situacao, data_publicacao, data_abertura,
valor_estimado, valor_homologado.

Regras rígidas:
- Extraia APENAS o que estiver no material. Não invente.
- Se a leitura local estiver correta, MANTENHA-A (confirme).
- Se não puder afirmar, use exatamente "Não informado".
- Número do CERTAME no formato 000/AAAA. NÃO use: lei, decreto, processo
  administrativo, contrato, empenho, CNPJ, telefone.
- Objeto: descrição da contratação, uma linha, sem inventar.
- Situação: use EXATAMENTE uma destas (ou Não informado):
  Aberto, Anulado, Cancelado, Deserto, Em andamento, Finalizado,
  Fracassado, Publicada, Revogado, Suspenso.
- Datas: formato dd/mm/aaaa.
  * data_publicacao: publicação do edital/aviso no site ou no documento.
  * data_abertura: sessão/abertura/disputa (não confundir com publicação).
- VALORES:
  * valor_estimado: TR/Edital/DFD — estimado/global/máximo. Formato 1720000.00.
  * valor_homologado: Termo de Homologação — TOTAL final (ou soma de lotes).
    NÃO confunda com estimado nem preço unitário.
- Em trecho_*, copie texto LITERAL do material.
- Prefira confirmar a leitura local quando correta.
- Responda APENAS um JSON válido, sem markdown.
"""

_RE_NUMERO = re.compile(r"^\s*(\d{1,10})\s*/\s*(\d{4})")  # ignora sufixo portal
_RE_JSON = re.compile(r"\{.*\}", re.DOTALL)


class ErroIA(Exception):
    pass


def ollama_disponivel(base_url: str = OLLAMA_URL_PADRAO) -> bool:
    try:
        r = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _chave_cache(payload: dict) -> str:
    bruto = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:24]


def _carregar_cache(pasta: Path, chave: str) -> dict | None:
    arq = pasta / f"{chave}.json"
    if not arq.is_file():
        return None
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        return None


def _salvar_cache(pasta: Path, chave: str, dados: dict) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{chave}.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _fonte_texto(titulo: str, cabecalhos: list[dict]) -> str:
    partes = [titulo or ""]
    for c in cabecalhos:
        partes.append(c.get("texto") or "")
    return normaliza("\n".join(partes))


def _trecho_existe(trecho: str, fonte: str) -> bool:
    citado = normaliza(trecho)
    if len(citado) < 8:
        return False
    return citado[:120] in fonte


def montar_prompt(titulo: str, leitura_local: dict, cabecalhos: list[dict]) -> str:
    # Prioriza docs íntegros: DFD → Edital → TR → Homologação → demais
    ordem_tipo = {
        "dfd": 0, "edital": 1, "termo_referencia": 2, "homologacao": 3,
        "orcamento": 4, "etp": 5, "contrato": 6, "ata": 7,
        "adjudicacao": 8, "aviso": 9, "dispensa_inexig": 10,
    }
    docs_ord = sorted(
        cabecalhos,
        key=lambda c: (
            ordem_tipo.get(c.get("tipo") or "", 50),
            c.get("nome") or "",
        ),
    )

    blocos = []
    total = 0
    tipos_no_prompt = set()
    for c in docs_ord:
        tipo = c.get("tipo") or "outro"
        lim = LIMITE_PROMPT_POR_TIPO.get(tipo, LIMITE_CABECALHO)
        texto_cheio = c.get("texto") or ""
        texto = texto_cheio[:lim]
        if not texto.strip():
            continue
        nome = c.get("nome") or "documento.pdf"
        rotulo = c.get("rotulo") or tipo or "documento"
        bloco = (
            f'<documento tipo="{rotulo}" nome="{nome}">\n'
            f"{texto}\n</documento>"
        )
        if total + len(bloco) > LIMITE_TOTAL:
            sobra = LIMITE_TOTAL - total - 180
            # Garante pedaço generoso dos docs íntegros se ainda faltam
            essenciais = ("edital", "dfd", "termo_referencia", "homologacao")
            if tipo in essenciais and tipo not in tipos_no_prompt and sobra > 8000:
                texto = texto_cheio[:sobra]
                bloco = (
                    f'<documento tipo="{rotulo}" nome="{nome}">\n'
                    f"{texto}\n</documento>"
                )
                blocos.append(bloco)
                tipos_no_prompt.add(tipo)
                total += len(bloco)
            break
        blocos.append(bloco)
        tipos_no_prompt.add(tipo)
        total += len(bloco)

    docs = "\n\n".join(blocos) if blocos else "(nenhum PDF prioritário com texto)"
    local = json.dumps(leitura_local, ensure_ascii=False, indent=2)
    return (
        f"TÍTULO NO SITE:\n{titulo}\n\n"
        f"LEITURA LOCAL (regras):\n{local}\n\n"
        "DOCUMENTOS PRIORITÁRIOS:\n"
        f"{docs}\n\n"
        "CONFIRME ou CORRIJA todos os campos: numero, objeto, situacao, "
        "data_publicacao, data_abertura, valor_estimado e valor_homologado. "
        "Cite trechos literais. Responda só JSON."
    )


def _extrair_json(bruto: str) -> dict:
    texto = (bruto or "").strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?\s*", "", texto)
        texto = re.sub(r"\s*```$", "", texto)
    try:
        return json.loads(texto)
    except Exception:
        m = _RE_JSON.search(texto)
        if not m:
            raise ErroIA("Resposta da IA não é JSON válido.")
        return json.loads(m.group(0))


def _chamar_ollama(prompt: str, modelo: str, base_url: str) -> dict:
    if not ollama_disponivel(base_url):
        raise ErroIA(
            "Ollama não está rodando em {0}.\n"
            "Instale em https://ollama.com/download e depois rode:\n"
            "  ollama pull {1}\n"
            "  ollama serve".format(base_url, modelo)
        )
    url = f"{base_url.rstrip('/')}/api/chat"
    corpo = {
        "model": modelo,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 1200},
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        r = requests.post(url, json=corpo, timeout=300)
    except requests.exceptions.ConnectionError as exc:
        raise ErroIA(
            "Não conectou no Ollama. Abra o app Ollama ou rode: ollama serve"
        ) from exc
    if r.status_code == 404:
        raise ErroIA(
            "Modelo '{0}' não encontrado. Baixe com:\n  ollama pull {0}".format(modelo)
        )
    if r.status_code >= 400:
        raise ErroIA("Ollama HTTP {0}: {1}".format(r.status_code, r.text[:300]))
    data = r.json()
    bruto = (data.get("message") or {}).get("content") or ""
    return _extrair_json(bruto)


def _chamar_anthropic(prompt: str, modelo: str, api_key: str) -> dict:
    try:
        import anthropic
    except ImportError as exc:
        raise ErroIA("Instale: pip install anthropic") from exc
    if not api_key or api_key.startswith("sk-ant-cole"):
        raise ErroIA("Chave Anthropic ausente (só necessária no provedor 'anthropic').")
    cliente = anthropic.Anthropic(api_key=api_key)
    try:
        resposta = cliente.messages.create(
            model=modelo,
            max_tokens=1200,
            system=[{
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {"type": "json_schema", "schema": _ESQUEMA},
            },
        )
    except Exception as exc:
        raise ErroIA(_msg_erro(exc)) from exc
    bruto = "".join(
        b.text for b in resposta.content if getattr(b, "type", "") == "text"
    )
    return _extrair_json(bruto)


def refinar(
    titulo: str,
    leitura_local: dict,
    cabecalhos: list[dict],
    *,
    provedor: str = "ollama",
    modelo: str = MODELO_LOCAL_PADRAO,
    api_key: str = "",
    ollama_url: str = OLLAMA_URL_PADRAO,
    pasta_cache: Path | None = None,
    usar_cache: bool = True,
) -> dict:
    """Devolve dict com campos refinados + metadados (cache/ia)."""
    provedor = (provedor or "ollama").strip().lower()
    prompt = montar_prompt(titulo, leitura_local, cabecalhos)
    payload_cache = {
        "provedor": provedor,
        "titulo": titulo,
        "local": {
            "numero": leitura_local.get("numero_bruto") or leitura_local.get("numero"),
            "objeto": leitura_local.get("objeto"),
            "situacao": leitura_local.get("situacao"),
            "data_publicacao": leitura_local.get("data_publicacao"),
            "data_abertura": leitura_local.get("data_abertura"),
            "valor_estimado": leitura_local.get("valor_estimado"),
            "valor_homologado": leitura_local.get("valor_homologado"),
        },
        "docs": [
            (c.get("nome"), c.get("tipo"), (c.get("texto") or "")[:500])
            for c in cabecalhos
        ],
        "modelo": modelo,
        "v": 3,
    }
    chave = _chave_cache(payload_cache)

    if usar_cache and pasta_cache:
        hit = _carregar_cache(pasta_cache, chave)
        if hit:
            hit = dict(hit)
            hit["cache"] = True
            hit["origem"] = "ia_cache"
            return hit

    if provedor == "ollama":
        dados = _chamar_ollama(prompt, modelo, ollama_url)
    elif provedor == "anthropic":
        dados = _chamar_anthropic(prompt, modelo, api_key)
    else:
        raise ErroIA("Provedor desconhecido: %s (use ollama ou anthropic)" % provedor)

    fonte = _fonte_texto(titulo, cabecalhos)
    saida = _validar_e_fundir(dados, leitura_local, fonte)
    saida["cache"] = False
    saida["origem"] = "ia_local" if provedor == "ollama" else "ia"
    saida["provedor"] = provedor
    saida["modelo"] = modelo
    saida["chave_cache"] = chave

    if pasta_cache:
        _salvar_cache(pasta_cache, chave, saida)
    return saida


_RE_VALOR_FRONT = re.compile(r"^\s*(\d+(?:\.\d{1,2})?)\s*$")
_RE_DATA_BR = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")


def _normalizar_valor_ia(texto: str) -> str:
    """Aceita 1720000.00 ou 1.720.000,00 → 1720000.00"""
    t = (texto or "").strip()
    if not t or t == "Não informado":
        return ""
    t = t.replace("R$", "").replace("r$", "").strip()
    if re.search(r",\d{2}$", t) and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t and "." not in t:
        t = t.replace(",", ".")
    m = _RE_VALOR_FRONT.match(t)
    if not m:
        return ""
    try:
        return f"{float(m.group(1)):.2f}"
    except ValueError:
        return ""


def _normalizar_data_ia(texto: str) -> str:
    """Aceita dd/mm/aaaa → dd/mm/aaaa normalizado; senão ''."""
    t = (texto or "").strip()
    if not t or t == "Não informado":
        return ""
    m = _RE_DATA_BR.match(t)
    if not m:
        return ""
    d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= d <= 31 and 1 <= mth <= 12 and 1990 <= y <= 2100):
        return ""
    return f"{d:02d}/{mth:02d}/{y}"


def _validar_e_fundir(dados: dict, local: dict, fonte: str) -> dict:
    """Aceita sugestão da IA só com evidência; senão mantém a leitura local."""
    out = {
        "numero": local.get("numero_bruto") or local.get("numero") or "",
        "ano": local.get("ano") or "",
        "objeto": local.get("objeto") or "",
        "situacao": local.get("situacao") or "",
        "data_publicacao": local.get("data_publicacao") or "",
        "data_abertura": local.get("data_abertura") or "",
        "valor_estimado": local.get("valor_estimado") or "",
        "valor_homologado": local.get("valor_homologado") or "",
        "confianca": dados.get("confianca") or "baixa",
        "trecho_numero": dados.get("trecho_numero") or "",
        "trecho_objeto": dados.get("trecho_objeto") or "",
        "motivo_situacao": dados.get("motivo_situacao") or "",
        "trecho_data_publicacao": dados.get("trecho_data_publicacao") or "",
        "trecho_data_abertura": dados.get("trecho_data_abertura") or "",
        "observacao": dados.get("observacao") or "",
        "mudancas": [],
    }

    num_ia = (dados.get("numero") or "").strip()
    if num_ia and num_ia != "Não informado":
        m = _RE_NUMERO.match(num_ia)
        num_norm = normaliza(num_ia)
        num_ok = _trecho_existe(dados.get("trecho_numero", ""), fonte) or (
            num_norm in fonte or normaliza(m.group(0) if m else "") in fonte
        )
        if m and num_ok:
            # Não altera dígitos/códigos já lidos — só a base N/AAAA da IA
            novo = "%s/%s" % (m.group(1), m.group(2))
            local_cheio = out["numero"] or ""
            try:
                from .regras_titulo import numero_sem_categoria
                local_base = numero_sem_categoria(local_cheio)
            except Exception:
                local_base = re.sub(r"-([A-Za-z]+)$", "", local_cheio)
            # Se o local já tem o mesmo N/AAAA (ex.: 9/2023-007-CMVX), preserva
            if local_base and re.search(
                r"(?<!\d)%s\s*/\s*%s\b" % (re.escape(m.group(1)), re.escape(m.group(2))),
                local_base,
            ):
                novo = local_base
            antigo = local_base or local_cheio
            if novo != antigo:
                out["mudancas"].append(f"numero: {antigo or '∅'} → {novo}")
            out["numero"] = novo
            out["ano"] = m.group(2)

    obj_ia = (dados.get("objeto") or "").strip()
    if obj_ia and obj_ia != "Não informado":
        if not out["objeto"]:
            if (_trecho_existe(dados.get("trecho_objeto", ""), fonte)
                    or normaliza(obj_ia)[:80] in fonte):
                out["objeto"] = re.sub(r"\s+", " ", obj_ia)[:1200]
                out["mudancas"].append("objeto: preenchido pela IA")
        elif _trecho_existe(dados.get("trecho_objeto", ""), fonte):
            if dados.get("confianca") == "alta" and normaliza(obj_ia) != normaliza(out["objeto"]):
                if len(obj_ia) >= 25:
                    out["mudancas"].append("objeto: refinado pela IA")
                    out["objeto"] = re.sub(r"\s+", " ", obj_ia)[:1200]

    sit_ia = (dados.get("situacao") or "").strip()
    if sit_ia in SITUACOES_FRONT:
        motivo = dados.get("motivo_situacao") or ""
        if sit_ia != out["situacao"] and (motivo or dados.get("confianca") in ("alta", "media")):
            if out["situacao"]:
                out["mudancas"].append(f"situacao: {out['situacao']} → {sit_ia}")
            else:
                out["mudancas"].append(f"situacao: ∅ → {sit_ia}")
            out["situacao"] = sit_ia

    for campo, chave_trecho in (
        ("data_publicacao", "trecho_data_publicacao"),
        ("data_abertura", "trecho_data_abertura"),
    ):
        data_ok = _normalizar_data_ia(dados.get(campo) or "")
        if not data_ok:
            continue
        trecho_ok = _trecho_existe(dados.get(chave_trecho, ""), fonte)
        data_na_fonte = normaliza(data_ok) in fonte or data_ok in (fonte or "")
        if not (trecho_ok or data_na_fonte or not out.get(campo)):
            # só preenche vazio sem evidência fraca; com evidência troca
            if out.get(campo) and not (trecho_ok or data_na_fonte):
                continue
        if not out.get(campo):
            if trecho_ok or data_na_fonte or dados.get("confianca") in ("alta", "media"):
                out[campo] = data_ok
                out["mudancas"].append(f"{campo}: preenchido pela IA")
        elif data_ok != out.get(campo) and (trecho_ok or data_na_fonte):
            if dados.get("confianca") in ("alta", "media"):
                out["mudancas"].append(
                    f"{campo}: {out.get(campo)} → {data_ok}"
                )
                out[campo] = data_ok

    for campo, chave_trecho in (
        ("valor_estimado", "trecho_valor_estimado"),
        ("valor_homologado", "trecho_valor_homologado"),
    ):
        val = _normalizar_valor_ia(dados.get(campo) or "")
        if not val:
            continue
        trecho_ok = _trecho_existe(dados.get(chave_trecho, ""), fonte)
        digitos = val.replace(".", "")
        fonte_tem = digitos[:6] in re.sub(r"\D", "", fonte) if len(digitos) >= 6 else False
        if not (trecho_ok or fonte_tem):
            continue
        if val != out.get(campo):
            out["mudancas"].append(
                f"{campo}: {out.get(campo) or '∅'} → {val}"
            )
            out[campo] = val

    return out


def _msg_erro(exc: BaseException) -> str:
    nome = type(exc).__name__
    texto = str(exc)
    if "AuthenticationError" in nome or "401" in texto:
        return "Chave de API inválida."
    if "RateLimit" in nome or "429" in texto:
        return "Limite de uso da API. Aguarde e tente de novo."
    if "credit" in texto.lower() or "billing" in texto.lower():
        return "Problema de créditos na Anthropic: " + texto
    return f"{nome}: {texto}"
