# -*- coding: utf-8 -*-
"""Formatação Front (regras 5, 8, 12) — portado do Gestor V1."""

from __future__ import annotations

import re
import unicodedata

from .config_front import (
    CAMPOS_OBRIGATORIOS_FRONT,
    MAPA_SITUACAO,
    MODALIDADE_REGISTRO_PRECOS,
    MODALIDADES,
    NAO_INFORMADO,
    ROTULOS,
    SIGLAS,
    SITUACOES,
)

MODALIDADE_SEM_CERTAME = "Não houve Processos Licitatórios"
VALOR_SIGILOSO = "Valor sigiloso"

SITUACOES_VALIDAS = [s for s in SITUACOES if s != NAO_INFORMADO]
MODALIDADES_VALIDAS = [
    m for m in MODALIDADES if m not in (NAO_INFORMADO, MODALIDADE_SEM_CERTAME)
]

# Ate 10 digitos: portais como Altamira usam 1123002/2023 (nao so 001/2023)
_RE_NUMERO = re.compile(r"^\s*(\d{1,10})\s*/\s*(\d{4})\s*(?:-\s*[A-Za-z]+)?\s*$")
_RE_NUMERO_BUSCA = re.compile(r"(?<!\d)(\d{1,10})\s*/\s*(\d{4})")
_RE_DATA = re.compile(r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})\b")
_RE_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_RE_RP = re.compile(r"registro\s+de\s+pre[cç]os?", re.I)


def _vazio(valor) -> bool:
    texto = "" if valor is None else str(valor).strip()
    return texto in ("", NAO_INFORMADO)


def _texto_front(valor) -> str:
    if _vazio(valor):
        return ""
    return re.sub(r"\s+", " ", str(valor)).strip()


def sigla(modalidade: str) -> str:
    return SIGLAS.get((modalidade or "").strip(), "")


def numero_front(reg: dict) -> str:
    bruto = str(reg.get("numero", "") or "")
    m = _RE_NUMERO.match(bruto)
    if not m:
        # "003/2025", "Nº 003/2025-PE" ou codigos longos tipo "1123002/2023"
        m = _RE_NUMERO_BUSCA.search(bruto)
        if not m:
            return ""
    seq = m.group(1)
    # Padroniza so numeros curtos (001/2023); nao corta 1123002
    base = "%s/%s" % (seq.zfill(3) if len(seq) <= 3 else seq, m.group(2))
    s = sigla(reg.get("modalidade", ""))
    return "%s-%s" % (base, s) if s else base


def ano_front(reg: dict) -> str:
    ano = str(reg.get("ano", "") or "").strip()
    if re.fullmatch(r"\d{4}", ano):
        return ano
    m = _RE_NUMERO_BUSCA.search(str(reg.get("numero", "") or ""))
    return m.group(2) if m else ""


def data_front(valor) -> str:
    if _vazio(valor):
        return ""
    # datetime / date
    if hasattr(valor, "strftime"):
        try:
            return valor.strftime("%d/%m/%Y")
        except Exception:
            pass
    texto = str(valor)
    m = _RE_DATA_ISO.search(texto)
    if m:
        dia, mes, ano = m.group(3), m.group(2), m.group(1)
    else:
        m = _RE_DATA.search(texto)
        if not m:
            return ""
        dia, mes, ano = m.group(1), m.group(2), m.group(3)
    try:
        d, mm, a = int(dia), int(mes), int(ano)
    except ValueError:
        return ""
    if not (1 <= d <= 31 and 1 <= mm <= 12 and 1990 <= a <= 2100):
        return ""
    return "%02d/%02d/%04d" % (d, mm, a)


def _para_decimal(valor):
    if _vazio(valor):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = re.sub(r"(?i)r\$|\s|\xa0", "", str(valor))
    texto = texto.replace("−", "-")
    if not re.search(r"\d", texto):
        return None
    texto = re.sub(r"[^\d.,\-]", "", texto)
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "." in texto:
        depois = texto.rsplit(".", 1)[1]
        if len(depois) == 3 and texto.count(".") > 1:
            texto = texto.replace(".", "")
        elif len(depois) == 3 and re.fullmatch(r"\d{1,3}(\.\d{3})+", texto.replace("-", "")):
            texto = texto.replace(".", "")
    try:
        return float(texto)
    except ValueError:
        return None


def valor_front(valor) -> str:
    if not _vazio(valor) and VALOR_SIGILOSO.lower() in str(valor).lower():
        return "0.00"
    numero = _para_decimal(valor)
    return "" if numero is None else "%.2f" % numero


def modalidade_front(valor) -> str:
    texto = (str(valor or "")).strip()
    if texto in MODALIDADES_VALIDAS:
        return texto
    alvo = texto.lower()
    for m in MODALIDADES_VALIDAS:
        if m.lower() == alvo:
            return m
    # aliases → nome oficial (mais específico primeiro; match por substring)
    aliases = {
        "registro de precos originario de chamamento": (
            "Registro de Preços Originário de Chamamento Público"
        ),
        "registro de precos originario de pregao eletronico": (
            "Registro de Preços Originário de Pregão Eletrônico"
        ),
        "registro de precos originario de pregao presencial": (
            "Registro de Preços Originário de Pregão Presencial"
        ),
        "adesao a ata de registro de preco": "Adesão a Ata de Registro de Preço",
        "adesao": "Adesão a Ata de Registro de Preço",
        "credenciamento": "Credenciamento",
        "concorrencia eletronica": "Concorrência",
        "concorrencia presencial": "Concorrência",
        "concorrencia": "Concorrência",
        "concurso": "Concurso",
        "carona": "Carona",
        "contratacao direta": "Contratação Direta",
        "carta convite": "Convite",
        "convite": "Convite",
        "chamada publica": "Chamada Pública",
        "chamamento publico": "Chamada Pública",
        "chamamento": "Chamada Pública",
        "dialogo competitivo": "Diálogo Competitivo",
        "dispensa de licitacao": "Dispensa de Licitação",
        "dispensa": "Dispensa de Licitação",
        "inexigibilidade de licitacao": "Inexigibilidade de Licitação",
        "inexigibilidade": "Inexigibilidade de Licitação",
        "leilao": "Leilão",
        "pregao eletronico": "Pregão Eletrônico",
        "pregao presencial": "Pregão Presencial",
        "tomada de precos": "Tomada de Preços",
        "tomada de preco": "Tomada de Preços",
    }
    n = re.sub(r"\s+", " ", alvo)
    n = unicodedata.normalize("NFKD", n)
    n = "".join(c for c in n if not unicodedata.combining(c))
    for k, v in aliases.items():
        if k in n:
            return v
    return ""


def situacao_front(valor) -> str:
    texto = (str(valor or "")).strip()
    if texto in SITUACOES_VALIDAS:
        return texto
    alvo = texto.lower()
    if alvo in MAPA_SITUACAO:
        return MAPA_SITUACAO[alvo]
    for s in SITUACOES_VALIDAS:
        if s.lower() == alvo:
            return s
    return MAPA_SITUACAO.get(alvo, "")


def aplicar_registro_precos(reg: dict) -> dict:
    """Regra 7: PE/PP/CP + 'registro de preços' no objeto -> modalidade RP*."""
    out = dict(reg)
    mod = modalidade_front(out.get("modalidade"))
    objeto = _texto_front(out.get("objeto"))
    if mod in MODALIDADE_REGISTRO_PRECOS and objeto and _RE_RP.search(objeto):
        out["modalidade"] = MODALIDADE_REGISTRO_PRECOS[mod]
    return out


def linha_front(reg: dict) -> dict:
    reg = aplicar_registro_precos(reg)
    publicacao = data_front(reg.get("data_publicacao"))
    abertura = data_front(reg.get("data_abertura"))
    estimado = valor_front(reg.get("valor_estimado")) or "0.00"
    homologado = valor_front(reg.get("valor_homologado"))
    sit = situacao_front(reg.get("situacao"))
    if not homologado and sit == "Finalizado":
        homologado = estimado
    return {
        "modalidade": modalidade_front(reg.get("modalidade")),
        "numero": numero_front(reg),
        "ano": ano_front(reg),
        "objeto": _texto_front(reg.get("objeto")),
        "data_publicacao": publicacao,
        "data_abertura": abertura or publicacao,
        "valor_estimado": estimado,
        "situacao": sit,
        "valor_homologado": homologado or "0.00",
    }


def falta_para_o_front(reg: dict) -> list[str]:
    linha = linha_front(reg)
    faltando: list[str] = []

    if (reg.get("modalidade") or "").strip() == MODALIDADE_SEM_CERTAME:
        return ["Modalidade (não é certame: não tem número)"]

    for chave in CAMPOS_OBRIGATORIOS_FRONT:
        if not linha.get(chave):
            faltando.append(ROTULOS.get(chave, chave))

    if linha["numero"] and "-" not in linha["numero"]:
        faltando.append("Sigla da modalidade")

    if not linha["data_publicacao"] and not linha["data_abertura"]:
        faltando.append("Data de Publicação (nenhuma data no dossiê)")

    return faltando


def alertas_licitacao(reg: dict) -> list[str]:
    alertas: list[str] = []
    if not valor_front(reg.get("valor_estimado")):
        alertas.append("Valor Estimado: não encontrado; gravado 0.00")
    if not data_front(reg.get("data_abertura")):
        alertas.append(
            "Data de Abertura: não encontrada; repetida a Data de Publicação (%s)"
            % data_front(reg.get("data_publicacao"))
        )
    if (
        not valor_front(reg.get("valor_homologado"))
        and situacao_front(reg.get("situacao")) == "Finalizado"
    ):
        estimado = valor_front(reg.get("valor_estimado"))
        alertas.append(
            "Valor Homologado: Finalizada sem homologado; repetido Estimado (%s)"
            % (estimado or "0.00")
        )
    return alertas
