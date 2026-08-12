"""Autenticação multi-usuário (sessões em memória)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
AUTH_DIR = ROOT / "data" / "auth"
USERS_FILE = AUTH_DIR / "users.json"
SESSIONS_FILE = AUTH_DIR / "sessions.json"
SESSION_TTL_S = int(os.getenv("OPTO_SESSION_TTL_H", "168")) * 3600  # 7 dias


@dataclass
class User:
    username: str
    role: str  # "admin" | "user"
    salt: str
    password_hash: str

    def to_public(self) -> dict[str, str]:
        return {"username": self.username, "role": self.role}


@dataclass
class Session:
    token: str
    username: str
    role: str
    expires_at: float
    nome: str = ""
    user_id: str = ""

    def to_public(self) -> dict[str, str]:
        out = {"username": self.username, "role": self.role}
        if self.nome:
            out["nome"] = self.nome
        if self.user_id:
            out["id"] = self.user_id
        return out


_lock = threading.RLock()
_users: dict[str, User] = {}
_sessions: dict[str, Session] = {}


def _sessions_to_disk() -> None:
    """Persiste sessões locais para sobreviver a reinício do servidor."""
    try:
        if is_supabase():
            return
    except Exception:
        pass
    try:
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        now = time.time()
        payload = []
        with _lock:
            for sess in _sessions.values():
                if sess.expires_at <= now:
                    continue
                payload.append(
                    {
                        "token": sess.token,
                        "username": sess.username,
                        "role": sess.role,
                        "expires_at": sess.expires_at,
                        "nome": sess.nome,
                        "user_id": sess.user_id,
                    }
                )
        tmp = SESSIONS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(SESSIONS_FILE)
    except OSError:
        pass


def _sessions_from_disk() -> None:
    if not SESSIONS_FILE.is_file():
        return
    try:
        data = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, list):
        return
    now = time.time()
    loaded: dict[str, Session] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        token = str(item.get("token") or "").strip()
        username = str(item.get("username") or "").strip()
        if not token or not username:
            continue
        exp = float(item.get("expires_at") or 0)
        if exp <= now:
            continue
        loaded[token] = Session(
            token=token,
            username=username,
            role=str(item.get("role") or "user"),
            expires_at=exp,
            nome=str(item.get("nome") or ""),
            user_id=str(item.get("user_id") or ""),
        )
    with _lock:
        _sessions.update(loaded)


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return digest.hex()


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return salt, _hash_password(password, salt)


def verify_password(password: str, user: User) -> bool:
    return secrets.compare_digest(_hash_password(password, user.salt), user.password_hash)


def _parse_users_env(raw: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split(":")
        if len(bits) < 2:
            continue
        username = bits[0].strip()
        password = bits[1]
        role = bits[2].strip() if len(bits) > 2 else "user"
        if username and password:
            out.append({"username": username, "password": password, "role": role})
    return out


def _load_users_file() -> list[dict[str, Any]]:
    if not USERS_FILE.is_file():
        return []
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _save_users_file(users: list[User]) -> None:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "username": u.username,
            "role": u.role,
            "salt": u.salt,
            "password_hash": u.password_hash,
        }
        for u in users
    ]
    USERS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def bootstrap_from_env() -> None:
    raw = (os.getenv("OPTO_AUTH_BOOTSTRAP") or "").strip()
    if not raw or USERS_FILE.is_file():
        return
    bits = raw.split(":")
    if len(bits) < 2:
        return
    username = bits[0].strip()
    password = bits[1]
    role = bits[2].strip() if len(bits) > 2 else "admin"
    salt, pwd_hash = hash_password(password)
    _save_users_file([User(username, role, salt, pwd_hash)])


def reload_users() -> None:
    global _users
    bootstrap_from_env()
    loaded: dict[str, User] = {}

    for raw in _load_users_file():
        if not isinstance(raw, dict):
            continue
        username = str(raw.get("username") or "").strip()
        if not username:
            continue
        loaded[username] = User(
            username=username,
            role=str(raw.get("role") or "user"),
            salt=str(raw.get("salt") or ""),
            password_hash=str(raw.get("password_hash") or ""),
        )

    env_users = _parse_users_env(os.getenv("OPTO_USERS") or "")
    for item in env_users:
        salt, pwd_hash = hash_password(item["password"])
        loaded[item["username"]] = User(item["username"], item["role"], salt, pwd_hash)

    with _lock:
        _users = loaded


def is_supabase() -> bool:
    from backend import supabase_auth

    return supabase_auth.is_configured()


def is_enabled() -> bool:
    raw = (os.getenv("OPTO_AUTH") or "").strip().lower()
    if raw in ("0", "off", "false", "no", "disabled"):
        return False
    if is_supabase():
        return True
    with _lock:
        return bool(_users)


def login(username: str, password: str) -> Session | None:
    if is_supabase():
        return None
    with _lock:
        user = _users.get(username.strip())
        if not user or not verify_password(password, user):
            return None
        token = secrets.token_urlsafe(32)
        sess = Session(
            token=token,
            username=user.username,
            role=user.role,
            expires_at=time.time() + SESSION_TTL_S,
        )
        _sessions[token] = sess
        _sessions_to_disk()
        return sess


def logout(token: str | None) -> None:
    if not token:
        return
    with _lock:
        _sessions.pop(token, None)
    _sessions_to_disk()


def _clean_expired() -> None:
    now = time.time()
    changed = False
    with _lock:
        dead = [t for t, s in _sessions.items() if s.expires_at <= now]
        for t in dead:
            _sessions.pop(t, None)
            changed = True
    if changed:
        _sessions_to_disk()


def session_from_token(token: str | None) -> Session | None:
    if not token:
        return None
    if is_supabase():
        from backend import supabase_auth

        return supabase_auth.session_from_token(token, _sessions, _lock)
    _clean_expired()
    with _lock:
        sess = _sessions.get(token)
        if not sess or sess.expires_at <= time.time():
            return None
        return sess


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def principal_admin_users() -> set[str]:
    """E-mails/usuários que podem abrir o painel Admin (OPTO_PRINCIPAL_ADMIN)."""
    raw = (os.getenv("OPTO_PRINCIPAL_ADMIN") or "").strip()
    if not raw:
        return set()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def is_panel_admin(sess: Session | None) -> bool:
    """Painel Admin + fila global — administrador principal ou role admin."""
    if not sess:
        return False
    principals = principal_admin_users()
    user_key = sess.username.strip().lower()
    if principals:
        if user_key in principals:
            return True
        # Supabase: role admin no perfil também abre o painel
        return sess.role == "admin"
    return sess.role == "admin"


def is_admin(sess: Session | None) -> bool:
    """Privilégios operacionais (cancelar job alheio, etc.)."""
    if principal_admin_users():
        return is_panel_admin(sess)
    return bool(sess and sess.role == "admin")


def can_cancel_job(sess: Session | None, owner: str | None) -> bool:
    if not is_enabled():
        return True
    if not sess:
        return False
    if is_panel_admin(sess):
        return True
    if not owner:
        return False
    return sess.username.strip().lower() == owner.strip().lower()


reload_users()
try:
    _sessions_from_disk()
except Exception:
    pass
