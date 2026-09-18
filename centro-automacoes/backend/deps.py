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
    ticket: str | None,
) -> tuple[str, str] | None:
    """Retorna ('bearer'|'ticket', valor). JWT na querystring não é aceito."""
    token = auth.bearer_token(authorization)
    if token:
        return "bearer", token
    if ticket:
        stripped = ticket.strip()
        if stripped:
            return "ticket", stripped
    return None


def _session_from_parts(kind: str, value: str) -> auth.Session | None:
    if kind == "ticket":
        return auth.session_from_ticket(value)
    return auth.session_from_token(value)


def get_optional_user(
    authorization: str | None = Header(None),
    ticket: str | None = Query(None),
) -> auth.Session | None:
    if not auth.is_enabled():
        return _local_bypass_session()
    parts = _token_from_request(authorization, ticket)
    if not parts:
        return None
    return _session_from_parts(*parts)


def require_user(
    authorization: str | None = Header(None),
    ticket: str | None = Query(None),
) -> auth.Session:
    if not auth.is_enabled():
        return _local_bypass_session()
    parts = _token_from_request(authorization, ticket)
    sess = _session_from_parts(*parts) if parts else None
    if not sess:
        raise HTTPException(401, "Login necessário.")
    return sess


def require_admin(user: auth.Session = Depends(require_user)) -> auth.Session:
    if auth.is_enabled() and not auth.is_panel_admin(user):
        raise HTTPException(403, "Acesso restrito ao administrador principal.")
    return user
