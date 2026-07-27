(() => {
  const API = "";
  const NAV = [
    { href: "/", label: "Início", key: "hub" },
    { href: "/documentos.html", label: "Documentos", key: "documentos" },
    { href: "/categorias.html", label: "Categorias", key: "categorias" },
    { href: "/normas.html", label: "Normas", key: "normas" },
    { href: "/publicacao.html", label: "Publicação", key: "publicacao" },
    { href: "/dic-est-ter.html", label: "Dic/Est/Ter", key: "dic_est_ter" },
    { href: "/mapa.html", label: "Mapa", key: "mapa" },
  ];

  const el = (id) => document.getElementById(id);

  function injectNav(activeKey) {
    const nav = el("site-nav");
    if (!nav) return;
    nav.innerHTML = NAV.map(
      (n) =>
        `<a href="${n.href}" class="${n.key === activeKey ? "is-active" : ""}">${n.label}</a>`
    ).join("");
  }

  async function pingApi() {
    const pill = el("api-pill");
    if (!pill) return;
    try {
      const r = await fetch(`${API}/api/health`);
      if (r.ok) {
        pill.textContent = "API online";
        pill.classList.add("online");
        pill.classList.remove("offline");
      } else throw new Error();
    } catch {
      pill.textContent = "API offline";
      pill.classList.add("offline");
      pill.classList.remove("online");
    }
  }

  function loadForm(key, fields) {
    try {
      const raw = localStorage.getItem(`cr2-centro-${key}`);
      if (!raw) return;
      const data = JSON.parse(raw);
      fields.forEach((f) => {
        const node = el(f);
        if (node && data[f] != null) {
          if (node.type === "checkbox") node.checked = !!data[f];
          else node.value = data[f];
        }
      });
    } catch (_) {}
  }

  function saveForm(key, fields, skipSensitive) {
    const data = {};
    fields.forEach((f) => {
      const node = el(f);
      if (!node) return;
      if (skipSensitive && (f.includes("senha") || f.includes("password"))) return;
      data[f] = node.type === "checkbox" ? node.checked : node.value;
    });
    localStorage.setItem(`cr2-centro-${key}`, JSON.stringify(data));
  }

  function appendLog(line, level) {
    const box = el("log-console");
    if (!box) return;
    const div = document.createElement("div");
    div.className = `log-line log-${level || "info"}`;
    div.textContent = line.t ? `[${line.t}] ${line.msg}` : line.msg || line;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function setLogState(state) {
    const s = el("log-state");
    if (s) {
      s.textContent = state;
      s.dataset.state = state.toLowerCase();
    }
  }

  function ensureNoticeHost() {
    let host = document.getElementById("opto-notice-host");
    if (host) return host;
    host = document.createElement("div");
    host.id = "opto-notice-host";
    host.className = "opto-notice-host";
    host.setAttribute("aria-live", "polite");
    document.body.appendChild(host);
    return host;
  }

  function showNotice(message, kind) {
    const host = ensureNoticeHost();
    const note = document.createElement("div");
    note.className = `opto-notice opto-notice-${kind || "ok"}`;
    note.innerHTML = `<strong>${kind === "error" ? "Erro" : "Concluído"}</strong><span>${message}</span>`;
    host.appendChild(note);
    requestAnimationFrame(() => note.classList.add("is-in"));
    setTimeout(() => {
      note.classList.remove("is-in");
      note.classList.add("is-out");
      setTimeout(() => note.remove(), 380);
    }, 6500);
  }

  const SERVICE_LABELS = {
    documentos: "Download de Documentos",
    categorias: "Download por Categoria",
    normas: "Download de Normas",
    publicacao: "Publicação CR2",
    mapa: "Mapa do Site",
    dic_est_ter: "Publicação Dic/Est/Ter",
  };

  let es = null;
  let currentJobId = null;
  let noticeShownFor = null;

  function closeStream() {
    if (es) {
      es.close();
      es = null;
    }
  }

  function watchJob(jobId) {
    closeStream();
    currentJobId = jobId;
    noticeShownFor = null;
    setLogState("Executando");
    const box = el("log-console");
    if (box) box.innerHTML = "";

    es = new EventSource(`${API}/api/jobs/${jobId}/logs/stream`);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.level === "done") {
          closeStream();
          refreshStatus(jobId);
          return;
        }
        appendLog(data, data.level);
        if ((data.msg || "").includes("— fim —")) {
          closeStream();
          refreshStatus(jobId);
        }
      } catch (_) {}
    };
    es.onerror = () => {
      closeStream();
      refreshStatus(jobId);
    };
  }

  async function refreshStatus(jobId) {
    try {
      const r = await fetch(`${API}/api/jobs/${jobId}`);
      const job = await r.json();
      const st = el("job-status");
      if (st) st.textContent = job.status;
      const dl = el("btn-download");
      if (dl) {
        dl.hidden = !job.has_download;
        if (job.has_download) dl.href = `${API}/api/jobs/${jobId}/download`;
      }

      const label = SERVICE_LABELS[job.service_id] || job.service_id || "Automação";
      const already = noticeShownFor === jobId;

      if (job.status === "failed") {
        setLogState("Erro");
        if (job.error) {
          appendLog({ msg: "ERRO: " + job.error, level: "error" }, "error");
        }
        if (!already) {
          noticeShownFor = jobId;
          showNotice(job.error || `${label} terminou com erro.`, "error");
        }
      }
      if (job.status === "completed") {
        setLogState("Concluído");
        const msg =
          (job.result && job.result.mensagem) ||
          `${label} finalizado com sucesso.`;
        if (!already) {
          noticeShownFor = jobId;
          showNotice(msg, "ok");
        }
      }
    } catch (_) {}
  }

  async function startJob(serviceId, config) {
    const btn = el("btn-run");
    if (btn) btn.disabled = true;
    setLogState("Iniciando");
    try {
      const r = await fetch(`${API}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service_id: serviceId, config }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || r.statusText);
      }
      const data = await r.json();
      watchJob(data.job_id);
    } catch (e) {
      appendLog({ msg: String(e.message || e), level: "error" }, "error");
      setLogState("Erro");
      showNotice(String(e.message || e), "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function bindRun(serviceId, formId, fieldIds, readConfig, skipSensitive) {
    const form = el(formId);
    if (!form) return;
    loadForm(serviceId, fieldIds);
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      saveForm(serviceId, fieldIds, skipSensitive);
      startJob(serviceId, readConfig());
    });
  }

  function parallaxHero() {
    const plane = document.querySelector(".hero-plane");
    if (!plane) return;
    document.addEventListener("pointermove", (e) => {
      const x = (e.clientX / window.innerWidth - 0.5) * 12;
      const y = (e.clientY / window.innerHeight - 0.5) * 8;
      plane.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    });
  }

  window.OptoAutomacoes = {
    injectNav,
    pingApi,
    bindRun,
    parallaxHero,
    appendLog,
    showNotice,
  };
  window.CR2Centro = window.OptoAutomacoes;
})();
