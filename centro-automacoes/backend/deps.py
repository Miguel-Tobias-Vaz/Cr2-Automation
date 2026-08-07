"""Dependências FastAPI (auth)."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from backend import auth


def get_optional_user(authorization: str | None = Header(None)) -> auth.Session | None:
    if not auth.is_enabled():
        return None
    token = auth.bearer_token(authorization)
    return auth.session_from_token(token)


def require_user(authorization: str | None = Header(None)) -> auth.Session:
    if not auth.is_enabled():
        return auth.Session(
            token="local",
            username="local",
            role="admin",
            expires_at=0,
        )
    sess = get_optional_user(authorization)
    if not sess:
        raise HTTPException(401, "Login necessário.")
    return sess


def require_admin(user: auth.Session = Depends(require_user)) -> auth.Session:
    if auth.is_enabled() and not auth.is_panel_admin(user):
        raise HTTPException(403, "Acesso restrito ao administrador principal.")
    return user
