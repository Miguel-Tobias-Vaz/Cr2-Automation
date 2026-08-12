"""Smoke test: páginas HTML e APIs essenciais (modo aberto)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.main import app

PAGES = [
    "/",
    "/login.html",
    "/extrair.html",
    "/publicar.html",
    "/documentos.html",
    "/categorias.html",
    "/normas.html",
    "/licitacoes.html",
    "/tcm-licitacoes.html",
    "/repasses.html",
    "/publicacao.html",
    "/sessao.html",
    "/pub-repasses.html",
    "/mapa.html",
    "/arquivos.html",
    "/admin.html",
]

APIS_OPEN = [
    ("/api/health", 200),
    ("/api/auth/config", 200),
    ("/api/auth/me", 200),
    ("/api/jobs", 200),
    ("/api/queue", 200),
    ("/api/workspace", 200),
    ("/api/admin/overview", 200),
]


@pytest.fixture
def open_client(monkeypatch):
    monkeypatch.setenv("OPTO_AUTH", "off")
    monkeypatch.delenv("OPTO_SUPABASE_URL", raising=False)
    monkeypatch.delenv("OPTO_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("OPTO_USERS", raising=False)
    monkeypatch.delenv("OPTO_REQUIRE_AUTH", raising=False)
    monkeypatch.setenv("OPTO_LOCAL", "1")
    monkeypatch.setattr(auth, "USERS_FILE", auth.AUTH_DIR / "users.test-smoke.json")
    auth.reload_users()
    with TestClient(app) as client:
        yield client
    auth.reload_users()


def test_pages_load(open_client):
    for path in PAGES:
        r = open_client.get(path)
        assert r.status_code == 200, path
        assert "text/html" in r.headers.get("content-type", "")
        assert "shared.js" in r.text, f"sem shared.js: {path}"


def test_index_html_redirect(open_client):
    r = open_client.get("/index.html", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/"


def test_apis_open_mode(open_client):
    for path, code in APIS_OPEN:
        r = open_client.get(path)
        assert r.status_code == code, path


def test_auth_me_open_has_user(open_client):
    data = open_client.get("/api/auth/me").json()
    assert data["auth_required"] is False
    assert data.get("user") is not None


def test_workspace_files_open(open_client):
    r = open_client.get("/api/workspace/files")
    # Modo local: explorador só na VPS; em OPTO_LOCAL=1 retorna 400
    assert r.status_code in (200, 400)
