# -*- coding: utf-8 -*-
"""Extração por regras dos campos do contrato (planilha Front)."""

from __future__ import annotations

import datetime
import re
import unicodedata
from typing import Any

from .config_front import (
    AGUARDANDO_INFO,
    CHAVES_CONTRATO,
    CNPJ_INEXISTENTE,
    DIAS_VIGENCIA_PADRAO,
)

_RE_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}\s*/\s*\d{4}\s*-?\s*\d{2}\b")
_RE_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}\s*-\s*\d{2}\b")
_RE_CONTRATADA = re.compile(r"\bcontratad[ao]\b|\bcontratad[ao]\s*\(a\)", re.I)
_RE_CONTRATANTE = re.compile(
    r"prefeitura\s+municipal|municipio\s+de|fundo\s+municipal|"
    r"camara\s+municipal|secretaria\s+municipal|estado\s+d[oe]",
    re.I,
)
_RE_RUIDO_NOME = re.compile(
    r",?\s*(pessoa\s+juridica.*|inscrit[ao].*|com\s+sede.*|estabelecid[ao].*|"
    r"sediada.*|cnpj.*|c\.n\.p\.j.*|doravante.*|neste\s+ato.*|representad[ao].*|"
    r"portador.*|situad[ao].*|endereco.*)$",
    re.I,
)
_RE_DATA = re.compile(r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})\b")
_RE_MOEDA = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?![\d])"
)
_RE_NUM_CONTRATO = re.compile(
    r"(?<!\d)(\d{1,10})\s*/\s*(\d{4})(?!\d)"
)
_RE_NOME_PESSOA = re.compile(
    r"\b([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç']+"
    r"(?:\s+(?:d[aeo]s?|e)\s+|\s+)"
    r"(?:[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç']+\s*){1,5})"
)
_RE_NOME_MAIUSCULO = re.compile(
    r"\b([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]{2,}(?:\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]{1,}){1,5})"
)


def normalizar(txt: str) -> str:
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip().lower()


def registro_contrato_vazio() -> dict[str, Any]:
    r = {k: "" for k in CHAVES_CONTRATO}
    r["tipoContrato"] = "Contrato"
    r["arquivo"] = ""
    r["vigencia_assumida"] = ""
    return r


def _limpar_nome(bruto: str) -> str:
    nome = re.sub(r"\s+", " ", bruto or "").strip(" \t:;-–,.")
    nome = _RE_RUIDO_NOME.sub("", nome).strip(" \t:;-–,.")
    nome = re.split(r"\.\s", nome)[0].strip(" \t:;-–,.")
    return nome[:150] if len(nome) >= 4 else ""


def _formatar_cnpj(bruto: str) -> str:
    d = re.sub(r"\D", "", bruto or "")
    if len(d) != 14:
        return ""
    return "%s.%s.%s/%s-%s" % (d[:2], d[2:5], d[5:8], d[8:12], d[12:])


def _formatar_cpf(bruto: str) -> str:
    d = re.sub(r"\D", "", bruto or "")
    if len(d) != 11:
        return ""
    return "%s.%s.%s-%s" % (d[:3], d[3:6], d[6:9], d[9:])


def _formatar_data(d: int, m: int, a: int) -> str:
    try:
        return datetime.date(a, m, d).strftime("%d/%m/%Y")
    except ValueError:
        return ""


def _datas_no_texto(texto: str) -> list[str]:
    out = []
    for m in _RE_DATA.finditer(texto or ""):
        fmt = _formatar_data(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if fmt:
            out.append(fmt)
    return out


def _data_apos(n: str, texto: str, palavras: list[str], janela: int = 160) -> str:
    for palavra in palavras:
        for m in re.finditer(palavra, n):
            datas = _datas_no_texto(texto[m.end(): m.end() + janela])
            if datas:
                return datas[0]
    return ""


def _moeda_para_front(txt: str) -> str:
    """Formato contratos Front: 68069,00 (vírgula)."""
    if not txt:
        return ""
    t = txt.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}", t):
        return t.replace(".", "") if t.count(".") else t
    # US / float
    try:
        if "," in t and "." in t:
            val = float(t.replace(".", "").replace(",", "."))
        elif "," in t:
            val = float(t.replace(",", "."))
        else:
            val = float(t)
        return ("%.2f" % val).replace(".", ",")
    except ValueError:
        return ""


def _valor_apos(n: str, palavras: list[str], janela: int = 260) -> str:
    for palavra in palavras:
        for m in re.finditer(palavra, n):
            trecho = n[m.end(): m.end() + janela]
            ach = _RE_MOEDA.search(trecho)
            if ach:
                return _moeda_para_front(ach.group(1))
    return ""


def _documento_da_contratada(texto: str, n: str) -> str:
    marca = re.search(r"\bcontratad[ao]\b|\bcontratad[ao]\s*\(a\)", texto, re.I)
    if marca:
        depois = texto[marca.end():]
        achado = _RE_CNPJ.search(depois)
        if achado:
            fmt = _formatar_cnpj(achado.group(0))
            if fmt:
                return fmt
        achado = _RE_CPF.search(depois)
        if achado:
            return _formatar_cpf(achado.group(0))
    for m in _RE_CNPJ.finditer(texto):
        ini = max(0, m.start() - 220)
        contexto = normalizar(texto[ini:m.start()])
        if _RE_CONTRATANTE.search(contexto):
            continue
        fmt = _formatar_cnpj(m.group(0))
        if fmt:
            return fmt
    m = _RE_CPF.search(texto)
    return _formatar_cpf(m.group(0)) if m else ""


def _razao_social(texto: str, n: str, cnpj: str) -> str:
    for m in re.finditer(r"contratad[ao]\s*(?:\(a\))?\s*[:\-–]", n):
        bruto = texto[m.end(): m.end() + 200]
        bruto = re.split(r"[\r\n]", bruto)[0]
        nome = _limpar_nome(bruto)
        if nome:
            return nome
    for m in re.finditer(r"\b(?:a\s+)?empresa\s+", n):
        bruto = texto[m.end(): m.end() + 200]
        nome = _limpar_nome(re.split(r"[\r\n]", bruto)[0])
        if nome:
            return nome
    if cnpj:
        digitos = re.sub(r"\D", "", cnpj)
        for m in _RE_CNPJ.finditer(texto):
            if re.sub(r"\D", "", m.group(0)) != digitos:
                continue
            antes = texto[max(0, m.start() - 220): m.start()]
            antes = re.split(r"[\r\n]", antes)[-1]
            antes = re.split(r",", antes)[0]
            nome = _limpar_nome(antes)
            if nome:
                return nome
    return ""


def _vigencia(texto: str, n: str) -> tuple[str, str]:
    palavras_vig = [
        r"prazo\s+de\s+vigencia", r"vigencia\s+d[eo]\s+contrato", r"vigencia",
        r"vigorar[a]?\s+(?:de|a\s+partir)", r"periodo\s+de\s+execucao",
    ]
    palavras_ini = [
        r"data\s+de\s+inicio", r"\binicio\s*[:\-–]", r"a\s+contar\s+de",
        r"a\s+partir\s+de", r"com\s+inicio\s+em",
    ]
    palavras_fim = [
        r"data\s+de\s+(termino|encerramento)", r"\btermino\s*[:\-–]",
        r"encerrando[-\s]se\s+em", r"\bate\s+o\s+dia\b", r"\bvalido\s+ate\b",
    ]
    palavras_ass = [
        r"data\s+da\s+assinatura", r"assinad[oa]\s+em", r"assinatura\s+d[eo]",
    ]
    inicio = _data_apos(n, texto, palavras_ini, 160)
    fim = _data_apos(n, texto, palavras_fim, 160)
    if not (inicio and fim):
        for palavra in palavras_vig:
            for m in re.finditer(palavra, n):
                datas = _datas_no_texto(texto[m.end(): m.end() + 400])
                if len(datas) >= 2:
                    return datas[0], datas[1]
                if datas and not inicio:
                    inicio = datas[0]
    if not inicio:
        inicio = _data_apos(n, texto, palavras_ass, 200)
    return inicio or "", fim or ""


def _valor(n: str) -> str:
    palavras = [
        r"valor\s+global", r"valor\s+total\s+d[oa]\s+contrato", r"valor\s+total",
        r"valor\s+d[oe]\s+(contrato|presente\s+contrato)", r"valor\s+contratad",
        r"importa\s+(?:em|no\s+valor)", r"valor\s+estimado\s+d[oa]\s+contrato",
        r"preco\s+global", r"valor\s+mensal",
    ]
    return _valor_apos(n, palavras, 260)


def _fiscal(texto: str, n: str) -> str:
    palavras = [
        r"fiscal\s+d[oe]\s+contrato\s*[:\-–]?", r"fiscal\s+contratual\s*[:\-–]?",
        r"gestor\s+d[oe]\s+contrato\s*[:\-–]?", r"fiscalizacao\s+ficara\s+a\s+cargo",
        r"\bfiscal\s*[:\-–]",
    ]
    for palavra in palavras:
        for m in re.finditer(palavra, n):
            trecho = texto[m.end(): m.end() + 160]
            trecho = re.split(r"[\r\n]{2,}|[;.]", trecho)[0]
            achado = (_RE_NOME_MAIUSCULO.search(trecho)
                      or _RE_NOME_PESSOA.search(trecho))
            if achado:
                nome = re.sub(r"\s+", " ", achado.group(1)).strip(" ,;:-–")
                if len(nome) >= 6:
                    return nome[:120]
    return ""


def _objeto(texto: str, n: str) -> str:
    for rot in (
        r"objeto\s+d[oe]\s+(?:presente\s+)?contrato",
        r"objeto\s*[:\-–]",
        r"tem\s+por\s+objeto",
        r"tem\s+como\s+objeto",
    ):
        for m in re.finditer(rot, n):
            bruto = texto[m.end(): m.end() + 500]
            bruto = re.split(r"\n\s*\n|CL[ÁA]USULA|\bCLAUSULA\b", bruto, maxsplit=1)[0]
            obj = re.sub(r"\s+", " ", bruto).strip(" \t:;-–.")
            if len(obj) >= 20:
                return obj[:500]
    return ""


def _numero_ano(n: str, texto: str) -> tuple[str, str]:
    for rot in (
        r"contrato\s+administrativo", r"contrato\s+n", r"\bcontrato\b",
        r"termo\s+de\s+contrato",
    ):
        for m in re.finditer(rot, n):
            trecho = texto[m.end(): m.end() + 140]
            ach = _RE_NUM_CONTRATO.search(trecho)
            if ach:
                seq, ano = ach.group(1), ach.group(2)
                num = "%s/%s" % (seq.zfill(3) if len(seq) <= 3 else seq, ano)
                return num, ano
    return "", ""


def _somar_dias(data_br: str, dias: int) -> str:
    try:
        d, m, a = (int(x) for x in data_br.split("/"))
        return (datetime.date(a, m, d) + datetime.timedelta(days=dias)).strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        return ""


def aplicar_regra_vigencia(reg: dict[str, Any]) -> dict[str, Any]:
    inicio = (reg.get("dataVigenciaIN") or "").strip()
    fim = (reg.get("dataVigenciaFIM") or "").strip()
    if inicio and not fim:
        calculada = _somar_dias(inicio, DIAS_VIGENCIA_PADRAO)
        if calculada:
            reg["dataVigenciaFIM"] = calculada
            reg["vigencia_assumida"] = "sim"
    return reg


def aplicar_regra_14(reg: dict[str, Any]) -> dict[str, Any]:
    tem_nome = bool((reg.get("nomeRazaoSocial") or "").strip())
    tem_doc = bool((reg.get("cpfCnpj") or "").strip())
    if not tem_nome and not tem_doc:
        reg["nomeRazaoSocial"] = AGUARDANDO_INFO
        reg["cpfCnpj"] = CNPJ_INEXISTENTE
    return reg


def extrair_contrato(
    texto: str,
    *,
    licitacao_origem: str = "",
    tipo: str = "Contrato",
    arquivo: str = "",
) -> dict[str, Any]:
    """Uma linha da planilha de contratos a partir do texto (todos os docs concatenados)."""
    reg = registro_contrato_vazio()
    reg["tipoContrato"] = tipo or "Contrato"
    reg["licitacaoOrigem"] = licitacao_origem or ""
    reg["arquivo"] = arquivo or ""
    reg["documento"] = ""  # regra 11

    if not texto or not texto.strip():
        return aplicar_regra_14(reg)

    n = normalizar(texto)
    numero, ano = _numero_ano(n, texto)
    reg["numero"] = numero
    reg["objeto"] = _objeto(texto, n)
    cnpj = _documento_da_contratada(texto, n)
    reg["cpfCnpj"] = cnpj
    reg["nomeRazaoSocial"] = _razao_social(texto, n, cnpj)
    reg["dataVigenciaIN"], reg["dataVigenciaFIM"] = _vigencia(texto, n)
    reg["valor"] = _valor(n)
    reg["fiscalContrato"] = _fiscal(texto, n)
    if ano:
        reg["ano"] = ano
    elif reg["dataVigenciaIN"]:
        reg["ano"] = reg["dataVigenciaIN"][-4:]

    aplicar_regra_14(reg)
    aplicar_regra_vigencia(reg)
    return reg
