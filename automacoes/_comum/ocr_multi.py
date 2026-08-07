# -*- coding: utf-8 -*-
"""
OCR multi-motor compartilhado (todas as automacoes).

Estratégia leve (rápido + qualidade suficiente):
  Auto = Tesseract primeiro (leve). PaddleOCR só se o texto vier fraco
  e o pacote estiver instalado — e só nas primeiras páginas.
  EasyOCR removido (pesado demais em CPU).

Instale no venv do painel, por exemplo:
  pip install pymupdf pytesseract pdf2image
  # opcional (mais pesado): paddlepaddle paddleocr
"""

from __future__ import annotations

import io
import os
import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Caminhos Tesseract / Poppler
# ---------------------------------------------------------------------------

def configurar_caminhos_ocr() -> str | None:
    candidatos_tess = [
        os.environ.get("TESSERACT_CMD") or "",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        shutil.which("tesseract") or "",
    ]
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        winget = os.path.join(local, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget):
            try:
                for nome in os.listdir(winget):
                    if "Tesseract" in nome:
                        cand = os.path.join(winget, nome, "tesseract.exe")
                        if os.path.isfile(cand):
                            candidatos_tess.append(cand)
            except OSError:
                pass
    tess = next((c for c in candidatos_tess if c and os.path.isfile(c)), None)
    if tess:
        try:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = tess
        except Exception:
            pass

    # tessdata: Program Files ou cópia do usuário (sem admin)
    candidatos_data = [
        os.environ.get("TESSDATA_PREFIX") or "",
        r"C:\Program Files\Tesseract-OCR\tessdata",
        r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
    ]
    if local:
        candidatos_data.append(os.path.join(local, "tesseract-tessdata"))
    for pasta in candidatos_data:
        if not pasta:
            continue
        por = os.path.join(pasta, "por.traineddata")
        eng = os.path.join(pasta, "eng.traineddata")
        if os.path.isfile(por) or os.path.isfile(eng):
            # Tesseract exige o diretório pai de tessdata/ OU o próprio tessdata
            # conforme versão — apontamos para a pasta que contém os .traineddata
            os.environ["TESSDATA_PREFIX"] = pasta
            break

    pops: list[str] = [
        r"C:\Program Files\poppler\Library\bin",
        r"C:\Program Files\poppler\bin",
        r"C:\poppler\Library\bin",
        r"C:\poppler\bin",
    ]
    if local:
        winget = os.path.join(local, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget):
            try:
                for nome in os.listdir(winget):
                    if "Poppler" in nome or "poppler" in nome.lower():
                        for sub in ("Library\\bin", "bin"):
                            pops.append(os.path.join(winget, nome, sub))
            except OSError:
                pass
    for pop in pops:
        if os.path.isfile(os.path.join(pop, "pdftoppm.exe")):
            if pop not in os.environ.get("PATH", ""):
                os.environ["PATH"] = pop + os.pathsep + os.environ.get("PATH", "")
            return pop
    return None


# ---------------------------------------------------------------------------
# Render PDF → imagens (PIL)
# ---------------------------------------------------------------------------

def renderizar_paginas(caminho: Path, dpi: int = 180, max_paginas: int = 4):
    """Lista de PIL.Image. Prefere PyMuPDF; senão pdf2image+Poppler.

    Defaults baixos (dpi/páginas) — OCR precisa ser rápido; a IA confirma valores.
    """
    caminho = Path(caminho)
    max_paginas = max(1, int(max_paginas or 4))
    # 1) PyMuPDF
    try:
        import fitz
        from PIL import Image

        doc = fitz.open(str(caminho))
        imgs = []
        try:
            for i, page in enumerate(doc):
                if i >= max_paginas:
                    break
                pix = page.get_pixmap(dpi=dpi)
                imgs.append(Image.open(io.BytesIO(pix.tobytes("png"))))
        finally:
            doc.close()
        if imgs:
            return imgs
    except Exception:
        pass

    # 2) pdf2image
    try:
        from pdf2image import convert_from_path

        poppler = configurar_caminhos_ocr()
        kwargs = {"dpi": dpi, "last_page": max_paginas}
        if poppler:
            kwargs["poppler_path"] = poppler
        return list(convert_from_path(str(caminho), **kwargs))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Qualidade do texto (para escolher o melhor motor)
# ---------------------------------------------------------------------------

_RE_MOEDA_MILHAR = re.compile(r"\d{1,3}(?:\.\d{3})+,\d{2}")
_RE_MOEDA_QUALQUER = re.compile(r"\d{1,3}(?:\.\d{3})+,\d{2}|\d{2,},\d{2}")
_RE_BOM = re.compile(
    r"[a-zA-Z0-9áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇàèìòùÀÈÌÒÙ ,.;:()\-/\nR$%]"
)


def qualidade_texto(texto: str) -> float:
    if not texto or not texto.strip():
        return 0.0
    t = texto.strip()
    # Fonte embutida quebrada (só cid:) — inútil para extração
    if "(cid:" in t.lower() and len(re.findall(r"[A-Za-z]{3,}", t)) < 8:
        return 0.0
    bons = len(_RE_BOM.findall(t))
    prop = bons / max(len(t), 1)
    milhares = len(_RE_MOEDA_MILHAR.findall(t))
    moedas = len(_RE_MOEDA_QUALQUER.findall(t))
    # premia texto com valores no formato 318.390,34
    bonus = milhares * 80 + moedas * 25 + min(len(t), 4000) * 0.02
    palavras_chave = sum(
        1
        for k in (
            "duodecimo", "duodécimo", "repasse", "valor", "camara", "câmara",
            "recibo", "portaria", "diaria", "diária", "lei", "decreto",
            "contrato", "edital", "licitacao", "licitação", "sessao", "sessão",
        )
        if k in t.lower()
    )
    bonus += palavras_chave * 40
    # datas DD/MM/AAAA ajudam (recibo/portaria)
    datas = len(re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", t))
    bonus += min(datas, 4) * 30
    return prop * 100 + bonus


def texto_nativo_insuficiente(texto: str, *, min_chars: int = 40) -> bool:
    """True se o texto nativo não serve (escaneado / cid / só cabeçalho)."""
    if not (texto or "").strip():
        return True
    util = re.sub(r"\s+", "", texto)
    if len(util) < min_chars:
        return True
    if qualidade_texto(texto) < 55:
        return True
    low = texto.lower()
    if "(cid:" in low:
        return True
    tem_data = bool(re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", texto))
    tem_moeda = bool(_RE_MOEDA_MILHAR.search(texto) or _RE_MOEDA_QUALQUER.search(texto))
    # Só timbre/endereço da Câmara, sem data nem valor → corpo é imagem
    if not tem_data and not tem_moeda and len(util) < 900:
        return True
    return False


# ---------------------------------------------------------------------------
# Motores
# ---------------------------------------------------------------------------

_PADDLE = None
OCR_MAX_PAG_PADRAO = 4
OCR_DPI_TESSERACT = 180
OCR_DPI_PADDLE = 160
# Score mínimo para aceitar Tesseract sem escalar ao Paddle
_SCORE_TESSERACT_OK = 110


def _ocr_paddle(caminho: Path, max_paginas: int = 3) -> str:
    global _PADDLE
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return ""
    try:
        if _PADDLE is None:
            try:
                _PADDLE = PaddleOCR(use_angle_cls=False, lang="pt", show_log=False)
            except TypeError:
                try:
                    _PADDLE = PaddleOCR(use_angle_cls=False, lang="pt")
                except TypeError:
                    _PADDLE = PaddleOCR(lang="pt")
        imgs = renderizar_paginas(
            caminho, dpi=OCR_DPI_PADDLE, max_paginas=max(1, int(max_paginas or 3))
        )
        if not imgs:
            return ""
        partes = []
        for img in imgs:
            import numpy as np

            arr = np.array(img.convert("RGB"))
            try:
                out = _PADDLE.ocr(arr, cls=False)
            except TypeError:
                out = _PADDLE.ocr(arr)
            linhas = []
            for block in out or []:
                if not block:
                    continue
                for line in block:
                    try:
                        linhas.append(str(line[1][0]))
                    except Exception:
                        continue
            partes.append("\n".join(linhas))
        return "\n".join(partes)
    except Exception as e:
        _aviso_ocr_uma_vez("fail:paddleocr", f"  [AVISO] PaddleOCR falhou: {str(e)[:100]}")
        return ""


def _ocr_tesseract(caminho: Path, max_paginas: int = OCR_MAX_PAG_PADRAO) -> str:
    configurar_caminhos_ocr()
    try:
        import pytesseract
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            _aviso_ocr_uma_vez(
                "fail:tesseract-bin",
                "  [AVISO] Tesseract não instalado (só o pacote Python) — OCR pulado.",
            )
            return ""
    except ImportError:
        return ""
    imgs = renderizar_paginas(
        caminho,
        dpi=OCR_DPI_TESSERACT,
        max_paginas=max(1, int(max_paginas or OCR_MAX_PAG_PADRAO)),
    )
    if not imgs:
        return ""
    partes = []
    try:
        for img in imgs:
            try:
                partes.append(
                    pytesseract.image_to_string(img, lang="por", config="--oem 1 --psm 6")
                )
            except Exception:
                partes.append(
                    pytesseract.image_to_string(img, lang="eng", config="--oem 1 --psm 6")
                )
        return "\n".join(partes)
    except Exception as e:
        _aviso_ocr_uma_vez("fail:tesseract", f"  [AVISO] Tesseract falhou: {str(e)[:100]}")
        return ""


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

_OCR_AVISOS_JA: set[str] = set()


def _aviso_ocr_uma_vez(chave: str, msg: str) -> None:
    """Evita spam: mesmo aviso no máximo 1× por execução."""
    if chave in _OCR_AVISOS_JA:
        return
    _OCR_AVISOS_JA.add(chave)
    print(msg)


_MOTORES: list[tuple[str, Callable[..., str]]] = [
    ("tesseract", _ocr_tesseract),
    ("paddleocr", _ocr_paddle),
]

MOTORES_NOMES = tuple(n for n, _ in _MOTORES)
MOTORES = MOTORES_NOMES
MOTOR_PADRAO = "auto"


@lru_cache(maxsize=1)
def motores_disponiveis() -> tuple[str, ...]:
    disponiveis = []
    try:
        configurar_caminhos_ocr()
        import pytesseract

        pytesseract.get_tesseract_version()
        disponiveis.append("tesseract")
    except Exception:
        pass
    try:
        __import__("paddleocr")
        disponiveis.append("paddleocr")
    except Exception:
        pass
    return tuple(disponiveis)


def _max_paginas_efetivo(max_paginas: int | None) -> int:
    if max_paginas is None or int(max_paginas) <= 0:
        return OCR_MAX_PAG_PADRAO
    return max(1, int(max_paginas))


def ocr_melhor(
    caminho: Path | str,
    motor: str = "auto",
    max_paginas: int | None = None,
) -> str:
    """
    Extrai texto do PDF.
    motor: auto | tesseract | paddleocr
    Auto = Tesseract (rápido); Paddle só se o score for baixo.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        return ""

    if motor in ("docling", "surya", "easyocr"):
        _aviso_ocr_uma_vez(
            f"legacy:{motor}",
            f"  [AVISO] Motor '{motor}' removido — usando auto (Tesseract).",
        )
        motor = "auto"

    max_p = _max_paginas_efetivo(max_paginas)
    disponiveis = set(motores_disponiveis())

    if motor and motor != "auto":
        fn = dict(_MOTORES).get(motor)
        if not fn:
            _aviso_ocr_uma_vez(
                f"unk:{motor}",
                f"  [AVISO] Motor OCR desconhecido: {motor}",
            )
            return ""
        if motor not in disponiveis:
            _aviso_ocr_uma_vez(
                f"miss:{motor}",
                f"  [AVISO] Motor '{motor}' indisponível — OCR pulado.",
            )
            return ""
        try:
            return fn(caminho, max_paginas=max_p) or ""
        except TypeError:
            return fn(caminho) or ""
        except Exception as e:
            _aviso_ocr_uma_vez(f"fail:{motor}", f"  [AVISO] {motor}: {str(e)[:100]}")
            return ""

    # --- AUTO: só Tesseract (leve). Paddle só com motor=paddleocr ---
    if "tesseract" in disponiveis:
        try:
            return _ocr_tesseract(caminho, max_paginas=max_p) or ""
        except Exception as e:
            _aviso_ocr_uma_vez("fail:tesseract", f"  [AVISO] tesseract: {str(e)[:80]}")
            return ""

    _aviso_ocr_uma_vez(
        "miss:tesseract-auto",
        "  [AVISO] Tesseract não instalado — OCR pulado "
        "(instale o Tesseract; a IA confirma os campos).",
    )
    return ""


def ocr_pdf(caminho, motor="auto", max_paginas: int | None = None):
    """Alias publico de ocr_melhor."""
    return ocr_melhor(caminho, motor=motor or "auto", max_paginas=max_paginas)


def obter_texto_pdf(caminho, *, usar_ocr=True, motor="auto", min_nativo=40, cache=True):
    """Retorna (texto, origem) — nativo | ocr | ocr-cache | vazio."""
    caminho = Path(caminho)
    if not caminho.is_file():
        return "", "vazio"
    cache_path = caminho.with_suffix(".ocr.txt")
    if cache and cache_path.is_file():
        try:
            cached = cache_path.read_text(encoding="utf-8")
            if not texto_nativo_insuficiente(cached, min_chars=min_nativo):
                return cached, "ocr-cache"
        except Exception:
            pass
    nativo = ler_texto_nativo(caminho)
    if not texto_nativo_insuficiente(nativo, min_chars=min_nativo):
        return nativo, "nativo"
    if not usar_ocr:
        return nativo or "", "nativo" if nativo else "vazio"
    ocr = ocr_pdf(caminho, motor=motor)
    if ocr.strip():
        if cache:
            try:
                cache_path.write_text(ocr, encoding="utf-8")
            except Exception:
                pass
        return ocr, "ocr"
    return nativo or "", "nativo" if nativo else "vazio"


def ler_texto_nativo(caminho, max_paginas=12):
    caminho = Path(caminho)
    try:
        import pdfplumber
        with pdfplumber.open(str(caminho)) as pdf:
            pages = pdf.pages[: max(1, max_paginas)]
            return "\n".join((p.extract_text() or "") for p in pages)
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(caminho))
        return "\n".join(
            (p.extract_text() or "") for p in reader.pages[: max(1, max_paginas)]
        )
    except Exception:
        return ""


def obter_texto_de_bytes(
    data, *, usar_ocr=True, motor="auto", min_nativo=40, max_paginas_nativo=12
):
    """Bytes PDF → (texto, origem). OCR via tempfile se nativo insuficiente."""
    import tempfile

    if not data or data[:4] != b"%PDF":
        return "", "vazio"
    nativo = ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        nativo = "\n".join(
            (p.extract_text() or "")
            for p in reader.pages[: max(1, max_paginas_nativo)]
        )
    except Exception:
        pass
    if not texto_nativo_insuficiente(nativo, min_chars=min_nativo):
        return nativo, "nativo"
    if not usar_ocr:
        return nativo or "", "nativo" if nativo else "vazio"
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        Path(tmp).write_bytes(data)
        ocr = ocr_pdf(tmp, motor=motor)
        if ocr.strip():
            return ocr, "ocr"
    except Exception as e:
        _aviso_ocr_uma_vez("fail:bytes", f"  [AVISO] OCR em bytes falhou: {str(e)[:100]}")
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return nativo or "", "nativo" if nativo else "vazio"
