/** Explorador de arquivos do workspace (ES module). */
import { API, el, escapeHtml, formatBytes, formatDate } from "./core.js";
import { authFetch } from "./auth.js";
import { uploadFile } from "./upload.js";

const PICK_STORAGE = "opto-folder-pick";

function fileCtx(opts = {}) {
  const owner = (opts.owner || "").trim();
  return {
    owner,
    admin: Boolean(opts.admin && owner),
    readOnly: Boolean(opts.readOnly),
  };
}

function filesUrl(path, ctx, method = "GET") {
  if (ctx.admin) {
    const base = `${API}/api/admin/workspace/files?owner=${encodeURIComponent(ctx.owner)}`;
    if (method === "DELETE") return `${base}&path=${encodeURIComponent(path)}`;
    return path ? `${base}&path=${encodeURIComponent(path)}` : base;
  }
  if (method === "DELETE") {
    return `${API}/api/workspace/files?path=${encodeURIComponent(path)}`;
  }
  return path
    ? `${API}/api/workspace/files?path=${encodeURIComponent(path)}`
    : `${API}/api/workspace/files`;
}

export async function listAdminWorkspaceUsers() {
  const r = await authFetch(`${API}/api/admin/workspace/users`);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Falha ao listar usuários");
  return data.users || [];
}

export async function listWorkspaceFiles(path = "", opts = {}) {
  const ctx = fileCtx(opts);
  const r = await authFetch(filesUrl(path, ctx));
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Falha ao listar arquivos");
  return data;
}

export async function mkdirWorkspace(path, opts = {}) {
  const ctx = fileCtx(opts);
  const url = ctx.admin ? `${API}/api/admin/workspace/mkdir` : `${API}/api/workspace/mkdir`;
  const body = ctx.admin ? { owner: ctx.owner, path } : { path };
  const r = await authFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Falha ao criar pasta");
  return data;
}

export async function deleteWorkspacePath(path, opts = {}) {
  const ctx = fileCtx(opts);
  const r = await authFetch(filesUrl(path, ctx, "DELETE"), { method: "DELETE" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Falha ao apagar");
  return data;
}

export async function fetchOutputHints() {
  const r = await authFetch(`${API}/api/workspace/output-hints`);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return {};
  return data.hints || {};
}

export function pickFolderUrl(fieldId, returnPath) {
  const ret = returnPath || window.location.pathname;
  return `/arquivos.html?pick=${encodeURIComponent(fieldId)}&return=${encodeURIComponent(ret)}`;
}

export function storeFolderPick(fieldId, absPath) {
  try {
    sessionStorage.setItem(PICK_STORAGE, JSON.stringify({ fieldId, absPath }));
  } catch (_) {}
}

export function applyPendingFolderPick() {
  let raw;
  try {
    raw = sessionStorage.getItem(PICK_STORAGE);
  } catch (_) {
    return null;
  }
  if (!raw) return null;
  sessionStorage.removeItem(PICK_STORAGE);
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (_) {
    return null;
  }
  const node = el(payload.fieldId);
  if (node && payload.absPath) {
    node.value = payload.absPath;
    node.dispatchEvent(new Event("change", { bubbles: true }));
  }
  return payload;
}

export function bindFolderPickButtons(root = document) {
  root.querySelectorAll("[data-folder-pick]").forEach((btn) => {
    if (btn.dataset.boundPick) return;
    btn.dataset.boundPick = "1";
    btn.addEventListener("click", () => {
      const fieldId = btn.getAttribute("data-folder-pick");
      if (!fieldId) return;
      window.location.href = pickFolderUrl(fieldId);
    });
  });
}

function breadcrumbHtml(path, rootLabel = "Meu espaço") {
  const parts = (path || "").split("/").filter(Boolean);
  const crumbs = [{ label: rootLabel, path: "" }];
  let acc = "";
  parts.forEach((p) => {
    acc = acc ? `${acc}/${p}` : p;
    crumbs.push({ label: p, path: acc });
  });
  return crumbs
    .map((c, i) => {
      const isLast = i === crumbs.length - 1;
      const label = escapeHtml(c.label);
      if (isLast) return `<span class="files-crumb is-current">${label}</span>`;
      return `<button type="button" class="files-crumb" data-path="${escapeHtml(c.path)}">${label}</button>`;
    })
    .join('<span class="files-crumb-sep">/</span>');
}

export function mountFileBrowser(container, opts = {}) {
  const host = typeof container === "string" ? el(container) : container;
  if (!host) return null;

  const ctx = fileCtx(opts);
  const rootLabel = ctx.admin ? `Usuário: ${ctx.owner}` : "Meu espaço";
  const state = {
    path: opts.initialPath || "",
    pickField: opts.pickField || "",
    onSelect: opts.onSelect || null,
    ctx,
    rootLabel,
  };

  const showUpload = !ctx.readOnly && !ctx.admin;
  const showDelete = !ctx.readOnly;

  host.innerHTML = `
    <div class="files-browser">
      <div class="files-toolbar">
        <nav class="files-breadcrumbs" aria-label="Pastas"></nav>
        <div class="files-actions">
          <button type="button" class="btn btn-ghost btn-sm" data-files-up ${state.path ? "" : "hidden"}>↑ Subir</button>
          <button type="button" class="btn btn-ghost btn-sm" data-files-mkdir>Nova pasta</button>
          ${
            showUpload
              ? `<label class="btn btn-ghost btn-sm files-upload-btn">
            Enviar arquivo
            <input type="file" hidden data-files-upload multiple />
          </label>`
              : ""
          }
        </div>
      </div>
      <p class="files-status" hidden data-files-status></p>
      <div class="files-list-wrap">
        <table class="files-table">
          <thead><tr><th>Nome</th><th>Tamanho</th><th>Modificado</th><th></th></tr></thead>
          <tbody data-files-body><tr><td colspan="4">Carregando…</td></tr></tbody>
        </table>
      </div>
      ${
        state.pickField
          ? `<p class="files-pick-hint">Selecione uma pasta e clique em <strong>Usar</strong>.</p>`
          : ""
      }
      ${
        ctx.admin
          ? `<p class="files-pick-hint">Modo admin: visualização do workspace de <strong>${escapeHtml(ctx.owner)}</strong>.</p>`
          : ""
      }
    </div>`;

  const crumbsEl = host.querySelector(".files-breadcrumbs");
  const bodyEl = host.querySelector("[data-files-body]");
  const statusEl = host.querySelector("[data-files-status]");
  const upBtn = host.querySelector("[data-files-up]");
  const uploadInput = host.querySelector("[data-files-upload]");

  const setStatus = (msg, ok) => {
    if (!statusEl) return;
    statusEl.hidden = !msg;
    statusEl.textContent = msg || "";
    statusEl.classList.toggle("upload-status--ok", ok === true);
    statusEl.classList.toggle("upload-status--err", ok === false);
  };

  const render = async () => {
    bodyEl.innerHTML = `<tr><td colspan="4">Carregando…</td></tr>`;
    try {
      const data = await listWorkspaceFiles(state.path, state.ctx);
      state.path = data.path || "";
      crumbsEl.innerHTML = breadcrumbHtml(state.path, state.rootLabel);
      if (upBtn) upBtn.hidden = !state.path;

      const rows = (data.entries || []).map((entry) => {
        const icon = entry.kind === "dir" ? "📁" : "📄";
        const name = escapeHtml(entry.name);
        const size =
          entry.kind === "file" && entry.size != null ? formatBytes(entry.size) : "—";
        const modified = entry.modified ? formatDate(entry.modified * 1000) : "—";
        const pickBtn =
          entry.kind === "dir" && state.pickField
            ? `<button type="button" class="btn btn-primary btn-sm" data-use-path="${escapeHtml(entry.abs_path)}">Usar</button>`
            : "";
        const delBtn =
          !showDelete || entry.path === "jobs" || entry.path.startsWith("jobs/")
            ? ""
            : `<button type="button" class="btn btn-ghost btn-sm files-del" data-del-path="${escapeHtml(entry.path)}" title="Apagar">✕</button>`;
        const open =
          entry.kind === "dir"
            ? `<button type="button" class="files-link" data-open-path="${escapeHtml(entry.path)}">${icon} ${name}</button>`
            : `<span>${icon} ${name}</span>`;
        return `<tr>
          <td>${open}</td>
          <td>${size}</td>
          <td>${modified}</td>
          <td class="files-row-actions">${pickBtn}${delBtn}</td>
        </tr>`;
      });
      bodyEl.innerHTML = rows.length
        ? rows.join("")
        : `<tr><td colspan="4" class="files-empty">Pasta vazia.</td></tr>`;
    } catch (e) {
      bodyEl.innerHTML = `<tr><td colspan="4">${escapeHtml(e.message || e)}</td></tr>`;
      setStatus(String(e.message || e), false);
    }
  };

  host.addEventListener("click", async (ev) => {
    const open = ev.target.closest("[data-open-path]");
    if (open) {
      state.path = open.getAttribute("data-open-path") || "";
      render();
      return;
    }
    const crumb = ev.target.closest(".files-crumb[data-path]");
    if (crumb) {
      state.path = crumb.getAttribute("data-path") || "";
      render();
      return;
    }
    if (ev.target.closest("[data-files-up]")) {
      try {
        const data = await listWorkspaceFiles(state.path, state.ctx);
        state.path = data.parent || "";
        render();
      } catch (_) {}
      return;
    }
    const use = ev.target.closest("[data-use-path]");
    if (use) {
      const absPath = use.getAttribute("data-use-path");
      if (state.onSelect) state.onSelect(absPath);
      else if (state.pickField) {
        storeFolderPick(state.pickField, absPath);
        const ret = new URLSearchParams(window.location.search).get("return");
        window.location.href = ret || "/";
      }
      return;
    }
    const del = ev.target.closest("[data-del-path]");
    if (del) {
      const p = del.getAttribute("data-del-path");
      if (!p || !window.confirm(`Apagar "${p.split("/").pop()}"?`)) return;
      try {
        await deleteWorkspacePath(p, state.ctx);
        setStatus("Apagado.", true);
        render();
      } catch (e) {
        setStatus(String(e.message || e), false);
      }
    }
  });

  host.querySelector("[data-files-mkdir]")?.addEventListener("click", async () => {
    const name = window.prompt("Nome da nova pasta:");
    if (!name || !name.trim()) return;
    const base = state.path ? `${state.path}/` : "";
    try {
      await mkdirWorkspace(base + name.trim(), state.ctx);
      setStatus("Pasta criada.", true);
      render();
    } catch (e) {
      setStatus(String(e.message || e), false);
    }
  });

  uploadInput?.addEventListener("change", async () => {
    const files = uploadInput.files;
    if (!files || !files.length) return;
    setStatus("Enviando…", null);
    try {
      for (const file of files) {
        await uploadFile(file, { extract: false });
      }
      setStatus(`${files.length} arquivo(s) enviado(s).`, true);
      if (!state.path) state.path = "uploads";
      render();
    } catch (e) {
      setStatus(String(e.message || e), false);
    } finally {
      uploadInput.value = "";
    }
  });

  render();
  return { refresh: render, setPath: (p) => { state.path = p || ""; render(); } };
}
