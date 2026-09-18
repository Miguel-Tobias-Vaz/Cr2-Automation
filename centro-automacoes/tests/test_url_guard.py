"""URL interna bloqueada na VPS; senhas redigidas."""

from __future__ import annotations

import pytest

from backend.secrets_redact import redact_config
from backend.url_guard import check_http_url, prepare_job_config


def test_redact_config_senha():
    out = redact_config({"usuario": "ana", "senha": "segredo", "app_password": "x"})
    assert out["usuario"] == "ana"
    assert out["senha"] == "***"
    assert out["app_password"] == "***"


def test_check_http_url_blocks_loopback():
    with pytest.raises(ValueError, match="interno|privado"):
        check_http_url("http://127.0.0.1/secret")
    with pytest.raises(ValueError, match="interno"):
        check_http_url("http://localhost/admin")
    with pytest.raises(ValueError, match="interno|privado"):
        check_http_url("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(ValueError, match="interno|privado"):
        check_http_url("http://10.0.0.8/x")
    check_http_url("C:\\Downloads\\planilha.xlsx")
    check_http_url("")


def test_prepare_job_config_vps_blocks(monkeypatch):
    monkeypatch.setenv("OPTO_LOCAL", "0")
    monkeypatch.setattr(
        "backend.url_guard.socket.getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    with pytest.raises(ValueError):
        prepare_job_config({"listagem": "http://127.0.0.1:8080/x"})
    cfg = prepare_job_config(
        {
            "listagem": "https://example.com/portal",
            "ignorar_ssl": True,
            "ollama_url": "http://169.254.169.254/",
            "refinar_ia": True,
        }
    )
    assert cfg["ignorar_ssl"] is False
    assert "169.254" not in (cfg.get("ollama_url") or "")
    assert "127.0.0.1" in cfg["ollama_url"]


def test_prepare_job_config_local_allows_intranet(monkeypatch):
    monkeypatch.setenv("OPTO_LOCAL", "1")
    cfg = prepare_job_config({"listagem": "http://192.168.0.10/transparencia"})
    assert "192.168.0.10" in cfg["listagem"]
