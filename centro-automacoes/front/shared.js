(() => {
  const API = "";

  /** Ferramentas por id (páginas de automação). */
  const TOOLS = {
    documentos: {
      id: "documentos",
      nome: "Documentos",
      descricao: "Baixa PDFs de páginas de transparência e organiza por tipo e ano.",
      pagina: "/documentos.html",
      icon: "file",
      cta: "Abrir",
    },
    categorias: {
      id: "categorias",
      nome: "Categorias",
      descricao: "Varre categorias WordPress e baixa PDFs de cada post, com IA local opcional no nome.",
      pagina: "/categorias.html",
      icon: "folder",
      cta: "Abrir",
    },
    normas: {
      id: "normas",
      nome: "Extração Pro",
      descricao: "Leis, atos, matérias e documentos — Prefeitura ou Câmara, com nomeação automática e IA local opcional.",
      pagina: "/normas.html",
      icon: "book",
      cta: "Abrir",
    },
    licitacoes: {
      id: "licitacoes",
      nome: "Licitações",
      descricao: "Baixa anexos de licitações CR2, extrai valores e preenche planilha.",
      pagina: "/licitacoes.html",
      icon: "building",
      cta: "Abrir",
    },
    contratos: {
      id: "contratos",
      nome: "Contratos",
      descricao: "Contratos e aditivos do Governo Transparente — PDFs e planilha.",
      pagina: "/contratos.html",
      icon: "contract",
      cta: "Abrir",
    },
    publicacao: {
      id: "publicacao",
      nome: "RGF / RREO / Balancete",
      descricao: "Publicação financeira no portal CR2 (navegador automático).",
      pagina: "/publicacao.html",
      icon: "upload",
      cta: "Abrir",
    },
    sessao: {
      id: "sessao",
      nome: "Sessão",
      descricao: "Pauta, Ata, Presença e Votações no portal CR2.",
      pagina: "/sessao.html",
      icon: "users",
      cta: "Abrir",
    },
    dic_est_ter: {
      id: "dic_est_ter",
      nome: "Dic / Est / Ter",
      descricao: "Dívida ativa, estagiários e terceirizados no portal CR2.",
      pagina: "/dic-est-ter.html",
      icon: "table",
      cta: "Abrir",
    },
    mapa: {
      id: "mapa",
      nome: "Mapa do Site",
      descricao: "Cria páginas WordPress e atualiza o mapa do site.",
      pagina: "/mapa.html",
      icon: "map",
      cta: "Abrir",
    },
  };

  const ICONS = {
    download:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M5 21h14"/></svg>',
    publish:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21V9"/><path d="m7 13 5-5 5 5"/><path d="M5 3h14"/></svg>',
    map:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18l-6 3V6l6-3 6 3 6-3v15l-6 3-6-3z"/><path d="M9 3v15"/><path d="M15 6v15"/></svg>',
    file:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h6"/></svg>',
    folder:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    book:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
    building:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 21v-6h6v6"/><path d="M9 10h.01"/><path d="M15 10h.01"/><path d="M9 14h.01"/><path d="M15 14h.01"/></svg>',
    upload:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/></svg>',
    users:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    table:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18v14H3z"/><path d="M3 10h18"/><path d="M3 15h18"/><path d="M9 5v14"/><path d="M15 5v14"/></svg>',
    contract:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h5"/><path d="m9 9 1.5 1.5L13 8"/></svg>',
  };

  /** Hubs de alto nível: Extração | Publicação | Mapa */
  const HUBS = [
    {
      key: "extrair",
      label: "Extração",
      href: "/extrair.html",
      titulo: "Extração",
      descricao:
        "Baixas do portal: documentos, categorias, Extração Pro e licitações.",
      icon: "download",
      cta: "Ver ferramentas",
      tools: ["documentos", "categorias", "normas", "licitacoes"],
      // ocultos por enquanto: "contratos"
    },
    {
      key: "publicar",
      label: "Publicação",
      href: "/publicar.html",
      titulo: "Publicação",
      descricao: "Envie dados e arquivos ao portal CR2 com poucos cliques.",
      icon: "publish",
      cta: "Ver ferramentas",
      tools: ["publicacao", "sessao", "dic_est_ter"],
      // ocultos por enquanto: nenhum
    },
    {
      key: "mapa",
      label: "Mapa",
      href: "/mapa.html",
      titulo: "Mapa do Site",
      descricao: "Crie páginas WordPress e atualize o mapa do site.",
      icon: "map",
      cta: "Abrir",
      tools: ["mapa"],
    },
  ];

  const NAV = [
    { href: "/", label: "Início", key: "hub" },
    ...HUBS.map((h) => ({ href: h.href, label: h.label, key: h.key })),
  ];

  const el = (id) => document.getElementById(id);

  function iconSvg(name) {
    return ICONS[name] || ICONS.file;
  }

  function findHub(key) {
    return HUBS.find((h) => h.key === key) || null;
  }

  function hubKeyFor(toolOrHub) {
    if (!toolOrHub || toolOrHub === "hub") return "hub";
    if (findHub(toolOrHub)) return toolOrHub;
    const hub = HUBS.find((h) => h.tools.includes(toolOrHub));
    return hub ? hub.key : "hub";
  }

  function injectSubnav(activeKey) {
    let bar = document.getElementById("hub-subnav");
    const hubKey = hubKeyFor(activeKey);
    const hub = findHub(hubKey);

    // Só mostra subnav em páginas de ferramenta com 2+ itens no hub
    const isToolPage = Boolean(TOOLS[activeKey]);
    if (!isToolPage || !hub || hub.tools.length < 2) {
      if (bar) bar.remove();
      document.body.classList.remove("has-subnav");
      return;
    }

    if (!bar) {
      bar = document.createElement("nav");
      bar.id = "hub-subnav";
      bar.className = "hub-subnav";
      bar.setAttribute("aria-label", "Ferramentas do hub");
      const top = document.querySelector("header.top");
      if (top && top.parentNode) {
        top.insertAdjacentElement("afterend", bar);
      } else {
        document.body.prepend(bar);
      }
    }

    document.body.classList.add("has-subnav");
    const back = `<a class="hub-subnav-back" href="${hub.href}">← ${hub.label}</a>`;
    const links = hub.tools
      .map((tid) => {
        const t = TOOLS[tid];
        if (!t) return "";
        const active = tid === activeKey ? " is-active" : "";
        return `<a class="hub-subnav-link${active}" href="${t.pagina}">${t.nome}</a>`;
      })
      .join("");
    bar.innerHTML = `<div class="hub-subnav-inner">${back}<div class="hub-subnav-links">${links}</div></div>`;
  }

  function injectNav(activeKey) {
    const nav = el("site-nav");
    const hubActive = hubKeyFor(activeKey);
    if (nav) {
      nav.innerHTML = NAV.map((n) => {
        const on =
          n.key === hubActive || (n.key === "hub" && activeKey === "hub");
        return `<a href="${n.href}" class="${on ? "is-active" : ""}">${n.label}</a>`;
      }).join("");
    }
    injectSubnav(activeKey);
  }

  function renderHubCards(targetId, items) {
    const grid = el(targetId);
    if (!grid) return;
    grid.innerHTML = items
      .map((s) => {
        const href = s.pagina || s.href || "#";
        const title = s.nome || s.titulo || s.label || "";
        const desc = s.descricao || "";
        const cta = s.cta || "Abrir";
        const icon = iconSvg(s.icon || "file");
        return `
      <a class="hub-card" href="${href}" data-glow>
        <span class="hub-card-glow" data-glow aria-hidden="true"></span>
        <span class="hub-card-icon">${icon}</span>
        <h3>${title}</h3>
        <p>${desc}</p>
        <div class="hub-card-foot">
          <span>${cta}</span>
          <span aria-hidden="true">→</span>
        </div>
      </a>`;
      })
      .join("");
    enableSpotlightCards();
  }

  let spotlightBound = false;

  function enableSpotlightCards() {
    const cards = document.querySelectorAll(".hub-card[data-glow]");
    if (!cards.length) return;

    if (!spotlightBound) {
      spotlightBound = true;
      document.addEventListener(
        "pointermove",
        (e) => {
          const x = e.clientX;
          const y = e.clientY;
          const xp = (x / window.innerWidth).toFixed(2);
          const yp = (y / window.innerHeight).toFixed(2);
          document.querySelectorAll(".hub-card[data-glow]").forEach((card) => {
            card.style.setProperty("--x", x.toFixed(2));
            card.style.setProperty("--y", y.toFixed(2));
            card.style.setProperty("--xp", xp);
            card.style.setProperty("--yp", yp);
          });
        },
        { passive: true }
      );
    }
  }

  function renderHomeHubs() {
    renderHubCards(
      "hub-grid",
      HUBS.map((h) => ({
        href: h.href,
        pagina: h.href,
        icon: h.icon,
        nome: h.titulo,
        descricao: h.descricao,
        cta: h.cta,
      }))
    );
  }

  function renderHubTools(hubKey) {
    const hub = findHub(hubKey);
    if (!hub) return;
    const title = el("hub-title");
    const lede = el("hub-lede");
    if (title) title.textContent = hub.titulo;
    if (lede) lede.textContent = hub.descricao;
    renderHubCards(
      "hub-grid",
      hub.tools.map((tid) => TOOLS[tid]).filter(Boolean)
    );
  }

  async function pingApi() {
    const pill = el("api-pill");
    if (!pill) return;
    try {
      const r = await fetch(`${API}/api/health`);
      if (!r.ok) throw new Error();
      const data = await r.json();
      atualizarPillStatus(pill, data);
      if (!window.__optoPillTimer) {
        window.__optoPillTimer = setInterval(() => {
          pingApi().catch(() => {});
        }, 2000);
      }
    } catch {
      pill.textContent = "Offline";
      pill.title = "Servidor do painel indisponível";
      pill.classList.add("offline");
      pill.classList.remove("online", "running");
    }
  }

  function atualizarPillStatus(pill, data) {
    const ativo = data && data.ativo;
    pill.classList.remove("offline");
    if (!ativo) {
      pill.textContent = "Online";
      pill.title = "Servidor online — nenhum processo em execução";
      pill.classList.add("online");
      pill.classList.remove("running");
      return;
    }

    const nome = ativo.nome || ativo.service_id || "Processo";
    const done = Number(ativo.done) || 0;
    const total = Number(ativo.total) || 0;
    let pct = ativo.percent;
    if (pct == null && total > 0) {
      pct = Math.round((100 * done) / total);
    }

    let texto = nome;
    if (total > 0) {
      texto = `${nome} · ${done}/${total}`;
      if (pct != null) texto += ` · ${pct}%`;
    } else if (pct != null) {
      texto = `${nome} · ${pct}%`;
    } else if (ativo.cancel_requested) {
      texto = `${nome} · cancelando…`;
    } else {
      texto = `${nome} · em execução`;
    }

    pill.textContent = texto;
    pill.title = ativo.label
      ? `${nome}: ${ativo.label}`
      : `${nome} em andamento`;
    pill.classList.add("online", "running");
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

    const empty = box.querySelector(".log-empty");
    if (empty) empty.remove();

    let msg = "";
    let lvl = level || "info";
    let time = "";

    if (line && typeof line === "object") {
      msg = String(line.msg || "");
      lvl = line.level || lvl || "info";
      time = line.t || "";
    } else {
      msg = String(line || "");
    }

    msg = msg.replace(/\s+/g, " ").trim();
    if (!msg || msg === "— fim —" || msg === "- fim -") return;

    // Separadores do script (====) viram linha visual limpa
    if (/^=+$/.test(msg) || /^-+$/.test(msg)) {
      const sep = document.createElement("div");
      sep.className = "log-sep";
      sep.setAttribute("aria-hidden", "true");
      box.appendChild(sep);
      box.scrollTop = box.scrollHeight;
      return;
    }

    // Títulos de seção / progresso do job
    const isSection =
      /^(fonte|resumo|download de normas|processando|p[aá]gina:)/i.test(msg) ||
      msg.includes("FONTE (") ||
      msg.startsWith("====") ||
      /^──\s*\[/.test(msg) ||
      /^etapas?:/i.test(msg) ||
      /\betapa:\s/i.test(msg);

    const labels = {
      info: "info",
      warn: "aviso",
      error: "erro",
      ok: "ok",
    };

    const div = document.createElement("div");
    div.className = `log-line log-${lvl}${isSection ? " log-section-line" : ""}`;
    div.innerHTML =
      '<span class="t"></span><span class="lv"></span><span class="msg"></span>';
    div.querySelector(".t").textContent = time || "··:··";
    div.querySelector(".lv").textContent = labels[lvl] || lvl;
    div.querySelector(".msg").textContent = msg.replace(/^====\s*/, "").replace(/\s*====$/, "");
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
    const title =
      kind === "error" ? "Erro" : kind === "warn" ? "Cancelado" : "Concluído";
    note.innerHTML = `<strong>${title}</strong><span>${message}</span>`;
    host.appendChild(note);
    requestAnimationFrame(() => note.classList.add("is-in"));
    setTimeout(() => {
      note.classList.remove("is-in");
      note.classList.add("is-out");
      setTimeout(() => note.remove(), 380);
    }, 6500);
  }

  const SERVICE_LABELS = {
    documentos: "Baixar Documentos",
    categorias: "Baixar por Categoria",
    normas: "Extração Pro",
    licitacoes: "Licitações",
    contratos: "Contratos / Aditivos",
    publicacao: "Publicação CR2",
    sessao: "Publicação de Sessão",
    mapa: "Mapa do Site",
    dic_est_ter: "Publicação Dic/Est/Ter",
  };

  const STATUS_PT = {
    pending: "Na fila",
    running: "Em execução",
    completed: "Concluído",
    failed: "Erro",
    cancelled: "Cancelado",
  };

  let es = null;
  let currentJobId = null;
  let noticeShownFor = null;

  function ensureCancelButton() {
    let btn = el("btn-cancel");
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.id = "btn-cancel";
      btn.className = "btn btn-stop";
      btn.textContent = "Cancelar fila";
      btn.hidden = true;
      btn.title = "Interrompe a fila deste processo";
      const row = document.querySelector(".acao-row");
      const bar = document.querySelector(".job-bar");
      const log = document.querySelector(".log-wrap .section-head");
      if (row) row.appendChild(btn);
      else if (bar) bar.appendChild(btn);
      else if (log) log.appendChild(btn);
      else document.body.appendChild(btn);
    }
    if (!btn.dataset.bound) {
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => cancelCurrentJob());
    }
    return btn;
  }

  function setCancelVisible(visible) {
    const btn = ensureCancelButton();
    btn.hidden = !visible;
    btn.disabled = !visible;
  }

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
    setCancelVisible(true);
    const runBtn = el("btn-run");
    if (runBtn) runBtn.disabled = true;
    const box = el("log-console");
    if (box) {
      box.innerHTML = '<p class="log-empty">Aguardando execução…</p>';
    }

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

  async function cancelCurrentJob() {
    if (!currentJobId) return;
    const btn = ensureCancelButton();
    btn.disabled = true;
    btn.textContent = "Cancelando…";
    try {
      const r = await fetch(`${API}/api/jobs/${currentJobId}/cancel`, {
        method: "POST",
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || "Falha ao cancelar");
      }
      appendLog({ msg: "Cancelamento solicitado…", level: "warn" }, "warn");
    } catch (e) {
      appendLog({ msg: String(e.message || e), level: "error" }, "error");
      btn.disabled = false;
      btn.textContent = "Cancelar fila";
    }
  }

  async function refreshStatus(jobId) {
    try {
      const r = await fetch(`${API}/api/jobs/${jobId}`);
      const job = await r.json();
      const runBtn = el("btn-run");
      if (runBtn) runBtn.disabled = false;
      const cancelBtn = el("btn-cancel");
      if (cancelBtn) cancelBtn.textContent = "Cancelar fila";

      const dl = el("btn-download");
      if (dl) {
        dl.hidden = !job.has_download;
        if (job.has_download) dl.href = `${API}/api/jobs/${jobId}/download`;
      }

      const label = SERVICE_LABELS[job.service_id] || job.service_id || "Automação";
      const already = noticeShownFor === jobId;
      const finished = ["completed", "failed", "cancelled"].includes(job.status);
      const st = el("job-status");
      if (st) st.textContent = STATUS_PT[job.status] || job.status;

      if (finished) {
        setCancelVisible(false);
      }

      if (job.status === "failed") {
        setLogState("Erro");
        if (job.error) {
          appendLog({ msg: "ERRO: " + job.error, level: "error" }, "error");
        }
        if (!already) {
          noticeShownFor = jobId;
          showNotice(job.error || `${label} terminou com erro.`, "error");
        }
      } else if (job.status === "cancelled") {
        setLogState("Cancelado");
        if (!already) {
          noticeShownFor = jobId;
          showNotice(
            (job.result && job.result.mensagem) || `${label}: fila cancelada.`,
            "warn"
          );
        }
      } else if (job.status === "completed") {
        setLogState("Concluído");
        if (!already) {
          noticeShownFor = jobId;
          showNotice(
            (job.result && job.result.mensagem) ||
              `${label} finalizado com sucesso.`,
            "ok"
          );
        }
      } else if (job.status === "running" && job.cancel_requested) {
        setLogState("Cancelando");
        setCancelVisible(true);
      } else {
        setLogState("Executando");
        setCancelVisible(true);
        if (runBtn) runBtn.disabled = true;
      }
    } catch (_) {
      setLogState("Parado");
      setCancelVisible(false);
      const runBtn = el("btn-run");
      if (runBtn) runBtn.disabled = false;
    }
  }

  async function startJob(serviceId, config) {
    const btn = el("btn-run");
    if (btn) btn.disabled = true;
    try {
      const r = await fetch(`${API}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service_id: serviceId, config }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Falha ao iniciar");
      watchJob(data.job_id);
    } catch (e) {
      appendLog({ msg: String(e.message || e), level: "error" }, "error");
      setLogState("Erro");
      setCancelVisible(false);
      showNotice(String(e.message || e), "error");
      if (btn) btn.disabled = false;
    }
  }

  function bindRun(serviceId, formId, fieldIds, readConfig, skipSensitive) {
    const form = el(formId);
    if (!form) return;
    ensureCancelButton();
    loadForm(serviceId, fieldIds);
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      saveForm(serviceId, fieldIds, skipSensitive);
      startJob(serviceId, readConfig());
    });
  }

  function parallaxHero() {
    /* no-op: o parallax no hero-plane competia com o layout da 1ª viewport */
  }

  window.OptoAutomacoes = {
    injectNav,
    pingApi,
    bindRun,
    parallaxHero,
    appendLog,
    showNotice,
    cancelCurrentJob,
    renderHomeHubs,
    renderHubTools,
    enableSpotlightCards,
    HUBS,
    TOOLS,
  };
  window.CR2Centro = window.OptoAutomacoes;

  // Garante fundo de partículas mesmo se a página esquecer o <script>
  if (!window.OptoFluidBackground) {
    const s = document.createElement("script");
    s.src = "/assets/fluid-particles.js";
    s.async = true;
    document.head.appendChild(s);
  } else if (window.OptoFluidBackground.init) {
    window.OptoFluidBackground.init();
  }
})();
