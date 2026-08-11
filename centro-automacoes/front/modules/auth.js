/** Autenticação e fetch autenticado (ES module). */
import { API, el } from "./core.js";

const AUTH_TOKEN_KEY = "opto-auth-token";
const AUTH_REFRESH_KEY = "opto-auth-refresh";

function _storageGet(key) {
  try {
    const v = localStorage.getItem(key);
    if (v) return v;
  } catch (_) {}
  try {
    const v = sessionStorage.getItem(key);
    if (v) {
      try {
        localStorage.setItem(key, v);
        sessionStorage.removeItem(key);
      } catch (_) {}
      return v;
    }
  } catch (_) {}
  return "";
}

function _storageSet(key, value) {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch (_) {}
  try {
    sessionStorage.removeItem(key);
  } catch (_) {}
}

export function authToken() {
  return _storageGet(AUTH_TOKEN_KEY);
}

export function authHeaders(extra) {
  const h = { ...(extra || {}) };
  const t = authToken();
  if (t) h.Authorization = "Bearer " + t;
  return h;
}

export function streamUrl(path) {
  const t = authToken();
  if (!t) return `${API}${path}`;
  const sep = path.includes("?") ? "&" : "?";
  return `${API}${path}${sep}access_token=${encodeURIComponent(t)}`;
}

let _authRefreshPromise = null;

export async function refreshSupabaseSessionIfNeeded() {
  if (_authRefreshPromise) return _authRefreshPromise;
  _authRefreshPromise = (async () => {
    try {
      const cfg = await fetch(`${API}/api/auth/config`).then((r) => r.json());
      if (cfg.mode !== "supabase") return authToken();
      const url = window.SUPABASE_URL || cfg.supabase_url;
      const key = window.SUPABASE_ANON_KEY || cfg.supabase_anon_key;
      if (!url || !key) return authToken();
      if (!window.supabase) {
        await new Promise((resolve, reject) => {
          const s = document.createElement("script");
          s.src = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2";
          s.onload = resolve;
          s.onerror = reject;
          document.head.appendChild(s);
        });
      }
      const client = window.supabase.createClient(url, key, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: false,
          storage: window.localStorage,
        },
      });
      const { data, error } = await client.auth.getSession();
      if (error || !data || !data.session) {
        const refresh = _storageGet(AUTH_REFRESH_KEY);
        if (refresh) {
          const { data: refreshed, error: rErr } = await client.auth.refreshSession({
            refresh_token: refresh,
          });
          if (!rErr && refreshed && refreshed.session) {
            setAuthToken(refreshed.session.access_token);
            if (refreshed.session.refresh_token) {
              _storageSet(AUTH_REFRESH_KEY, refreshed.session.refresh_token);
            }
            return refreshed.session.access_token;
          }
        }
        return authToken();
      }
      const access = data.session.access_token;
      if (access) setAuthToken(access);
      if (data.session.refresh_token) {
        _storageSet(AUTH_REFRESH_KEY, data.session.refresh_token);
      }
      return access || authToken();
    } catch (_) {
      return authToken();
    } finally {
      _authRefreshPromise = null;
    }
  })();
  return _authRefreshPromise;
}

export function authFetch(url, opts) {
  const o = { ...(opts || {}) };
  o.headers = authHeaders(o.headers);
  return fetch(url, o).then(async (r) => {
    if (r.status !== 401) return r;
    const before = authToken();
    await refreshSupabaseSessionIfNeeded();
    const after = authToken();
    if (!after || after === before) return r;
    const retry = { ...(opts || {}) };
    retry.headers = authHeaders(retry.headers);
    return fetch(url, retry);
  });
}

export async function guardAuth() {
  if (location.pathname.includes("login.html")) return;
  try {
    await refreshSupabaseSessionIfNeeded();
    const r = await authFetch(`${API}/api/auth/me`);
    if (!r.ok) return;
    const d = await r.json();
    if (d.auth_required && !d.user) {
      const next = encodeURIComponent(location.pathname + location.search);
      location.href = `/login.html?next=${next}`;
    }
  } catch (_) {}
}

export function setAuthToken(token) {
  _storageSet(AUTH_TOKEN_KEY, token || "");
  if (!token) _storageSet(AUTH_REFRESH_KEY, "");
}

async function supabaseSignOutIfNeeded() {
  try {
    const cfg = await fetch(`${API}/api/auth/config`).then((r) => r.json());
    if (cfg.mode !== "supabase") return;
    const url = window.SUPABASE_URL || cfg.supabase_url;
    const key = window.SUPABASE_ANON_KEY || cfg.supabase_anon_key;
    if (!url || !key) return;
    if (!window.supabase) {
      await new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2";
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
      });
    }
    await window.supabase
      .createClient(url, key, {
        auth: { persistSession: true, storage: window.localStorage },
      })
      .auth.signOut();
  } catch (_) {}
}

export async function logout() {
  try {
    await authFetch(`${API}/api/auth/logout`, { method: "POST" });
  } catch (_) {}
  setAuthToken(null);
  await supabaseSignOutIfNeeded();
  location.href = "/login.html";
}

export function ensureLogoutButton() {
  if (el("btn-logout")) return;
  const pill = el("api-pill");
  if (!pill || !pill.parentNode) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.id = "btn-logout";
  btn.className = "btn btn-ghost btn-sm nav-logout";
  btn.textContent = "Sair";
  btn.hidden = true;
  btn.addEventListener("click", () => logout());
  pill.insertAdjacentElement("afterend", btn);
}
