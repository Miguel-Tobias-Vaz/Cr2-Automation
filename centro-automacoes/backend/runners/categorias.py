from __future__ import annotations

from backend.runners.base import SCRIPTS, apply_globals, load_module, run_main_with_logs


def run(job) -> None:
    cfg = job.config
    url = (cfg.get("url_categoria") or "").strip()
    site = (cfg.get("site") or "").strip()
    if not url or not site:
        raise ValueError("URL da categoria e Site são obrigatórios.")

    pasta = cfg.get("pasta_base") or r"C:\Downloads"
    anos_raw = (cfg.get("anos") or "").strip()
    anos_filtro = [a.strip() for a in anos_raw.split(",") if a.strip()] if anos_raw else []
    limite = int(cfg.get("limite_posts") or 0)
    ler_pdf = bool(cfg.get("ler_pdf", True))
    usar_ocr = bool(cfg.get("usar_ocr", True))
    motor_ocr = (cfg.get("motor_ocr") or "auto").strip().lower() or "auto"
    if motor_ocr in ("docling", "surya", "easyocr"):
        motor_ocr = "auto"
    refinar_ia = bool(cfg.get("refinar_ia", False))
    modelo_ia = (cfg.get("modelo_ia") or "llama3.2:3b").strip() or "llama3.2:3b"
    ollama_url = (cfg.get("ollama_url") or "http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434"
    ia_sempre = bool(cfg.get("ia_sempre", False))
    mod = load_module("download_categorias", SCRIPTS["categorias"])
    apply_globals(mod, {
        "PASTA_BASE": pasta,
        "URL_CATEGORIA": url,
        "SITE": site.rstrip("/"),
        "ANOS_FILTRO": anos_filtro,
        "LIMITE_POSTS": limite,
        "LER_PDF": ler_pdf,
        "USAR_OCR": usar_ocr,
        "MOTOR_OCR": motor_ocr,
        "REFINAR_IA": refinar_ia,
        "MODELO_IA": modelo_ia,
        "OLLAMA_URL": ollama_url,
        "IA_SEMPRE": ia_sempre,
    })
    if anos_filtro:
        job.emit("info", "Filtro de anos: {0}".format(", ".join(anos_filtro)))
    else:
        job.emit("info", "Filtro de anos: todos")
    job.emit("info", "Leitura PDF para nome: {0}".format("sim" if ler_pdf else "nao"))
    job.emit(
        "info",
        "OCR: {0}".format(
            "ligado ({0})".format(motor_ocr) if usar_ocr and ler_pdf else "desligado"
        ),
    )
    if refinar_ia:
        job.emit("info", "IA local: Ollama / {0} @ {1}".format(modelo_ia, ollama_url))
    else:
        job.emit("info", "IA local: desligada")
    run_main_with_logs(job, mod)
    job.result["pasta"] = pasta
    job.result["mensagem"] = "Downloads por categoria concluídos."
