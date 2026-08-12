import { whenReady } from "./modules/core.js";

(() => {
  "use strict";

  const API = "";
  const PANEL_TITLES = {
    overview: ["Visão geral", "Monitoramento em tempo real"],
    jobs: ["Processos", "Histórico e logs dos jobs"],
    services: ["Ferramentas", "Automações disponíveis no painel"],
    files: ["Arquivos", "Uploads, downloads e jobs por usuário"],
    system: ["Sistema", "Servidor, fila e armazenamento"],
  };

  let filesUsersLoaded = false;
  let filesCurrentOwner = "";

  const STATUS_LABEL = {
    pending: "Na fila",
    running: "Rodando",
    completed: "Concluído",
    failed: "Erro",
    cancelled: "Cancelado",
  };

  let overviewData = null;
  let pollTimer = null;

  function $(id) {
    return document.getElementById(id);
  }

  function fmtTime(ts) {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function statusClass(status) {
    return "admin-badge admin-badge--" + (status || "pending");
  }

  function serviceName(id, labels) {
    return (labels && labels[id]) || id || "—";
  }

  function formatProgress(j) {
    const prog = j.progress || {};
    const done = prog.done ?? j.done;
    const total = prog.total ?? j.total;
    let pct = prog.percent ?? j.percent;
    if (j.status === "running" && pct != null && pct >= 100) pct = 99;
    if (done != null && total != null && total > 0) {
      const p = pct != null ? pct : Math.round((100 * done) / total);
      return `${done}/${total} (${p}%)`;
    }
    if (pct != null) return `${pct}%`;
    const label = prog.label || j.label;
    if (label) return label;
    return "—";
  }

  function progressBarWidth(j) {
    const prog = j.progress || {};
    let pct = prog.percent ?? j.percent;
    const done = prog.done ?? j.done;
    const total = prog.total ?? j.total;
    if (pct == null && done != null && total != null && total > 0) {
      pct = Math.round((100 * done) / total);
    }
    if (j.status === "running" && pct != null && pct >= 100) pct = 99;
    return pct != null ? pct : 0;
  }

  function canCancelJob(j) {
    return j && (j.status === "running" || j.status === "pending") && !j.cancel_requested;
  }

  function jobActionButtons(j) {
    const logBtn =
      '<button type="button" class="btn btn-ghost btn-sm" data-view-job="' +
      j.id +
      '">Log</button>';
    if (j.cancel_requested && (j.status === "running" || j.status === "pending")) {
      return (
        '<div class="admin-job-actions">' +
        logBtn +
        '<span class="admin-muted admin-canceling">Cancelando…</span></div>'
      );
    }
    if (!canCancelJob(j)) {
      return '<div class="admin-job-actions">' + logBtn + "</div>";
    }
    return (
      '<div class="admin-job-actions">' +
      logBtn +
      '<button type="button" class="btn btn-stop btn-sm" data-cancel-job="' +
      j.id +
      '" title="Interrompe este processo">Cancelar</button></div>'
    );
  }

  async function cancelJobById(jobId) {
    if (!jobId) return;
    if (!confirm("Cancelar o processo " + jobId + "?")) return;
    const fetchFn =
      window.OptoAutomacoes && OptoAutomacoes.authFetch
        ? OptoAutomacoes.authFetch
        : fetch;
    const r = await fetchFn(API + "/api/jobs/" + encodeURIComponent(jobId) + "/cancel", {
      method: "POST",
    });
    if (!r.ok) {
      let msg = "Falha ao cancelar";
      try {
        const data = await r.json();
        msg = data.detail || data.msg || msg;
      } catch (_) {}
      alert(msg);
      return;
    }
    await refresh();
  }

  function bindJobActionButtons(root) {
    if (!root) return;
    root.querySelectorAll("[data-view-job]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-view-job");
        showPanel("jobs");
        loadJobDetail(id);
      });
    });
    root.querySelectorAll("[data-cancel-job]").forEach((btn) => {
      btn.addEventListener("click", () => cancelJobById(btn.getAttribute("data-cancel-job")));
    });
  }

  async function fetchOverview() {
    const fetchFn =
      window.OptoAutomacoes && OptoAutomacoes.authFetch
        ? OptoAutomacoes.authFetch
        : fetch;
    const r = await fetchFn(API + "/api/admin/overview");
    if (r.status === 401) {
      location.href = "/login.html?next=" + encodeURIComponent("/admin.html");
      throw new Error("Login necessário");
    }
    if (r.status === 403) {
      throw new Error("Acesso restrito ao administrador principal.");
    }
    if (!r.ok) throw new Error("Falha ao carregar admin");
    return r.json();
  }

  function renderStats(data) {
    const stats = data.stats || {};
    const by = stats.by_status || {};
    const running = data.running ?? by.running ?? 0;
    const pending = data.pending ?? by.pending ?? 0;
    const maxSlots = data.max_ativos || 4;
    const cards = [
      { label: "Total de processos", value: stats.total || 0, hint: "Na sessão do servidor" },
      {
        label: "Rodando agora",
        value: running,
        hint: `${pending} na fila · máx. ${maxSlots} simultâneo(s)`,
      },
      { label: "Concluídos", value: by.completed || 0, hint: "Com sucesso" },
      { label: "Com erro", value: by.failed || 0, hint: "Falharam ou cancelados" },
    ];
    $("admin-stats").innerHTML = cards
      .map(
        (c) => `
      <article class="admin-stat">
        <p class="admin-stat-label">${c.label}</p>
        <p class="admin-stat-value">${c.value}</p>
        <p class="admin-stat-hint">${c.hint}</p>
      </article>`
      )
      .join("");

    const runningBadge = (by.running || 0) + (by.pending || 0);
    const badge = $("badge-jobs");
    if (badge) {
      if (runningBadge > 0) {
        badge.hidden = false;
        badge.textContent = String(runningBadge);
      } else {
        badge.hidden = true;
      }
    }
  }

  function renderOverviewQueue(data) {
    const box = $("overview-queue-live");
    if (!box) return;
    const labels = data.service_labels || {};
    const q = data.queue || {};
    const running = q.running_jobs || [];
    const pending = q.pending_jobs || [];
    const maxSlots = data.max_ativos || 4;

    if (!running.length && !pending.length) {
      box.innerHTML = '<p class="admin-muted">Nenhum processo na fila — slots livres.</p>';
      return;
    }

    const row = (j, kind) => {
      const pct = formatProgress(j);
      const pos =
        kind === "pending" && j.queue && j.queue.position
          ? "#" + j.queue.position
          : kind === "running"
            ? "▶"
            : "—";
      return (
        "<tr>" +
        "<td>" + pos + "</td>" +
        '<td><span class="' + statusClass(j.status) + '">' + (STATUS_LABEL[j.status] || j.status) + "</span></td>" +
        "<td>" + serviceName(j.service_id, labels) + "</td>" +
        "<td>" + (j.owner || "—") + "</td>" +
        "<td>" + pct + "</td>" +
        '<td><code class="admin-code">' + j.id + "</code></td>" +
        "<td>" + jobActionButtons(j) + "</td>" +
        "</tr>"
      );
    };

    box.innerHTML =
      '<div class="admin-slots" style="margin-bottom:1rem">' +
      '<span class="admin-slots-label">' + (data.running ?? 0) + "/" + maxSlots + " slots em uso</span>" +
      '<div class="admin-progress"><div class="admin-progress-bar" style="width:' +
      Math.round(((data.running ?? 0) / maxSlots) * 100) +
      '%"></div></div></div>' +
      '<div class="admin-table-wrap"><table class="admin-table admin-table--compact">' +
      "<thead><tr><th>Fila</th><th>Status</th><th>Ferramenta</th><th>Usuário</th><th>%</th><th>ID</th><th></th></tr></thead><tbody>" +
      running.map((j) => row(j, "running")).join("") +
      pending.map((j) => row(j, "pending")).join("") +
      "</tbody></table></div>";

    bindJobActionButtons(box);
  }

  function renderActive(data) {
    const box = $("active-job-box");
    const cancelBtn = $("btn-cancel-active");
    const running = data.running_jobs || [];
    if (!running.length) {
      const pending = data.pending || 0;
      box.innerHTML =
        pending > 0
          ? `<p class="admin-muted">${pending} processo(s) aguardando vaga na fila.</p>`
          : '<p class="admin-muted">Nenhum processo rodando.</p>';
      if (cancelBtn) cancelBtn.hidden = true;
      return;
    }
    if (cancelBtn) cancelBtn.hidden = false;
    box.innerHTML = running
      .map((a) => {
        const pct = formatProgress(a);
        const bar = progressBarWidth(a);
        const canceling = a.cancel_requested
          ? '<span class="admin-muted admin-canceling">Cancelando…</span>'
          : canCancelJob(a)
            ? `<button type="button" class="btn btn-stop btn-sm" data-cancel-job="${a.id}">Cancelar</button>`
            : "";
        return `
      <div class="admin-active-job">
        <div class="admin-active-head">
          <span class="${statusClass(a.status)}">${STATUS_LABEL[a.status] || a.status}</span>
          <code class="admin-code">${a.id}</code>
        </div>
        <p class="admin-active-name">${a.nome}</p>
        <p class="admin-muted">${a.label || "Em andamento…"}</p>
        <div class="admin-progress">
          <div class="admin-progress-bar" style="width:${bar}%"></div>
        </div>
        <p class="admin-stat-hint">Progresso: ${pct}</p>
        <div class="admin-job-actions">
          <button type="button" class="btn btn-ghost btn-sm" data-view-job="${a.id}">Ver log</button>
          ${canceling}
        </div>
      </div>`;
      })
      .join("");
    bindJobActionButtons(box);
  }

  function renderByService(data) {
    const box = $("by-service-box");
    const by = (data.stats && data.stats.by_service) || {};
    const labels = data.service_labels || {};
    const entries = Object.entries(by).sort((a, b) => b[1] - a[1]);
    if (!entries.length) {
      box.innerHTML = '<p class="admin-muted">Nenhum processo registrado ainda.</p>';
      return;
    }
    const max = entries[0][1] || 1;
    box.innerHTML = entries
      .map(([sid, n]) => {
        const w = Math.round((n / max) * 100);
        return `
        <div class="admin-bar-row">
          <span class="admin-bar-label">${serviceName(sid, labels)}</span>
          <div class="admin-bar-track"><div class="admin-bar-fill" style="width:${w}%"></div></div>
          <span class="admin-bar-num">${n}</span>
        </div>`;
      })
      .join("");
  }

  function renderRecent(data) {
    const el = $("recent-activity");
    const recent = (data.stats && data.stats.recent) || [];
    const labels = data.service_labels || {};
    if (!recent.length) {
      el.innerHTML = '<p class="admin-muted">Sem atividade recente.</p>';
      return;
    }
    el.innerHTML = recent
      .slice(0, 8)
      .map((j) => {
        const msg = (j.result && j.result.mensagem) || j.error || "—";
        return `
        <button type="button" class="admin-activity-row" data-view-job="${j.id}">
          <span class="${statusClass(j.status)}">${STATUS_LABEL[j.status] || j.status}</span>
          <span class="admin-activity-title">${serviceName(j.service_id, labels)}</span>
          <span class="admin-activity-msg">${String(msg).slice(0, 80)}</span>
          <span class="admin-activity-time">${fmtTime(j.created_at)}</span>
        </button>`;
      })
      .join("");
    el.querySelectorAll("[data-view-job]").forEach((btn) => {
      btn.addEventListener("click", () => {
        showPanel("jobs");
        loadJobDetail(btn.getAttribute("data-view-job"));
      });
    });
  }

  function renderJobsTable(data) {
    const tbody = $("jobs-table")?.querySelector("tbody");
    if (!tbody) return;
    const queue = data.queue || {};
    const labels = data.service_labels || {};
    const alive = []
      .concat(queue.running_jobs || [])
      .concat(queue.pending_jobs || []);
    const recent = alive.length
      ? alive
      : (data.stats && data.stats.recent) || [];
    tbody.innerHTML = recent
      .map((j) => {
        const pct = formatProgress(j);
        const pos =
          j.status === "pending" && j.queue && j.queue.position
            ? `#${j.queue.position}`
            : "—";
        return `
        <tr>
          <td><code class="admin-code">${j.id}</code></td>
          <td>${serviceName(j.service_id, labels)}</td>
          <td><span class="${statusClass(j.status)}">${STATUS_LABEL[j.status] || j.status}</span></td>
          <td>${pos}</td>
          <td>${j.owner || "—"}</td>
          <td>${pct}</td>
          <td>${fmtTime(j.created_at)}</td>
          <td>${jobActionButtons(j)}</td>
        </tr>`;
      })
      .join("");
    tbody.querySelectorAll("[data-view-job]").forEach((btn) => {
      btn.addEventListener("click", () => loadJobDetail(btn.getAttribute("data-view-job")));
    });
    tbody.querySelectorAll("[data-cancel-job]").forEach((btn) => {
      btn.addEventListener("click", () => cancelJobById(btn.getAttribute("data-cancel-job")));
    });
  }

  function renderServices(data) {
    const grid = $("services-grid");
    if (!grid) return;
    const ocultos = new Set(data.services_ocultos || []);
    grid.innerHTML = (data.services || [])
      .map((s) => {
        const hidden = ocultos.has(s.id);
        const count = ((data.stats && data.stats.by_service) || {})[s.id] || 0;
        return `
        <a class="admin-tool-card" href="${s.pagina}">
          <span class="admin-tool-index">${s.icone || "—"}</span>
          <h3>${s.nome}${hidden ? ' <span class="admin-badge admin-badge--muted">oculto</span>' : ""}</h3>
          <p>${s.descricao}</p>
          <footer><span>${count} execução(ões)</span><span>Abrir →</span></footer>
        </a>`;
      })
      .join("");
  }

  let dragId = null;

  function renderQueueReorder(data) {
    const box = $("queue-reorder");
    if (!box) return;
    const labels = data.service_labels || {};
    const pending = (data.queue && data.queue.pending_jobs) || [];
    if (!pending.length) {
      box.innerHTML = '<p class="admin-muted">Nenhum job na fila de espera.</p>';
      return;
    }
    box.innerHTML = `
      <p class="admin-muted">Arraste os itens e clique em Salvar ordem.</p>
      <ul class="admin-queue-sortable" id="queue-sortable">
        ${pending
          .map((j, i) => {
            const pos = (j.queue && j.queue.position) || i + 1;
            return `<li draggable="true" data-id="${j.id}">
              <span class="admin-drag-handle" aria-hidden="true">⋮⋮</span>
              <span>#${pos} · ${serviceName(j.service_id, labels)} · <code class="admin-code">${j.id}</code>${j.owner ? ` · ${j.owner}` : ""}</span>
            </li>`;
          })
          .join("")}
      </ul>
      <button type="button" class="btn btn-primary btn-sm" id="btn-save-queue">Salvar ordem</button>`;

    const list = $("queue-sortable");
    list.querySelectorAll("li").forEach((li) => {
      li.addEventListener("dragstart", () => {
        dragId = li.getAttribute("data-id");
        li.classList.add("is-dragging");
      });
      li.addEventListener("dragend", () => {
        dragId = null;
        li.classList.remove("is-dragging");
      });
      li.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        const over = ev.currentTarget;
        if (!dragId || over.getAttribute("data-id") === dragId) return;
        const dragging = list.querySelector('[data-id="' + dragId + '"]');
        if (dragging && dragging !== over) {
          const rect = over.getBoundingClientRect();
          const after = ev.clientY > rect.top + rect.height / 2;
          if (after) over.after(dragging);
          else over.before(dragging);
        }
      });
    });

    $("btn-save-queue")?.addEventListener("click", async () => {
      const order = [...list.querySelectorAll("li")].map((li) =>
        li.getAttribute("data-id")
      );
      const fetchFn =
        window.OptoAutomacoes && OptoAutomacoes.authFetch
          ? OptoAutomacoes.authFetch
          : fetch;
      const r = await fetchFn(API + "/api/queue/reorder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ order }),
      });
      if (!r.ok) {
        alert("Falha ao salvar ordem.");
        return;
      }
      await refresh();
    });
  }

  function renderSystem(data) {
    const sys = $("system-info");
    const disk = $("disk-info");
    const queueEl = $("queue-info");
    const q = data.queue || {};
    const maxSlots = data.max_ativos || 4;
    const maxQueue = data.max_queue || 20;
    if (sys) {
      sys.innerHTML = `
        <dt>Versão API</dt><dd>${data.version || "—"}</dd>
        <dt>Status</dt><dd>${data.ok ? "Online" : "Offline"}</dd>
        <dt>Slots de execução</dt><dd>${data.running ?? 0} / ${maxSlots} rodando</dd>
        <dt>Na fila</dt><dd>${data.pending ?? 0} aguardando</dd>
        <dt>Timeout job</dt><dd>${data.job_timeout_s ? data.job_timeout_s + " s" : "desligado"}</dd>
        <dt>Autenticação</dt><dd>${data.auth_required ? "ligada" : "desligada (local)"}</dd>
        <dt>Total na memória</dt><dd>${(data.stats && data.stats.total) || 0}</dd>`;
    }
    if (disk) {
      const d = data.disk || {};
      disk.innerHTML = `
        <dt>Pasta de jobs</dt><dd><code class="admin-code admin-code-block">${d.path || "—"}</code></dd>
        <dt>Pastas</dt><dd>${d.job_dirs ?? 0}</dd>
        <dt>Tamanho</dt><dd>${d.mb ?? 0} MB</dd>`;
    }
    if (queueEl) {
      const pendingList = (q.pending_jobs || [])
        .map((j, i) => {
          const pos = (j.queue && j.queue.position) || i + 1;
          return `<li><code>${j.id}</code> — ${serviceName(j.service_id, data.service_labels)} (pos. ${pos})</li>`;
        })
        .join("");
      queueEl.innerHTML = `
        <p>Até <strong>${maxSlots}</strong> processos rodam ao mesmo tempo; novos entram na fila (máx. <strong>${maxQueue}</strong> pending+running).</p>
        <div class="admin-slots">
          <span class="admin-slots-label">${data.running ?? 0}/${maxSlots} slots</span>
          <div class="admin-progress"><div class="admin-progress-bar" style="width:${Math.round(((data.running ?? 0) / maxSlots) * 100)}%"></div></div>
        </div>
        ${pendingList ? `<p class="admin-muted">Fila:</p><ul class="admin-queue-list">${pendingList}</ul>` : '<p class="admin-muted">Fila vazia.</p>'}
        <p class="admin-muted">Playwright (${["publicacao", "sessao", "pub_repasses", "contratos", "dic_est_ter"].join(", ")}) roda em <strong>subprocesso isolado</strong> por job.</p>
        <p class="admin-muted">A fila persiste em disco — jobs pending sobrevivem a reinício do servidor.</p>
        <p class="admin-muted">Variáveis: <code>OPTO_MAX_JOBS</code>, <code>OPTO_MAX_QUEUE</code>, <code>OPTO_DOWNLOAD_WORKERS</code>, <code>OPTO_JOB_TIMEOUT_S</code>, <code>OPTO_USERS</code></p>`;
    }
    renderCleanup(data.cleanup_preview);
  }

  function adminFetch(url, opts) {
    const fn =
      window.OptoAutomacoes && OptoAutomacoes.authFetch
        ? OptoAutomacoes.authFetch
        : fetch;
    return fn(url, opts);
  }

  function renderCleanup(preview) {
    const panel = $("cleanup-panel");
    if (!panel) return;
    const p = preview || {};
    const buckets = p.buckets || [];
    if (!buckets.length) {
      panel.innerHTML = '<p class="admin-muted">Nada para limpar no momento.</p>';
      return;
    }
    const rows = buckets
      .map((b) => {
        const checked =
          b.key === "upload_temp" ? "" : " checked";
        return `<label class="admin-cleanup-row">
          <input type="checkbox" data-cleanup-key="${b.key}"${checked} />
          <span><strong>${b.label}</strong> — ${b.files} arquivo(s), ${b.mb} MB</span>
        </label>`;
      })
      .join("");
    panel.innerHTML = `
      <p class="admin-cleanup-total">Total recuperável: <strong>${p.total_mb || 0} MB</strong> (${p.total_files || 0} arquivos)</p>
      <div class="admin-cleanup-list">${rows}</div>
      <div class="admin-cleanup-actions">
        <button type="button" class="btn btn-ghost btn-sm" id="btn-cleanup-preview">Atualizar</button>
        <button type="button" class="btn btn-primary btn-sm" id="btn-cleanup-run">Apagar selecionados</button>
      </div>
      <p class="admin-muted">Jobs na fila ou rodando <strong>nunca</strong> são apagados.</p>
      <p id="cleanup-result" class="admin-cleanup-result" hidden></p>`;
    $("btn-cleanup-preview")?.addEventListener("click", () => refreshCleanupPreview());
    $("btn-cleanup-run")?.addEventListener("click", () => runCleanup());
  }

  async function refreshCleanupPreview() {
    try {
      const r = await adminFetch(API + "/api/admin/cleanup/preview");
      if (!r.ok) throw new Error("Falha ao analisar");
      const data = await r.json();
      renderCleanup(data);
    } catch (e) {
      const panel = $("cleanup-panel");
      if (panel) {
        panel.innerHTML =
          '<p class="admin-error">' + (e.message || e) + "</p>";
      }
    }
  }

  async function runCleanup() {
    const panel = $("cleanup-panel");
    if (!panel) return;
    const keys = new Set(
      [...panel.querySelectorAll("[data-cleanup-key]:checked")].map(
        (n) => n.getAttribute("data-cleanup-key")
      )
    );
    if (!keys.size) {
      alert("Marque pelo menos um tipo de arquivo.");
      return;
    }
    if (
      !confirm(
        "Apagar os itens selecionados? Esta ação não pode ser desfeita."
      )
    ) {
      return;
    }
    const body = {
      job_dirs: keys.has("job_dirs"),
      job_days: 0,
      screenshots: keys.has("screenshots"),
      ia_cache: keys.has("ia_cache"),
      upload_temp: keys.has("upload_temp"),
      upload_days: 7,
    };
    const btn = $("btn-cleanup-run");
    if (btn) btn.disabled = true;
    try {
      const r = await adminFetch(API + "/api/admin/cleanup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(data.detail || "Falha na limpeza");
      }
      const msg = document.getElementById("cleanup-result");
      if (msg) {
        msg.hidden = false;
        msg.textContent = `Removidos ${data.deleted_mb || 0} MB (${data.deleted_files || 0} arquivos, ${data.removed_dirs || 0} pastas).`;
        if (data.errors && data.errors.length) {
          msg.textContent += " Avisos: " + data.errors.join("; ");
        }
      }
      if (overviewData) {
        overviewData.disk = data.disk || overviewData.disk;
        overviewData.cleanup_preview = data.cleanup_preview;
        renderSystem(overviewData);
      } else {
        renderCleanup(data.cleanup_preview);
      }
    } catch (e) {
      alert(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function loadJobDetail(jobId) {
    const card = $("job-detail-card");
    const logEl = $("job-detail-log");
    const title = $("job-detail-title");
    const head = card?.querySelector(".admin-card-head");
    if (!card || !logEl) return;
    card.hidden = false;
    title.textContent = "Job " + jobId;
    logEl.textContent = "Carregando…";
    let detailCancel = head?.querySelector("[data-cancel-job-detail]");
    if (detailCancel) detailCancel.remove();
    try {
      const fetchFn =
        window.OptoAutomacoes && OptoAutomacoes.authFetch
          ? OptoAutomacoes.authFetch
          : fetch;
      const r = await fetchFn(API + "/api/jobs/" + jobId);
      if (r.status === 401) throw new Error("Sessão expirada — faça login novamente.");
      if (r.status === 403) throw new Error("Sem permissão para ver este log.");
      if (r.status === 404) throw new Error("Processo não encontrado (pode ter sido limpo do disco).");
      if (!r.ok) throw new Error("Falha ao carregar log (" + r.status + ")");
      const job = await r.json();
      const lines = (job.logs || []).map((e) => {
        const t = e.t ? e.t + " " : "";
        return `${t}[${e.level}] ${e.msg}`;
      });
      const header = [];
      if (job.from_disk) header.push("(lido do disco)");
      if (job.status) header.push("Status: " + (STATUS_LABEL[job.status] || job.status));
      if (job.owner) header.push("Usuário: " + job.owner);
      if (job.error) header.push("ERRO: " + job.error);
      if (job.result && job.result.mensagem) header.push("Resultado: " + job.result.mensagem);
      const body = lines.length ? lines.join("\n") : "(sem linhas de log)";
      logEl.textContent = (header.length ? header.join("\n") + "\n\n" : "") + body;
      logEl.scrollTop = logEl.scrollHeight;
      if (head && canCancelJob(job)) {
        detailCancel = document.createElement("button");
        detailCancel.type = "button";
        detailCancel.className = "btn btn-stop btn-sm";
        detailCancel.setAttribute("data-cancel-job-detail", job.id);
        detailCancel.textContent = "Cancelar este processo";
        detailCancel.addEventListener("click", () => cancelJobById(job.id));
        const closeBtn = $("job-detail-close");
        if (closeBtn) head.insertBefore(detailCancel, closeBtn);
        else head.appendChild(detailCancel);
      } else if (head && job.cancel_requested && (job.status === "running" || job.status === "pending")) {
        const note = document.createElement("span");
        note.className = "admin-muted admin-canceling";
        note.setAttribute("data-cancel-job-detail", "1");
        note.textContent = "Cancelando…";
        const closeBtn = $("job-detail-close");
        if (closeBtn) head.insertBefore(note, closeBtn);
        else head.appendChild(note);
      }
    } catch (e) {
      logEl.textContent = String(e.message || e);
    }
  }

  function filesFrameUrl(owner, path) {
    if (!owner) return "about:blank";
    const q = new URLSearchParams({
      embed: "1",
      admin: "1",
      owner,
    });
    if (path) q.set("path", path);
    return "/arquivos.html?" + q.toString();
  }

  function navigateFilesFrame(path) {
    const frame = $("admin-files-frame");
    if (!frame || !filesCurrentOwner) return;
    const win = frame.contentWindow;
    if (win) {
      win.postMessage({ type: "opto-files-nav", path: path || "" }, window.location.origin);
      return;
    }
    frame.src = filesFrameUrl(filesCurrentOwner, path);
  }

  function setFilesOwner(owner, path) {
    filesCurrentOwner = owner || "";
    const frame = $("admin-files-frame");
    const openTab = $("files-open-tab");
    if (!frame) return;
    if (!filesCurrentOwner) {
      frame.src = "about:blank";
      if (openTab) openTab.href = "/arquivos.html";
      return;
    }
    frame.src = filesFrameUrl(filesCurrentOwner, path || "");
    if (openTab) {
      openTab.href = filesFrameUrl(filesCurrentOwner, "");
    }
  }

  async function loadFilesPanel() {
    const select = $("files-owner-select");
    const frame = $("admin-files-frame");
    if (!select || !frame) return;

    if (filesUsersLoaded && select.options.length > 1) {
      if (filesCurrentOwner) setFilesOwner(filesCurrentOwner);
      return;
    }

    select.innerHTML = '<option value="">Carregando…</option>';
    try {
      const r = await adminFetch(API + "/api/admin/workspace/users");
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || "Falha ao listar usuários");
      const users = data.users || [];
      if (!users.length) {
        select.innerHTML = '<option value="">Nenhum workspace ainda</option>';
        frame.srcdoc =
          '<p style="padding:1rem;color:#a8b0c0;font-family:sans-serif">Nenhum usuário com pasta no servidor. Após o primeiro upload ou job, aparece aqui.</p>';
        return;
      }
      select.innerHTML = users
        .map((u) => {
          const mb = u.size_bytes ? (u.size_bytes / (1024 * 1024)).toFixed(1) + " MB" : "";
          const label = u.id + (mb ? " · " + mb : "");
          return `<option value="${u.id}">${label}</option>`;
        })
        .join("");
      filesUsersLoaded = true;
      const first = users[0].id;
      select.value = filesCurrentOwner || first;
      setFilesOwner(select.value, "");
    } catch (e) {
      select.innerHTML = '<option value="">Erro ao carregar</option>';
      frame.srcdoc =
        '<p style="padding:1rem;color:#f87171;font-family:sans-serif">' +
        (e.message || e) +
        "</p>";
    }
  }

  function bindFilesPanel() {
    $("files-owner-select")?.addEventListener("change", (ev) => {
      setFilesOwner(ev.target.value, "");
    });
    document.querySelectorAll("[data-files-shortcut]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const path = btn.getAttribute("data-files-shortcut") || "";
        if (!filesCurrentOwner) return;
        navigateFilesFrame(path);
      });
    });
  }

  function showPanel(name) {
    document.querySelectorAll(".admin-panel").forEach((p) => {
      const on = p.getAttribute("data-panel") === name;
      p.hidden = !on;
      p.classList.toggle("is-visible", on);
    });
    document.querySelectorAll(".admin-nav-item[data-panel]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-panel") === name);
    });
    const t = PANEL_TITLES[name] || ["Admin", ""];
    $("admin-page-title").textContent = t[0];
    $("admin-page-sub").textContent = t[1];
    if (name === "files") loadFilesPanel();
  }

  async function refresh() {
    try {
      overviewData = await fetchOverview();
      renderStats(overviewData);
      renderOverviewQueue(overviewData);
      renderActive(overviewData);
      renderByService(overviewData);
      renderRecent(overviewData);
      renderJobsTable(overviewData);
      renderQueueReorder(overviewData);
      renderServices(overviewData);
      renderSystem(overviewData);
      if (window.OptoAutomacoes && OptoAutomacoes.pingApi) {
        OptoAutomacoes.pingApi();
      }
    } catch (e) {
      $("admin-stats").innerHTML =
        '<p class="admin-error">Erro ao carregar: ' + (e.message || e) + "</p>";
    }
  }

  function bindUi() {
    document.querySelectorAll(".admin-nav-item[data-panel]").forEach((btn) => {
      btn.addEventListener("click", () => showPanel(btn.getAttribute("data-panel")));
    });
    bindFilesPanel();

    $("admin-sidebar-toggle")?.addEventListener("click", () => {
      document.body.classList.toggle("admin-sidebar-collapsed");
    });

    $("btn-refresh")?.addEventListener("click", () => refresh());
    $("job-detail-close")?.addEventListener("click", () => {
      $("job-detail-card").hidden = true;
    });

    $("btn-cancel-active")?.addEventListener("click", async () => {
      if (!confirm("Cancelar TODOS os processos em andamento e na fila?")) return;
      const fetchFn =
        window.OptoAutomacoes && OptoAutomacoes.authFetch
          ? OptoAutomacoes.authFetch
          : fetch;
      const r = await fetchFn(API + "/api/jobs/cancel-active", { method: "POST" });
      if (!r.ok) {
        let msg = "Falha ao cancelar";
        try {
          const data = await r.json();
          msg = data.detail || data.msg || msg;
        } catch (_) {}
        alert(msg);
      }
      await refresh();
    });
  }

  function boot() {
    bindUi();
    refresh();
    pollTimer = setInterval(refresh, 8000);
    window.addEventListener("beforeunload", () => clearInterval(pollTimer));
  }
  whenReady(boot);
})();
