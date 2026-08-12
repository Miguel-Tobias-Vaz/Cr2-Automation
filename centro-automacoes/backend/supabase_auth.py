"""Validação de sessão Supabase Auth + tabela public.profiles."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from backend.auth import Session

_CACHE_TTL_S = max(30, int(os.getenv("OPTO_SUPABASE_CACHE_S", "120")))


def supabase_url() -> str:
    return (os.getenv("OPTO_SUPABASE_URL") or "").rstrip("/")


def supabase_anon_key() -> str:
    return (os.getenv("OPTO_SUPABASE_ANON_KEY") or "").strip()


def is_configured() -> bool:
    return bool(supabase_url() and supabase_anon_key())


def map_role(role: str | None) -> str:
    """Supabase: admin | editor → painel: admin | user."""
    if (role or "").strip().lower() == "admin":
        return "admin"
    return "user"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "apikey": supabase_anon_key(),
    }


def session_from_token(token: str, sessions: dict, lock) -> Session | None:
    """Valida JWT no Supabase e lê perfil (role, ativo). Usa cache em memória."""
    from backend.auth import Session

    if not is_configured() or not token:
        return None

    now = time.time()
    with lock:
        cached = sessions.get(token)
        if cached and cached.expires_at > now:
            return cached

    try:
        user_resp = requests.get(
            f"{supabase_url()}/auth/v1/user",
            headers=_headers(token),
            timeout=12,
        )
        if user_resp.status_code != 200:
            with lock:
                sessions.pop(token, None)
            return None

        user = user_resp.json()
        uid = str(user.get("id") or "").strip()
        email = str(user.get("email") or "").strip()
        if not uid:
            return None

        profile_resp = requests.get(
            f"{supabase_url()}/rest/v1/profiles",
            params={"id": f"eq.{uid}", "select": "role,ativo,email,nome"},
            headers={**_headers(token), "Accept": "application/json"},
            timeout=12,
        )

        profile: dict = {}
        if profile_resp.status_code == 200:
            rows = profile_resp.json()
            if isinstance(rows, list) and rows:
                profile = rows[0]

        username = str(profile.get("email") or email or uid).strip()
        nome = str(profile.get("nome") or "").strip()
        role = map_role(profile.get("role"))

        sess = Session(
            token=token,
            username=username,
            role=role,
            expires_at=now + _CACHE_TTL_S,
            nome=nome,
            user_id=uid,
        )
        with lock:
            sessions[token] = sess
        return sess
    except requests.RequestException:
        return None
