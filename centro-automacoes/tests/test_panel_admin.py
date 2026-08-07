"""Admin principal (painel) vs usuários comuns."""

from __future__ import annotations

import pytest

from backend import auth


@pytest.fixture
def principal_env(monkeypatch):
    monkeypatch.delenv("OPTO_SUPABASE_URL", raising=False)
    monkeypatch.setenv("OPTO_PRINCIPAL_ADMIN", "boss@empresa.com,admin")
    monkeypatch.setenv("OPTO_USERS", "admin:secret:admin,maria:123:user")
    monkeypatch.setattr(auth, "USERS_FILE", auth.AUTH_DIR / "users.test-panel.json")
    auth.reload_users()
    yield
    monkeypatch.delenv("OPTO_PRINCIPAL_ADMIN", raising=False)
    monkeypatch.delenv("OPTO_USERS", raising=False)
    auth.reload_users()


def test_panel_admin_only_principal(principal_env):
    boss = auth.login("boss@empresa.com", "x")  # not in users - simulate supabase session
    # Simulate session directly
    s_boss = auth.Session("t1", "boss@empresa.com", "user", 0)
    s_admin = auth.Session("t2", "admin", "admin", 0)
    s_maria = auth.Session("t3", "maria", "user", 0)

    assert auth.is_panel_admin(s_boss)
    assert auth.is_panel_admin(s_admin)
    assert not auth.is_panel_admin(s_maria)
    assert auth.is_admin(s_boss)
    assert not auth.is_admin(s_maria)


def test_without_principal_falls_back_to_role(monkeypatch):
    monkeypatch.delenv("OPTO_PRINCIPAL_ADMIN", raising=False)
    monkeypatch.setenv("OPTO_USERS", "admin:secret:admin,maria:123:user")
    auth.reload_users()
    s = auth.Session("t", "maria", "user", 0)
    a = auth.Session("t", "admin", "admin", 0)
    assert not auth.is_panel_admin(s)
    assert auth.is_panel_admin(a)
