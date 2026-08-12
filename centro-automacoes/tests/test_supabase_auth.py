"""Testes de auth Supabase (mock HTTP)."""

from __future__ import annotations

import pytest

from backend import auth
from backend import supabase_auth


@pytest.fixture
def supabase_env(monkeypatch):
    monkeypatch.delenv("OPTO_USERS", raising=False)
    monkeypatch.setenv(
        "OPTO_SUPABASE_URL", "https://test.supabase.co"
    )
    monkeypatch.setenv("OPTO_SUPABASE_ANON_KEY", "anon-test-key")
    auth._sessions.clear()
    yield
    monkeypatch.delenv("OPTO_SUPABASE_URL", raising=False)
    monkeypatch.delenv("OPTO_SUPABASE_ANON_KEY", raising=False)
    auth._sessions.clear()
    auth.reload_users()


def test_map_role():
    assert supabase_auth.map_role("admin") == "admin"
    assert supabase_auth.map_role("editor") == "user"
    assert supabase_auth.map_role(None) == "user"


def test_is_enabled_supabase(supabase_env):
    assert auth.is_supabase()
    assert auth.is_enabled()
    assert auth.login("x", "y") is None


def test_session_from_token_supabase_ok(supabase_env, monkeypatch):
    calls = []

    class FakeResp:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/auth/v1/user"):
            return FakeResp(
                200,
                {"id": "uid-1", "email": "ana@empresa.com"},
            )
        if "/rest/v1/profiles" in url:
            return FakeResp(
                200,
                [{"role": "editor", "ativo": True, "email": "ana@empresa.com", "nome": "Ana"}],
            )
        return FakeResp(404, {})

    monkeypatch.setattr(supabase_auth.requests, "get", fake_get)

    sess = auth.session_from_token("jwt-token-abc")
    assert sess is not None
    assert sess.username == "ana@empresa.com"
    assert sess.role == "user"
    assert sess.nome == "Ana"
    assert auth.session_from_token("jwt-token-abc") is sess


def test_session_without_profile(supabase_env, monkeypatch):
    class FakeResp:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, **kwargs):
        if url.endswith("/auth/v1/user"):
            return FakeResp(200, {"id": "uid-2", "email": "novo@x.com"})
        return FakeResp(200, [])

    monkeypatch.setattr(supabase_auth.requests, "get", fake_get)
    sess = auth.session_from_token("tok-new")
    assert sess is not None
    assert sess.username == "novo@x.com"
    assert sess.role == "user"
