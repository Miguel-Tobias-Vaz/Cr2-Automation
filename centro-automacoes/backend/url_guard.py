"""Bloqueia destinos internos (SSRF) em URLs enviadas pelo painel — só na VPS."""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any
from urllib.parse import urlparse

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
        "ip6-localhost",
        "ip6-loopback",
    }
)
_SKIP_URL_KEYS = frozenset({"ollama_url"})


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def check_http_url(value: str, *, field: str = "url") -> None:
    """Aceita path local; recusa http(s) para rede interna."""
    text = (value or "").strip()
    if not text.lower().startswith(("http://", "https://")):
        return
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("{0}: use apenas http ou https.".format(field))
    if parsed.username or parsed.password:
        raise ValueError("{0}: URL com usuário/senha não é permitida.".format(field))
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise ValueError("{0}: host inválido.".format(field))
    if host in _BLOCKED_HOSTS or host.endswith(".internal") or host.endswith(".localhost"):
        raise ValueError("{0}: destino interno não permitido neste servidor.".format(field))
    try:
        literal = ipaddress.ip_address(host)
        if _is_private_ip(str(literal)):
            raise ValueError(
                "{0}: IP interno/privado não permitido neste servidor.".format(field)
            )
        return
    except ValueError as exc:
        if "interno" in str(exc) or "privado" in str(exc):
            raise
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("{0}: host não encontrado.".format(field)) from None
    for info in infos:
        ip = info[4][0]
        if _is_private_ip(ip):
            raise ValueError(
                "{0}: o host resolve para um endereço interno — bloqueado na VPS.".format(
                    field
                )
            )


def _walk(obj: Any, path: str) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            if str(key) in _SKIP_URL_KEYS:
                continue
            _walk(val, "{0}.{1}".format(path, key))
        return
    if isinstance(obj, (list, tuple)):
        for i, val in enumerate(obj):
            _walk(val, "{0}[{1}]".format(path, i))
        return
    if not isinstance(obj, str):
        return
    for line in obj.splitlines():
        piece = line.split("|", 1)[0].strip()
        if piece.lower().startswith(("http://", "https://")):
            check_http_url(piece, field=path)


def prepare_job_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """VPS: valida URLs públicas, desliga ignorar_ssl e fixa Ollama local."""
    from backend.user_storage import is_local_mode

    out = dict(cfg or {})
    if is_local_mode():
        return out
    out["ignorar_ssl"] = False
    ollama = (os.getenv("OPTO_OLLAMA_URL") or "http://127.0.0.1:11434").strip()
    if "ollama_url" in out or out.get("refinar_ia") or out.get("refinar_ia_declaracao"):
        out["ollama_url"] = ollama
    _walk(out, "config")
    return out
