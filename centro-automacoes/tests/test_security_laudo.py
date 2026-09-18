"""Correções do laudo de segurança (fail-closed, ticket, docs)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.main import app
from backend.user_storage import owners_match


def test_vps_recusa_iniciar_sem_auth(monkeypatch):
    monkeypatch.setenv("OPTO_LOCAL", "0")
    monkeypatch.delenv("OPTO_SUPABASE_URL", raising=False)
    monkeypatch.delenv("OPTO_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("OPTO_USERS", raising=False)
    monkeypatch.delenv("OPTO_AUTH", raising=False)
    monkeypatch.setattr(auth, "USERS_FILE", auth.AUTH_DIR / "users.test-vps-empty.json")
    auth.reload_users()
    with pytest.raises(RuntimeError, match="Recusando iniciar"):
        auth.assert_production_auth()
    assert auth.is_enabled() is True
    auth.reload_users()


def test_vps_ignora_opto_auth_off(monkeypatch):
    monkeypatch.setenv("OPTO_LOCAL", "0")
    monkeypatch.setenv("OPTO_AUTH", "off")
    monkeypatch.setenv("OPTO_SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("OPTO_SUPABASE_ANON_KEY", "anon-test-key")
    assert auth.is_enabled() is True
    with TestClient(app) as client:
        r = client.get("/api/jobs")
        assert r.status_code == 401


def test_pages_escondidas_ate_auth(monkeypatch):
    monkeypatch.setenv("OPTO_LOCAL", "0")
    monkeypatch.setenv("OPTO_USERS", "admin:secret:admin")
    monkeypatch.delenv("OPTO_SUPABASE_URL", raising=False)
    monkeypatch.delenv("OPTO_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("OPTO_AUTH", raising=False)
    monkeypatch.setattr(auth, "USERS_FILE", auth.AUTH_DIR / "users.test-gate.json")
    auth.reload_users()
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "opto-auth-gate" in r.text
        assert "opto-auth-wait" in r.text
        login = client.get("/login.html")
        assert "opto-auth-gate" not in login.text
    auth.reload_users()


def test_owners_match_aceita_uuid_e_email():
    from backend.auth import Session

    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    sess = Session("t", "ana@empresa.com", "user", 0, user_id=uid)
    assert owners_match(uid, sess)
    assert owners_match("ana@empresa.com", sess)
    assert not owners_match("outra@empresa.com", sess)


def test_resposta_tem_csp(monkeypatch):
    monkeypatch.setenv("OPTO_LOCAL", "1")
    monkeypatch.setenv("OPTO_AUTH", "off")
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        csp = r.headers.get("content-security-policy") or r.headers.get(
            "Content-Security-Policy"
        )
        assert csp
        assert "default-src 'self'" in csp
        assert r.headers.get("x-content-type-options") == "nosniff"
