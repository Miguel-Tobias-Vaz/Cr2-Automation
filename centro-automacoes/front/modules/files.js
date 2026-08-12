/** Explorador de arquivos do workspace (ES module). */
import { API, el, escapeHtml, formatBytes, formatDate } from "./core.js";
import { authFetch, authToken } from "./auth.js";
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

function folderSizeUrl(path, ctx) {
  if (ctx.admin) {
    return (
      `${API}/api/admin/workspace/files/folder-size?owner=${encodeURIComponent(ctx.owner)}` +
      `&path=${encodeURIComponent(path)}`
    );
  }
  return `${API}/api/workspace/files/folder-size?path=${encodeURIComponent(path)}`;
}

async function fetchWorkspaceFolderSize(path, ctx) {
  const r = await authFetch(folderSizeUrl(path, ctx));
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Falha ao calcular tamanho");
  return data;
}

function formatEntrySize(entry) {
  if (entry.size == null) return entry.kind === "dir" ? "…" : "—";
  return formatBytes(entry.size) + (entry.size_partial ? "+" : "");
}

async function loadFolderSizes(paths, ctx, bodyEl) {
  const listId = ++loadFolderSizes._seq;
  for (const relPath of paths) {
    if (listId !== loadFolderSizes._seq) return;
    const cell = bodyEl.querySelector(`[data-size-path="${CSS.escape(relPath)}"]`);
    if (!cell) continue;
    try {
      const data = await fetchWorkspaceFolderSize(relPath, ctx);
      if (listId !== loadFolderSizes._seq) return;
      if (data.size == null) {
        cell.textContent = "—";
      } else {
        cell.textContent = formatBytes(data.size) + (data.size_partial ? "+" : "");
      }
    } catch (_) {
      if (listId !== loadFolderSizes._seq) return;
      cell.textContent = "—";
    }
  }
}
loadFolderSizes._seq = 0;

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

export function workspaceDownloadUrl(path, opts = {}, lot = 1) {
  const ctx = fileCtx(opts);
  const rel = (path || "").trim();
  if (!rel) return "";
  let url;
  if (ctx.admin) {
    url =
      `${API}/api/admin/workspace/files/download?owner=${encodeURIComponent(ctx.owner)}` +
      `&path=${encodeURIComponent(rel)}`;
  } else {
    url = `${API}/api/workspace/files/download?path=${encodeURIComponent(rel)}`;
  }
  url += `&lot=${Math.max(1, Number(lot) || 1)}`;
  const token = authToken();
  if (token) {
    url += `&access_token=${encodeURIComponent(token)}`;
  }
  return url;
}

function downloadPlanUrl(path, ctx) {
  if (ctx.admin) {
    return (
      `${API}/api/admin/workspace/files/download/plan?owner=${encodeURIComponent(ctx.owner)}` +
      `&path=${encodeURIComponent(path)}`
    );
  }
  return `${API}/api/workspace/files/download/plan?path=${encodeURIComponent(path)}`;
}

async function fetchDownloadPlan(path, ctx) {
  const r = await authFetch(downloadPlanUrl(path, ctx));
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Falha ao planejar download");
  return data;
}

function triggerDownload(path, ctx, lot = 1) {
  const url = workspaceDownloadUrl(path, ctx, lot);
  if (!url) return;
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function closeLotsModal() {
  document.querySelector(".files-lots-backdrop")?.remove();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function renderLotsRows(lots) {
  return (lots || [])
    .map((lot) => {
      const units = (lot.units || []).slice(0, 8);
      const more = (lot.units || []).length > 8 ? ` +${lot.units.length - 8}` : "";
      const unitList = units.map((u) => escapeHtml(u)).join(", ") + more;
      const status = lot.cached
        ? `<span class="files-lots-badge files-lots-badge--ok">Pronto</span>`
        : `<span class="files-lots-badge">Gerando…</span>`;
      return `<li class="files-lots-item">
        <div class="files-lots-item-head">
          <strong>${escapeHtml(lot.label)}</strong>
          <span>${escapeHtml(formatBytes(lot.bytes))} · ${lot.unit_count} pasta(s) ${status}</span>
        </div>
        <p class="files-lots-units">${unitList}</p>
        <button type="button" class="btn btn-primary btn-sm" data-lot-dl="${lot.lot}">Baixar ${escapeHtml(lot.filename)}</button>
      </li>`;
    })
    .join("");
}

function showLotsModal(plan, path, ctx, setStatus) {
  closeLotsModal();
  let pollTimer = null;

  const backdrop = document.createElement("div");
  backdrop.className = "files-lots-backdrop";
  backdrop.innerHTML = `<div class="files-lots-panel" role="dialog" aria-labelledby="files-lots-title">
    <header class="files-lots-head">
      <h3 id="files-lots-title">Download em lotes — ${escapeHtml(plan.name || "")}</h3>
      <button type="button" class="btn btn-ghost btn-sm" data-lots-close aria-label="Fechar">✕</button>
    </header>
    <p class="files-lots-lede">
      Pasta grande (${escapeHtml(formatBytes(plan.bytes))}) dividida em
      <strong>${plan.lot_count} lotes</strong> (até ${plan.lote_max_mb} MB cada).
      Cada licitação ou subpasta fica <strong>inteira</strong> em um lote.
      ${plan.prebuild ? " O servidor <strong>prepara os ZIPs em background</strong> — lotes marcados Pronto baixam na hora." : ""}
    </p>
    <div class="files-lots-actions">
      <button type="button" class="btn btn-ghost btn-sm" data-lots-all>Baixar todos em sequência</button>
    </div>
    <ul class="files-lots-list" data-lots-list>${renderLotsRows(plan.lots)}</ul>
    <p class="files-lots-hint">Aguarde o status <strong>Pronto</strong> para download instantâneo. No modo sequência, espere cada arquivo terminar no navegador.</p>
  </div>`;

  const stopPoll = () => {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  };

  const refreshPlan = async () => {
    try {
      const fresh = await fetchDownloadPlan(path, ctx);
      const list = backdrop.querySelector("[data-lots-list]");
      if (list && fresh.lots) list.innerHTML = renderLotsRows(fresh.lots);
      const allReady = (fresh.lots || []).every((l) => l.cached);
      if (allReady) stopPoll();
    } catch (_) {}
  };

  pollTimer = setInterval(refreshPlan, 2500);

  backdrop.addEventListener("click", async (ev) => {
    if (ev.target === backdrop || ev.target.closest("[data-lots-close]")) {
      stopPoll();
      closeLotsModal();
      return;
    }
    const btn = ev.target.closest("[data-lot-dl]");
    if (btn) {
      const lot = Number(btn.getAttribute("data-lot-dl") || "1");
      setStatus(`Iniciando lote ${lot}…`, null);
      triggerDownload(path, ctx, lot);
      return;
    }
    if (ev.target.closest("[data-lots-all]")) {
      const lots = plan.lots || [];
      setStatus("Sequência iniciada — aguarde cada lote terminar no navegador.", true);
      for (let i = 0; i < lots.length; i++) {
        const lot = lots[i];
        setStatus(`Lote ${lot.lot} de ${lots.length} — baixando…`, null);
        triggerDownload(path, ctx, lot.lot);
        if (i < lots.length - 1) {
          await sleep(45000);
        }
      }
    }
  });

  document.body.appendChild(backdrop);
  const ready = (plan.lots || []).filter((l) => l.cached).length;
  setStatus(
    `${plan.lot_count} lotes — ${ready} pronto(s). ${plan.prebuild ? "Gerando os demais em background…" : ""}`,
    true
  );
}

async function startFolderDownload(path, ctx, setStatus) {
  setStatus("Calculando lotes…", null);
  try {
    const plan = await fetchDownloadPlan(path, ctx);
    if (plan.mode === "file" || plan.mode === "single") {
      setStatus("Iniciando download…", null);
      triggerDownload(path, ctx, 1);
      return;
    }
    showLotsModal(plan, path, ctx, setStatus);
  } catch (e) {
    setStatus(String(e.message || e), false);
  }
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
          <button type="button" class="btn btn-ghost btn-sm" data-files-dl-current ${state.path ? "" : "hidden"} title="Baixar esta pasta como ZIP">↓ Baixar pasta</button>
          <button type="button" class="btn btn-ghost btn-sm" data-files-mkdir ${ctx.readOnly ? "hidden" : ""}>Nova pasta</button>
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
          ? `<p class="files-pick-hint files-admin-hint">Arquivos no servidor (VPS) — usuário <strong>${escapeHtml(ctx.owner)}</strong>.</p>`
          : ""
      }
    </div>`;

  const crumbsEl = host.querySelector(".files-breadcrumbs");
  const bodyEl = host.querySelector("[data-files-body]");
  const statusEl = host.querySelector("[data-files-status]");
  const upBtn = host.querySelector("[data-files-up]");
  const dlCurrentBtn = host.querySelector("[data-files-dl-current]");
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
      if (dlCurrentBtn) dlCurrentBtn.hidden = !state.path;

      const rows = (data.entries || []).map((entry) => {
        const icon = entry.kind === "dir" ? "📁" : "📄";
        const name = escapeHtml(entry.name);
        const size = formatEntrySize(entry);
        const modified = entry.modified ? formatDate(entry.modified * 1000) : "—";
        const isJobs = entry.path === "jobs" || entry.path.startsWith("jobs/");
        const pickBtn =
          entry.kind === "dir" && state.pickField
            ? `<button type="button" class="btn btn-primary btn-sm" data-use-path="${escapeHtml(entry.abs_path)}">Usar</button>`
            : "";
        const dlBtn = isJobs
          ? ""
          : `<button type="button" class="btn btn-ghost btn-sm files-dl" data-dl-path="${escapeHtml(entry.path)}" data-dl-kind="${entry.kind}" title="${entry.kind === "dir" ? "Baixar pasta (ZIP)" : "Baixar arquivo"}">↓</button>`;
        const delBtn =
          !showDelete || isJobs
            ? ""
            : `<button type="button" class="btn btn-ghost btn-sm files-del" data-del-path="${escapeHtml(entry.path)}" title="Apagar">✕</button>`;
        const open =
          entry.kind === "dir"
            ? `<button type="button" class="files-link" data-open-path="${escapeHtml(entry.path)}">${icon} ${name}</button>`
            : `<span>${icon} ${name}</span>`;
        const sizeCell =
          entry.kind === "dir"
            ? `<td data-size-path="${escapeHtml(entry.path)}">${size}</td>`
            : `<td>${size}</td>`;
        return `<tr>
          <td>${open}</td>
          ${sizeCell}
          <td>${modified}</td>
          <td class="files-row-actions">${pickBtn}${dlBtn}${delBtn}</td>
        </tr>`;
      });
      bodyEl.innerHTML = rows.length
        ? rows.join("")
        : `<tr><td colspan="4" class="files-empty">Pasta vazia.</td></tr>`;

      const dirPaths = (data.entries || [])
        .filter((e) => e.kind === "dir" && e.size == null)
        .map((e) => e.path);
      if (dirPaths.length) {
        void loadFolderSizes(dirPaths, state.ctx, bodyEl);
      }
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
    const dl = ev.target.closest("[data-dl-path]");
    if (dl) {
      const p = dl.getAttribute("data-dl-path");
      const kind = dl.getAttribute("data-dl-kind") || "file";
      if (p) {
        if (kind === "dir") {
          void startFolderDownload(p, state.ctx, setStatus);
        } else {
          setStatus("Preparando download…", null);
          triggerDownload(p, state.ctx, 1);
          setStatus("Download iniciado.", true);
        }
      }
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

  dlCurrentBtn?.addEventListener("click", () => {
    if (!state.path) return;
    void startFolderDownload(state.path, state.ctx, setStatus);
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
