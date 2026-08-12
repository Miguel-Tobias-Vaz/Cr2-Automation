"""Dependências FastAPI (auth)."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query

from backend import auth


def _local_bypass_session() -> auth.Session:
    return auth.Session(
        token="local",
        username="local",
        role="admin",
        expires_at=0,
    )


def _token_from_request(
    authorization: str | None,
    access_token: str | None,
) -> str | None:
    token = auth.bearer_token(authorization)
    if token:
        return token
    if access_token:
        stripped = access_token.strip()
        if stripped:
            return stripped
    return None


def get_optional_user(
    authorization: str | None = Header(None),
    access_token: str | None = Query(None),
) -> auth.Session | None:
    if not auth.is_enabled():
        return _local_bypass_session()
    token = _token_from_request(authorization, access_token)
    if not token:
        return None
    return auth.session_from_token(token)


def require_user(
    authorization: str | None = Header(None),
    access_token: str | None = Query(None),
) -> auth.Session:
    if not auth.is_enabled():
        return _local_bypass_session()
    token = _token_from_request(authorization, access_token)
    sess = auth.session_from_token(token) if token else None
    if not sess:
        raise HTTPException(401, "Login necessário.")
    return sess


def require_admin(user: auth.Session = Depends(require_user)) -> auth.Session:
    if auth.is_enabled() and not auth.is_panel_admin(user):
        raise HTTPException(403, "Acesso restrito ao administrador principal.")
    return user
