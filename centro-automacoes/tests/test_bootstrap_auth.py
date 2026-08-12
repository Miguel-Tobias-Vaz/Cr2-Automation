"""Testes: bootstrap de env e config de auth."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.bootstrap_env import bootstrap_env
from backend.main import app


def test_bootstrap_loads_supabase_from_front_js(monkeypatch):
    monkeypatch.delenv("OPTO_SUPABASE_URL", raising=False)
    monkeypatch.delenv("OPTO_SUPABASE_ANON_KEY", raising=False)
    from backend import bootstrap_env as be

    js = be.ROOT / "front" / "supabase-config.js"
    if not js.is_file():
        pytest.skip("sem supabase-config.js local")
    be._load_supabase_js(js)
    assert os.environ.get("OPTO_SUPABASE_URL", "").startswith("https://")
    assert os.environ.get("OPTO_SUPABASE_ANON_KEY")


def test_auth_config_supabase_when_enabled(monkeypatch):
    monkeypatch.delenv("OPTO_AUTH", raising=False)
    monkeypatch.setenv("OPTO_SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("OPTO_SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.delenv("OPTO_USERS", raising=False)
    monkeypatch.setattr(auth, "USERS_FILE", auth.AUTH_DIR / "users.test-bootstrap.json")
    auth.reload_users()
    with TestClient(app) as client:
        r = client.get("/api/auth/config")
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "supabase"
        assert data["auth_required"] is True
        assert data["supabase_url"] == "https://test.supabase.co"
    auth.reload_users()


def test_auth_config_off_when_opt_auth_off(monkeypatch):
    monkeypatch.setenv("OPTO_AUTH", "off")
    monkeypatch.setenv("OPTO_SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("OPTO_SUPABASE_ANON_KEY", "test-anon-key")
    with TestClient(app) as client:
        r = client.get("/api/auth/config")
        assert r.json()["mode"] == "off"
        assert r.json()["auth_required"] is False
