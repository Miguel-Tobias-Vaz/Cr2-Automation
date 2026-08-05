# -*- coding: utf-8 -*-
"""Extração de Valor Estimado e Valor Homologado nos documentos prioritários."""

from __future__ import annotations

import re

from .regras_titulo import normaliza

# BR: 1.720.000,00 | 1720,00
# US (planilhas Contábil/Mapa): 1,720,000.00 | 1720.00 (só com milhar ou >= 4 dígitos)
RE_MOEDA_BR = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?![\d])"
)
RE_MOEDA_US = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:,\d{3})+\.\d{2}|\d{4,}\.\d{2})(?![\d])"
)
RE_MOEDA_RS = re.compile(
    r"r\s*[\$s]\s*("
    r"\d{1,3}(?:\.\d{3})+(?:,\d{2})?"
    r"|\d+,\d{2}"
    r"|\d{1,3}(?:,\d{3})+\.\d{2}"
    r"|\d{1,3}(?:\.\d{3})+"
    r"|\d{4,}\.\d{2}"
    r")",
    re.IGNORECASE,
)
# Totais de linha em mapa de cotação: "Valores médios : 1.617 29,100.00"
RE_VALORES_MEDIOS = re.compile(
    r"valores\s+m[eé]dios\s*:?\s*[^\n]*?"
    r"(\d{1,3}(?:,\d{3})+\.\d{2}|\d{4,}\.\d{2}|\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})",
    re.IGNORECASE,
)

ROTULOS_ESTIMADO = [
    "valor total estimado", "valor global estimado", "valor estimado",
    "valor total de referencia", "valor de referencia", "valor maximo",
    "valor global maximo estimado", "preco maximo", "preco estimado",
    "custo estimado", "valor previsto", "despesa estimada",
    "estimado no valor", "valor teto", "orcado em", "orcamento estimado",
    "orcamento total", "estimativa de preco", "total estimado",
    "cujo valor estimado", "total geral", "preco total",
    "valor total", "valor global",
]

ROTULOS_HOMOLOGADO = [
    "valor homologado", "valor adjudicado", "valor total homologado",
    "valor total do contrato", "valor do contrato", "valor contratado",
    "valor da contratacao", "valor global do contrato", "valor global",
    "homologado no valor", "adjudicado no valor", "no valor global de",
    "no valor total de", "perfazendo o valor", "pela importancia de",
    "proposta vencedora no valor", "lance vencedor", "valor negociado",
    "total do vencedor", "valor total", "valor da proposta",
    "pelo valor de", "no valor de",
]

# Totais explícitos no Termo de Homologação (preferir, sobretudo no final)
ROTULOS_TOTAL_HOMOLOGACAO = [
    "valor total homologado", "valor global homologado", "total homologado",
    "valor total adjudicado", "valor global adjudicado", "total adjudicado",
    "valor total geral", "total geral", "montante total",
    "valor total da contratacao", "valor global da contratacao",
    "perfazendo o valor total", "perfazendo o valor global",
    "perfazendo a importancia", "no valor total de", "no valor global de",
    "homologo o valor", "homologo no valor", "adjudico o valor",
    "valor total do contrato", "valor global do contrato",
]

# Valores por item/lote — somar quando não houver total explícito
ROTULOS_ITEM_HOMOLOGACAO = [
    "valor total do item", "total do item", "valor do item",
    "valor total do lote", "total do lote", "valor do lote",
    "valor homologado do item", "valor adjudicado do item",
    "valor homologado do lote", "valor adjudicado do lote",
]

RE_ITEM_LOTE_LINHA = re.compile(
    r"(?:^|\n)\s*(?:item|lote)\s*(?:n[ºo°.]?\s*)?\d+"
    r"[^\n]{0,200}",
    re.IGNORECASE,
)

TIPOS_ESTIMADO = {
    "edital", "aviso", "termo_referencia", "etp", "dfd", "orcamento",
    "dispensa_inexig", "autorizacao",
}
TIPOS_HOMOLOGADO = {
    "homologacao", "adjudicacao", "contrato", "ata",
    "dispensa_inexig", "aceite_adesao",
}


def _para_float(txt: str) -> float | None:
    """Aceita BR (1.720.000,00) e US (1,720,000.00)."""
    if not txt:
        return None
    t = txt.strip()
    # US com milhar: 1,234.56
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?", t):
        try:
            return round(float(t.replace(",", "")), 2)
        except ValueError:
            return None
    # US simples com >= 4 dígitos antes do ponto: 50365.00
    if re.fullmatch(r"\d{4,}\.\d{1,2}", t):
        try:
            return round(float(t), 2)
        except ValueError:
            return None
    # BR
    if "," not in t and "." in t and t.count(".") == 1:
        # ambíguo: 1720.00 US curto — só se parte inteira >= 100
        esquerda = t.split(".", 1)[0]
        if esquerda.isdigit() and int(esquerda) >= 100:
            try:
                return round(float(t), 2)
            except ValueError:
                pass
    if "," not in t:
        t = t + ",00"
    try:
        return round(float(t.replace(".", "").replace(",", ".")), 2)
    except ValueError:
        return None


def _primeiro_valor(trecho: str) -> float | None:
    cands = []
    for rx in (RE_MOEDA_BR, RE_MOEDA_US, RE_MOEDA_RS):
        m = rx.search(trecho or "")
        if m:
            cands.append((m.start(), m.group(1)))
    if not cands:
        return None
    cands.sort()
    return _para_float(cands[0][1])


def _buscar(texto: str, rotulos: list[str], janela: int = 280) -> list[dict]:
    n = normaliza(texto)
    achados = []
    for rot in rotulos:
        inicio = 0
        while True:
            pos = n.find(rot, inicio)
            if pos < 0:
                break
            inicio = pos + len(rot)
            trecho_n = n[pos: pos + len(rot) + janela]
            val = _primeiro_valor(trecho_n)
            if val and 0 < val < 1e12:
                achados.append({
                    "valor": val,
                    "rotulo": rot,
                    "trecho": trecho_n[:140],
                    "pos": pos,
                    "pos_rel": pos / max(len(n), 1),
                })
    return achados


def formatar_front(valor: float | None) -> str:
    """Formato do Front: 1720000.00"""
    if valor is None:
        return ""
    return f"{valor:.2f}"


def _fallback_rs(texto: str, nome: str, tipo: str) -> list[dict]:
    """Se não achou rótulo, pega R$ explícitos (útil em atas de RP)."""
    achados = []
    for m in RE_MOEDA_RS.finditer(texto or ""):
        val = _para_float(m.group(1))
        if not val or val < 100:
            continue
        ini = max(0, m.start() - 40)
        trecho = re.sub(r"\s+", " ", (texto or "")[ini:m.end() + 10])[:140]
        achados.append({
            "valor": val,
            "rotulo": "r$",
            "trecho": trecho,
            "doc": nome,
            "tipo": tipo,
            "peso": 1,
        })
    return achados


def _valores_itens_homologacao(texto: str) -> list[float]:
    """Valores por item/lote no termo (para eventual soma), sem duplicar."""
    achados: list[tuple[int, float]] = []  # (pos, valor)

    def _registrar(pos: int, val: float) -> None:
        if val < 1:
            return
        for p, v in achados:
            if abs(p - pos) < 100 and abs(v - val) < 0.02:
                return  # mesma ocorrência
        achados.append((pos, val))

    for a in _buscar(texto, ROTULOS_ITEM_HOMOLOGACAO, janela=200):
        _registrar(int(a.get("pos") or 0), a["valor"])

    for m in RE_ITEM_LOTE_LINHA.finditer(texto or ""):
        trecho = m.group(0)
        nlin = normaliza(trecho)
        cands: list[float] = []
        for rx in (RE_MOEDA_BR, RE_MOEDA_US, RE_MOEDA_RS):
            for mm in rx.finditer(trecho):
                vv = _para_float(mm.group(1) if mm.lastindex else mm.group(0))
                if vv and vv >= 1:
                    cands.append(vv)
        if not cands:
            continue
        escolhido = max(cands)
        if "unitario" in nlin or " unit " in f" {nlin} ":
            maiores = [c for c in cands if c > min(cands) * 1.01]
            if maiores:
                escolhido = max(maiores)
        _registrar(m.start(), escolhido)

    return [v for _, v in achados]


def _total_bate_com_soma(valores: list[float]) -> float | None:
    """Se algum valor ≈ soma dos demais, é o total explícito no doc."""
    if len(valores) < 3:
        return None
    ordenados = sorted(valores, reverse=True)
    for i, cand in enumerate(ordenados):
        if cand < 100:
            continue
        partes = ordenados[i + 1:]
        if len(partes) < 2:
            continue
        soma = round(sum(partes), 2)
        if soma <= 0:
            continue
        if abs(soma - cand) <= max(0.02 * cand, 0.5):
            return round(cand, 2)
    return None


def _valor_do_termo_homologacao(texto: str, nome: str, tipo: str) -> dict | None:
    """
    No Termo de Homologação:
      1) se houver TOTAL no final (ou total que confere com a soma), use-o;
      2) senão, some os valores dos itens/lotes homologados.
    """
    if not (texto or "").strip():
        return None

    totais = _buscar(texto, ROTULOS_TOTAL_HOMOLOGACAO, janela=320)
    # reforça totais genéricos só no terço final do documento
    for a in _buscar(texto, ["valor total", "valor global", "total geral"], 280):
        if a["pos_rel"] >= 0.50:
            totais.append(a)

    def _score_total(a: dict) -> tuple:
        rot = a.get("rotulo") or ""
        fim = 3 if a.get("pos_rel", 0) >= 0.55 else (1 if a.get("pos_rel", 0) >= 0.35 else 0)
        rot_pts = 0
        if "homolog" in rot or "adjudic" in rot:
            rot_pts += 4
        if "total geral" in rot or "valor total homolog" in rot:
            rot_pts += 3
        if "global" in rot or "total" in rot:
            rot_pts += 1
        if "contrato" in rot:
            rot_pts += 1
        return (fim + rot_pts, a["valor"])

    melhor_total = max(totais, key=_score_total) if totais else None

    itens = _valores_itens_homologacao(texto)
    soma_itens = round(sum(itens), 2) if len(itens) >= 2 else None

    # Heurística: total impresso = soma dos valores menores no doc
    todos_rs: list[float] = []
    for rx in (RE_MOEDA_BR, RE_MOEDA_US, RE_MOEDA_RS):
        for m in rx.finditer(texto or ""):
            v = _para_float(m.group(1) if m.lastindex else m.group(0))
            if v and v >= 1:
                todos_rs.append(v)
    total_por_soma = _total_bate_com_soma(todos_rs)

    # 1) Total explícito que confere com soma dos itens
    if melhor_total and soma_itens:
        if abs(melhor_total["valor"] - soma_itens) <= max(0.05 * melhor_total["valor"], 1.0):
            return {
                "valor": round(melhor_total["valor"], 2),
                "rotulo": "total homologado (confere com soma dos itens)",
                "trecho": melhor_total.get("trecho") or "",
                "doc": nome,
                "tipo": tipo,
                "peso": 7,
            }

    # 2) Total no final / rótulo forte
    if melhor_total and (
        melhor_total.get("pos_rel", 0) >= 0.40
        or "homolog" in (melhor_total.get("rotulo") or "")
        or "adjudic" in (melhor_total.get("rotulo") or "")
        or "total geral" in (melhor_total.get("rotulo") or "")
    ):
        # se a soma dos itens for bem maior, o "total" pode ser unitário — prefira soma
        if soma_itens and soma_itens > melhor_total["valor"] * 1.5:
            return {
                "valor": soma_itens,
                "rotulo": "soma dos itens/lotes homologados",
                "trecho": "itens=%d total=%s" % (len(itens), formatar_front(soma_itens)),
                "doc": nome,
                "tipo": tipo,
                "peso": 6,
            }
        return {
            "valor": round(melhor_total["valor"], 2),
            "rotulo": melhor_total.get("rotulo") or "total homologado",
            "trecho": melhor_total.get("trecho") or "",
            "doc": nome,
            "tipo": tipo,
            "peso": 6,
        }

    # 3) Total que bate com a soma dos demais valores impressos
    if total_por_soma:
        return {
            "valor": total_por_soma,
            "rotulo": "total homologado (soma confere no documento)",
            "trecho": "total=%s" % formatar_front(total_por_soma),
            "doc": nome,
            "tipo": tipo,
            "peso": 6,
        }

    # 4) Sem total: soma dos itens/lotes
    if soma_itens:
        return {
            "valor": soma_itens,
            "rotulo": "soma dos itens/lotes homologados",
            "trecho": "itens=%d total=%s" % (len(itens), formatar_front(soma_itens)),
            "doc": nome,
            "tipo": tipo,
            "peso": 6,
        }

    # 5) Só um total fraco encontrado
    if melhor_total:
        return {
            "valor": round(melhor_total["valor"], 2),
            "rotulo": melhor_total.get("rotulo") or "valor no termo",
            "trecho": melhor_total.get("trecho") or "",
            "doc": nome,
            "tipo": tipo,
            "peso": 4,
        }

    return None


def _total_mapa_cotacao(texto: str, nome: str, tipo: str) -> dict | None:
    """
    Soma os totais de linha 'Valores médios : … 29,100.00' típicos de
    mapa de cotação / orçamento estimado (Jacareacanga etc.).
    """
    vals = []
    for m in RE_VALORES_MEDIOS.finditer(texto or ""):
        v = _para_float(m.group(1))
        if v and v >= 1:
            vals.append(v)
    if len(vals) < 2:
        # fallback: maior valor US/BR plausível no doc (>= 1000)
        cands = []
        for rx in (RE_MOEDA_US, RE_MOEDA_BR):
            for m in rx.finditer(texto or ""):
                v = _para_float(m.group(1))
                if v and v >= 1000:
                    cands.append(v)
        if not cands:
            return None
        # evita unitário: pega o maior (costuma ser total parcial/geral)
        total = max(cands)
        return {
            "valor": total,
            "rotulo": "maior valor no orçamento",
            "trecho": "max=%s" % formatar_front(total),
            "doc": nome,
            "tipo": tipo,
            "peso": 2,
        }
    total = round(sum(vals), 2)
    return {
        "valor": total,
        "rotulo": "soma valores médios (mapa de cotação)",
        "trecho": "linhas=%d total=%s" % (len(vals), formatar_front(total)),
        "doc": nome,
        "tipo": tipo,
        "peso": 4,
    }


def extrair_valores_dos_docs(cabecalhos: list[dict]) -> dict:
    """
    Lê valor estimado (edital/TR/ETP/orçamento…) e homologado
    (homologação/contrato…). Retorna strings no formato Front + metadados.
    """
    cand_est, cand_hom = [], []

    for doc in cabecalhos:
        texto = doc.get("texto") or ""
        if not texto.strip():
            continue
        tipo = doc.get("tipo") or "outro"
        nome = doc.get("nome") or ""

        if tipo in TIPOS_ESTIMADO or tipo in ("ata", "outro"):
            for a in _buscar(texto, ROTULOS_ESTIMADO):
                peso = 3 if tipo in (
                    "edital", "termo_referencia", "etp", "aviso", "orcamento"
                ) else 2
                if a["rotulo"] in ("valor total", "valor global"):
                    peso = max(peso - 1, 1)
                cand_est.append({**a, "doc": nome, "tipo": tipo, "peso": peso})

            # Planilha/mapa sem rótulo textual clássico
            if tipo == "orcamento" and not any(c["doc"] == nome for c in cand_est):
                tot = _total_mapa_cotacao(texto, nome, tipo)
                if tot:
                    cand_est.append(tot)

        if tipo in TIPOS_HOMOLOGADO or tipo in ("edital", "aviso"):
            # Termo de Homologação: total final OU soma dos itens
            if tipo == "homologacao":
                tot_h = _valor_do_termo_homologacao(texto, nome, tipo)
                if tot_h:
                    cand_hom.append(tot_h)
            for a in _buscar(texto, ROTULOS_HOMOLOGADO):
                peso = 3 if tipo in ("homologacao", "contrato", "adjudicacao") else 2
                if a["rotulo"] in ("total do vencedor",):
                    peso = 4
                if a["rotulo"] in (
                    "valor total homologado", "valor total adjudicado",
                    "valor total do contrato",
                ):
                    peso = 5
                if a["rotulo"] in ("valor total", "valor global", "no valor de"):
                    peso = max(peso - 1, 1)
                # Se já temos total/soma do termo, rótulos genéricos pesam menos
                if tipo == "homologacao" and any(
                    c.get("peso", 0) >= 6 and c.get("doc") == nome for c in cand_hom
                ):
                    peso = min(peso, 2)
                cand_hom.append({**a, "doc": nome, "tipo": tipo, "peso": peso})

        if tipo in ("ata", "contrato", "homologacao", "aceite_adesao") and not any(
            c["doc"] == nome for c in cand_hom
        ):
            cand_hom.extend(_fallback_rs(texto, nome, tipo))
        elif tipo == "homologacao" and not any(
            c["doc"] == nome and c.get("peso", 0) >= 4 for c in cand_hom
        ):
            # Sem total/soma claros: tenta R$ como apoio
            cand_hom.extend(_fallback_rs(texto, nome, tipo))

    def _melhor(cands):
        if not cands:
            return None
        return max(
            cands,
            key=lambda c: (c["peso"], 0 if c["rotulo"] == "r$" else 1, c["valor"]),
        )

    est = _melhor(cand_est)
    hom = _melhor(cand_hom)

    if est and hom and hom["valor"] > est["valor"] * 1.5:
        coerentes = [c for c in cand_hom if c["valor"] <= est["valor"] * 1.5]
        hom = _melhor(coerentes) or hom

    if hom and not est and hom.get("tipo") in ("ata", "aceite_adesao"):
        est = dict(hom)
        est["rotulo"] = (est.get("rotulo") or "") + " (também como estimado)"

    return {
        "valor_estimado": formatar_front(est["valor"] if est else None),
        "valor_homologado": formatar_front(hom["valor"] if hom else None),
        "valor_estimado_meta": {
            "doc": est["doc"], "rotulo": est["rotulo"], "trecho": est["trecho"],
        } if est else None,
        "valor_homologado_meta": {
            "doc": hom["doc"], "rotulo": hom["rotulo"], "trecho": hom["trecho"],
        } if hom else None,
    }
