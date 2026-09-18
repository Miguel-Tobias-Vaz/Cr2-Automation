"""Redige credenciais em dumps de config (disco / logs)."""

from __future__ import annotations

from typing import Any

_SENSITIVE = ("senha", "password", "app_password", "token", "api_key", "secret")


def is_sensitive_key(key: str) -> bool:
    kl = str(key or "").lower()
    return any(s in kl for s in _SENSITIVE)


def redact_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Cópia com senhas/tokens trocados por *** (não altera o dict original)."""
    out: dict[str, Any] = {}
    for k, v in (cfg or {}).items():
        if is_sensitive_key(str(k)):
            out[k] = "***" if v else ""
        elif isinstance(v, dict):
            out[k] = redact_config(v)
        else:
            out[k] = v
    return out
