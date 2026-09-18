"""Carrega opto.env e supabase-config.js antes de avaliar auth (dev + VPS)."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_BOOTSTRAPPED = False


def _load_dotenv_file(path: Path, *, override: bool = False) -> None:
    if not path.is_file():
        return
    try:
        # utf-8-sig remove BOM (ex.: arquivo salvo pelo Notepad/PowerShell)
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip().lstrip("\ufeff")
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].strip()
        if "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        key = key.strip().lstrip("\ufeff")
        val = val.strip()
        if not key:
            continue
        if not override and key in os.environ:
            continue
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        os.environ[key] = val


def _load_supabase_js(path: Path) -> None:
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    mapping = (
        ("SUPABASE_URL", "OPTO_SUPABASE_URL"),
        ("SUPABASE_ANON_KEY", "OPTO_SUPABASE_ANON_KEY"),
    )
    for js_var, env_key in mapping:
        if os.getenv(env_key):
            continue
        match = re.search(rf'window\.{js_var}\s*=\s*"([^"]+)"', text)
        if match:
            os.environ[env_key] = match.group(1)


def bootstrap_env() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True
    # deploy = defaults da VPS; opto.env local sobrescreve (PC pessoal)
    _load_dotenv_file(ROOT / "deploy" / "opto.env", override=False)
    _load_dotenv_file(ROOT / "opto.env", override=True)
    _load_supabase_js(ROOT / "front" / "supabase-config.js")
