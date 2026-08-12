import { API, el, markReady } from "./modules/core.js";
import {
  authFetch,
  authHeaders,
  authToken,
  streamUrl,
  setAuthToken,
  logout,
  guardAuth,
  ensureLogoutButton,
} from "./modules/auth.js";
import { uploadFile, bindFileUpload, setUploadNotifier } from "./modules/upload.js";
import {
  applyPendingFolderPick,
  bindFolderPickButtons,
  fetchOutputHints,
  mountFileBrowser,
  pickFolderUrl,
} from "./modules/files.js";
import { injectFooter } from "./modules/nav.js";

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
      nome: "Baixar Extração Pro",
      descricao: "Leis, atos, matérias e documentos — Prefeitura ou Câmara, com nomeação automática e IA local opcional.",
      pagina: "/normas.html",
      icon: "book",
      cta: "Abrir",
    },
    licitacoes: {
      id: "licitacoes",
      nome: "Licitações CR2",
      descricao: "Baixa anexos de licitações CR2, extrai valores e preenche planilha.",
      pagina: "/licitacoes.html",
      icon: "building",
      cta: "Abrir",
    },
    tcm_licitacoes: {
      id: "tcm_licitacoes",
      nome: "Licitações TCM-PA",
      descricao: "Mural do TCM-PA: documentos, contratos e planilha Excel.",
      pagina: "/tcm-licitacoes.html",
      icon: "table",
      cta: "Abrir",
    },
    repasses: {
      id: "repasses",
      nome: "Repasses",
      descricao: "Planilha com links -> baixa documentos, OCR e gera planilha de repasses.",
      pagina: "/repasses.html",
      icon: "table",
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
    pub_repasses: {
      id: "pub_repasses",
      nome: "Publicação de Repasses",
      descricao: "Publica Repasses.xlsx no portal CR2 (mês/ano, data, valores, PDF).",
      pagina: "/pub-repasses.html",
      icon: "upload",
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
  // Alinhado ao backend SERVICES_OCULTOS — não listar no hub/subnav.
  const TOOLS_OCULTOS = new Set(["contratos", "dic_est_ter"]);

  const HUBS = [
    {
      key: "extrair",
      label: "Extração",
      href: "/extrair.html",
      titulo: "Extração",
      descricao:
        "Baixas do portal: documentos, categorias, Extração Pro, licitações CR2, TCM-PA e repasses.",
      icon: "download",
      cta: "Ver ferramentas",
      tools: ["documentos", "categorias", "normas", "licitacoes", "tcm_licitacoes", "repasses"],
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
      tools: ["publicacao", "sessao", "pub_repasses"],
      // ocultos por enquanto: "dic_est_ter"
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
    { href: "/arquivos.html", label: "Meus arquivos", key: "arquivos" },
    { href: "/admin.html", label: "Admin", key: "admin" },
  ];

  function iconSvg(name) {
    return ICONS[name] || ICONS.file;
  }

  function findHub(key) {
    return HUBS.find((h) => h.key === key) || null;
  }

  function hubKeyFor(toolOrHub) {
    if (!toolOrHub || toolOrHub === "hub") return "hub";
    if (toolOrHub === "arquivos") return "arquivos";
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
      .filter((tid) => !TOOLS_OCULTOS.has(tid))
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
        const adminCls = n.key === "admin" ? " nav-admin" : "";
        return `<a href="${n.href}" class="${on ? "is-active" : ""}${adminCls}" data-nav-key="${n.key}"${n.key === "admin" ? " hidden" : ""}>${n.label}</a>`;
      }).join("");
    }
    injectSubnav(activeKey);
    applyNavAuth();
  }

  async function applyNavAuth() {
    const nav = el("site-nav");
    try {
      const r = await authFetch(`${API}/api/auth/me`);
      if (!r.ok) return;
      const d = await r.json();
      const showAdmin = !d.auth_required || (d.user && d.user.panel_admin);
      const logoutBtn = el("btn-logout");
      if (logoutBtn) {
        logoutBtn.hidden = !d.auth_required || !d.user;
      }
      if (!nav) return;
      nav.querySelectorAll('[data-nav-key="admin"]').forEach((a) => {
        a.hidden = !showAdmin;
      });
      if (!showAdmin) {
        const adminCard = document.querySelector('.hub-card[href="/admin.html"]');
        if (adminCard) adminCard.remove();
      }
    } catch (_) {}
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
    const cards = [
      ...HUBS.map((h) => ({
        href: h.href,
        pagina: h.href,
        icon: h.icon,
        nome: h.titulo,
        descricao: h.descricao,
        cta: h.cta,
      })),
    ];
    renderHubCards("hub-grid", cards);
    authFetch(`${API}/api/auth/me`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d || d.auth_required && !(d.user && d.user.panel_admin)) return;
        const grid = el("hub-grid");
        if (!grid) return;
        const adminHtml = `
      <a class="hub-card" href="/admin.html" data-glow>
        <span class="hub-card-glow" data-glow aria-hidden="true"></span>
        <span class="hub-card-icon">${iconSvg("table")}</span>
        <h3>Admin</h3>
        <p>Monitoramento, processos, logs e status do servidor.</p>
        <div class="hub-card-foot">
          <span>Abrir painel</span>
          <span aria-hidden="true">→</span>
        </div>
      </a>`;
        grid.insertAdjacentHTML("beforeend", adminHtml);
        enableSpotlightCards();
      })
      .catch(() => {});
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
      hub.tools
        .filter((tid) => !TOOLS_OCULTOS.has(tid))
        .map((tid) => TOOLS[tid])
        .filter(Boolean)
    );
  }

  async function pingApi() {
    const pill = el("api-pill");
    if (!pill) return;
    try {
      const r = await authFetch(`${API}/api/health`);
      if (!r.ok) throw new Error();
      const data = await r.json();
      authRequired = !!data.auth_required;
      if (data.user && data.user.username) {
        currentUsername = data.user.username;
      } else if (!data.auth_required) {
        currentUsername = null;
      }
      atualizarPillStatus(pill, data);
      pollDownloadsReady().catch(() => {});
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

  function formatFilaPosicao(n) {
    const num = Math.max(1, Number(n) || 1);
    return String(num).padStart(2, "0");
  }

  function jobDisplayName(job) {
    if (!job) return "Processo";
    if (job.nome) return job.nome;
    return downloadLabel(job.service_id, job.owner || currentUsername);
  }

  function formatJobProgressText(job) {
    if (!job) return null;
    const done = job.done;
    const total = job.total;
    let pct = job.percent;
    if (job.status === "running" && pct != null && pct >= 100) pct = 99;
    if (done != null && total != null && total > 0) {
      const base = `${done}/${total}`;
      return pct != null ? `${base} (${pct}%)` : base;
    }
    if (pct != null) return `${pct}%`;
    if (job.label) return job.label;
    return null;
  }

  function resolveMyJob(data, serviceId) {
    const sid = serviceId || boundServiceId || null;
    if (data && Array.isArray(data.my_jobs)) {
      if (sid) {
        return data.my_jobs.find((j) => j.service_id === sid) || null;
      }
      return data.my_jobs[0] || null;
    }
    if (data && data.my_job && !sid) return data.my_job;
    if (data && data.auth_required) return null;
    const mem = readRememberedJob(sid);
    if (!mem || !mem.jobId) return null;
    const q = (data && data.queue) || {};
    const running = (q.running_jobs || []).find((j) => j.id === mem.jobId);
    if (running) {
      const prog = running.progress || {};
      return {
        id: running.id,
        service_id: running.service_id,
        status: "running",
        percent: prog.percent,
        cancel_requested: running.cancel_requested,
      };
    }
    const pending = (q.pending_jobs || []).find((j) => j.id === mem.jobId);
    if (pending) {
      const prog = pending.progress || {};
      const pos =
        (pending.queue && pending.queue.position) || pending.queue_position;
      return {
        id: pending.id,
        service_id: pending.service_id,
        status: "pending",
        percent: prog.percent,
        cancel_requested: pending.cancel_requested,
        queue_position: pos,
      };
    }
    return null;
  }

  function atualizarPillStatus(pill, data) {
    const queue = (data && data.queue) || {};
    const running = Number(data.running ?? queue.running) || 0;
    const pending = Number(data.pending ?? queue.pending) || 0;
    const maxSlots = Number(data.max_concurrent ?? queue.max_concurrent) || 4;
    const myJob = resolveMyJob(data);
    pill.classList.remove("offline");

    if (running === 0 && pending === 0) {
      syncCancelFromHealth(null);
      pill.textContent = "Online";
      pill.title = "Servidor online — nenhum processo na fila";
      pill.classList.add("online");
      pill.classList.remove("running");
      return;
    }

    let texto = `Online · ${running}/${maxSlots} rodando`;
    let title = texto;

    if (myJob && myJob.status === "running") {
      if (!boundServiceId || myJob.service_id === boundServiceId) {
        syncCancelFromHealth(myJob);
      }
      const nome = jobDisplayName(myJob);
      const prog = formatJobProgressText(myJob);
      if (prog) texto += ` · ${nome} ${prog}`;
      else if (myJob.cancel_requested) texto += ` · ${nome} cancelando…`;
      else texto += ` · ${nome} rodando`;
      title = texto;
    } else if (myJob && myJob.status === "pending") {
      if (
        boundServiceId &&
        myJob.service_id === boundServiceId
      ) {
        const mem = readRememberedJob(boundServiceId);
        if (mem && mem.jobId === myJob.id) {
          currentJobId = myJob.id;
          setCancelVisible(true);
          const runBtn = el("btn-run");
          if (runBtn) runBtn.disabled = true;
        }
      }
      const nome = jobDisplayName(myJob);
      const pos = formatFilaPosicao(
        myJob.queue_position ||
          (myJob.queue && myJob.queue.position) ||
          1
      );
      texto += ` · ${nome} · Na fila posição ${pos}`;
      title = `Seu processo aguarda vaga — posição ${pos} na fila`;
    } else {
      if (!boundServiceId) syncCancelFromHealth(null);
      if (pending > 0) texto += ` · ${pending} na fila`;
      title = "Servidor em uso — aguarde sua vez ou inicie um processo";
    }

    pill.textContent = texto;
    pill.title = title;
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

  function isNoisyLog(msg) {
    const m = String(msg || "");
    if (!m.trim()) return true;
    return (
      /UserWarning|FutureWarning|DeprecationWarning/i.test(m) ||
      /huggingface_hub|HF Hub|HF_TOKEN|symlinks by default/i.test(m) ||
      /torch\.quantize|torch_dtype is deprecated|Triggered internally/i.test(m) ||
      /site-packages[\\/](torch|huggingface|transformers|easyocr|docling)/i.test(m) ||
      /Loading weights:|\d+%\|[#█]+/i.test(m) ||
      /Developer Mode|To support symlinks|HF_HUB_DISABLE/i.test(m) ||
      /^\s*w_ih\s*=/.test(m) ||
      /warnings\.warn\(/i.test(m) ||
      /\[OCR\]\s*(Tentando|Usando|Escolhido)|\[OCR\].*chars, score=/i.test(m) ||
      /Texto nativo insuficiente|OCR multi-motor/i.test(m) ||
      /Using CPU\.|CUDA not available|Neither CUDA nor MPS/i.test(m) ||
      /\[PULADO\]|fora do filtro|sem ano no link \(filtro/i.test(m) ||
      /site-packages|\\\\Users\\\\|\/opt\/opto-automacoes\/centro-automacoes\/venv/i.test(m)
    );
  }

  function shouldAggregateLog(rawMsg, msg) {
    const r = String(rawMsg || "");
    const m = String(msg || "");
    return (
      /^\s*\[OK\]/i.test(r) ||
      /^\[DOWN\]/i.test(r) ||
      /^Baixou:/i.test(m) ||
      /^baixou:/i.test(m) ||
      /^arquivo enviado/i.test(m)
    );
  }

  function shortPathInMsg(msg) {
    return String(msg || "").replace(
      /(?:[A-Za-z]:\\|\/)?(?:[^\s\\/]+[\\/]){2,}([^\s\\/]+(?:[\\/][^\s\\/]+)?)/g,
      "…/$1"
    );
  }

  const LOG_MODULES = {
    inicio: { label: "Começando", tone: "teal" },
    config: { label: "O que foi configurado", tone: "slate" },
    coleta: { label: "Buscando no site", tone: "blue" },
    item: { label: "Licitação", tone: "indigo" },
    download: { label: "Baixando arquivos", tone: "cyan" },
    leitura: { label: "Lendo documentos", tone: "violet" },
    extracao: { label: "Organizando dados", tone: "amber" },
    planilha: { label: "Montando planilha", tone: "green" },
    contratos: { label: "Contratos", tone: "lime" },
    publicacao: { label: "Publicando no portal", tone: "rose" },
    resumo: { label: "Resultado final", tone: "gold" },
    geral: { label: "Acompanhamento", tone: "mist" },
  };

  function detectLogModule(msg, lvl, currentId) {
    const m = String(msg || "").trim();
    if (!m) return null;

    if (
      /processo iniciado|modo:|ocr:\s*ligado|ocr:\s*desligado|subcategorias|ia local|cancelamento solicitado/i.test(
        m
      )
    ) {
      return { id: "inicio", label: LOG_MODULES.inicio.label, tone: "teal" };
    }
    if (
      /^(entidade|listagem|downloads|planilha|anos|renomear|ia)\s*:/i.test(m) ||
      /^pasta\s*:/i.test(m) ||
      (/motor ['"]?auto|tesseract:|easyocr:/i.test(m) && /OCR:/i.test(m))
    ) {
      return { id: "config", label: LOG_MODULES.config.label, tone: "slate" };
    }
    if (
      /coletando|raspando|licita[cç][aã]o\(ões\) a processar|via api rest|via html/i.test(m)
    ) {
      return { id: "coleta", label: LOG_MODULES.coleta.label, tone: "blue" };
    }

    const itemMatch = m.match(/\[(\d+)\s*\/\s*(\d+)/);
    if (itemMatch && (/^──/.test(m) || /%\]/.test(m) || /\[[\-=]+\]/.test(m))) {
      let titulo = m
        .replace(/^──\s*/, "")
        .replace(/\[\d+\s*\/\s*\d+[^\]]*\]\s*/g, "")
        .replace(/\[[\-=]+\]\s*/g, "")
        .trim();
      if (titulo.length > 42) titulo = titulo.slice(0, 40).trim() + "…";
      const label = titulo
        ? `Licitação ${itemMatch[1]} de ${itemMatch[2]} · ${titulo}`
        : `Licitação ${itemMatch[1]} de ${itemMatch[2]}`;
      return { id: `item-${itemMatch[1]}`, label, tone: "indigo" };
    }

    if (currentId && String(currentId).startsWith("item")) {
      if (
        /\[DOWN\]|baixou:|baixado:|\[OK\]|salvou:/i.test(m) ||
        /\(OCR\)|\[OCR\]|\[REN\s*\]|\betapa:|lendo .+|Baixando modelo OCR|Modelo OCR|pytesseract|poppler|AVISO/i.test(
          m
        )
      ) {
        return null;
      }
    }

    if (/^PÁGINA:|^PAGINA:/i.test(m)) {
      return {
        id: "pagina-atual",
        label:
          "Página · " +
          m
            .replace(/^PÁGINA:\s*/i, "")
            .replace(/^PAGINA:\s*/i, "")
            .slice(0, 42),
        tone: "blue",
      };
    }
    if (
      /RESUMO GERAL|Total baixados|Paginas na fila|Paginas com falha|Pastas com arquivos/i.test(
        m
      )
    ) {
      return { id: "resumo", label: LOG_MODULES.resumo.label, tone: "gold" };
    }

    if (/\[DOWN\]|baixando anexo|arquivo enviado/i.test(m)) {
      return { id: "download", label: LOG_MODULES.download.label, tone: "cyan" };
    }
    if (
      /\(OCR\)|\[OCR\]|lendo .+ INTEIRO|modelo OCR|Baixando modelo OCR|pytesseract|poppler/i.test(
        m
      )
    ) {
      return { id: "leitura", label: LOG_MODULES.leitura.label, tone: "violet" };
    }
    if (/\[REN\s*\]|preenchendo planilha|auditoria \(origem/i.test(m)) {
      return { id: "extracao", label: LOG_MODULES.extracao.label, tone: "amber" };
    }
    if (
      /planilhas oficiais|subirLicitacoes|subirDocumentos|contratos\.xlsx|aba 'Auditoria'/i.test(
        m
      )
    ) {
      return { id: "planilha", label: LOG_MODULES.planilha.label, tone: "green" };
    }
    if (
      /contratos separados|pasta Contratos|portaria de fiscal|TESTES CONTRATO/i.test(m)
    ) {
      return {
        id: "contratos",
        label: LOG_MODULES.contratos.label,
        tone: "lime",
      };
    }
    if (
      /\[-> REPASSE\]|Clicou em Publicar|Clicou em Anexar|Clicou em Finalizar|Clicou no lapis|Dialogo 'Anexar|Mes e Ano|Valor Previsto|Valor Realizado|Descri[cç][aã]o =/i.test(
        m
      )
    ) {
      return {
        id: "publicacao",
        label: LOG_MODULES.publicacao.label,
        tone: "rose",
      };
    }
    if (
      /^(Conclu[ií]do|CANCELADO)/i.test(m) ||
      /Resumo —|Prontas:|Erros:\s*\d|OK:\s*\d|CONCLUIDO|fila interrompida|PENDENTES\//i.test(
        m
      )
    ) {
      return { id: "resumo", label: LOG_MODULES.resumo.label, tone: "gold" };
    }
    if (/^►\s/.test(m)) {
      if (/planilha|upload|oficial/i.test(m)) {
        return { id: "planilha", label: LOG_MODULES.planilha.label, tone: "green" };
      }
      if (/colet/i.test(m)) {
        return { id: "coleta", label: LOG_MODULES.coleta.label, tone: "blue" };
      }
      if (/contrat/i.test(m)) {
        return {
          id: "contratos",
          label: LOG_MODULES.contratos.label,
          tone: "lime",
        };
      }
    }
    return null;
  }

  function humanizeLogMsg(msg) {
    let m = String(msg || "").replace(/\s+/g, " ").trim();
    if (!m) return "";

    // Modelos / ruído técnico → frases claras
    if (/Downloading detection model/i.test(m)) {
      return "Preparando a leitura de PDFs escaneados (primeira vez pode demorar)…";
    }
    if (/Downloading recognition model/i.test(m)) {
      return "Baixando o reconhecimento de texto dos PDFs…";
    }
    if (/Loading weights:\s*100%/i.test(m)) {
      return "Leitor de PDF escaneado pronto.";
    }
    if (/por\.traineddata|tessdata\/por/i.test(m)) {
      return "Falta o português no Tesseract (arquivo por.traineddata). Sem isso, PDFs escaneados ficam difíceis de ler.";
    }
    if (/poppler/i.test(m) && /PATH|instal/i.test(m)) {
      return "Falta o programa Poppler neste computador (ajuda a abrir PDFs). Peça à equipe de TI para instalar.";
    }
    if (/WinError 1114|biblioteca de v[ií]nculo din[aâ]mico/i.test(m)) {
      return "O leitor EasyOCR não abriu neste PC. Vamos tentar outra forma de ler o PDF.";
    }
    if (/easyocr.*falhou|AVISO.*easyocr/i.test(m)) {
      return "Não foi possível usar o EasyOCR neste arquivo. Tentando outra opção…";
    }
    if (/paddleocr.*falhou|AVISO.*paddle/i.test(m)) {
      return "Não foi possível usar o PaddleOCR neste arquivo. Tentando outra opção…";
    }
    if (/tesseract.*falhou|AVISO.*tesseract/i.test(m)) {
      return "O Tesseract não conseguiu ler este PDF. Continuando…";
    }
    if (/Motor OCR .+ removido|docling|surya/i.test(m) && /auto|removid/i.test(m)) {
      return "Um leitor antigo foi trocado pelo modo automático.";
    }

    // Início / painel
    let mm;
    mm = m.match(/^Processo iniciado\s*[—\-–]?\s*(.+)$/i);
    if (mm) {
      const mapa = {
        licitacoes: "licitações",
        tcm_licitacoes: "licitações TCM",
        repasses: "repasses",
        normas: "normas",
        categorias: "categorias",
        "pub-repasses": "publicação de repasses",
        publicacao: "publicação",
        sessao: "sessão",
        contratos: "contratos",
        documentos: "documentos",
        mapa: "mapa",
      };
      const nome = mapa[String(mm[1]).trim().toLowerCase()] || mm[1].trim();
      return `Começamos o processo de ${nome}.`;
    }
    mm = m.match(/^Modo:\s*(.+)$/i);
    if (mm) {
      let modo = mm[1];
      modo = modo.replace(/Completo\s*\([^)]*\)/i, "completo: baixar, ler e montar a planilha");
      modo = modo.replace(/s[oó] baixar|so_baixar/i, "somente baixar arquivos");
      modo = modo.replace(/s[oó] planilha|so_planilha/i, "somente montar a planilha (sem baixar de novo)");
      return `Como vai funcionar: ${modo}.`;
    }
    if (/^OCR:\s*ligado/i.test(m)) {
      return "Leitura de PDFs escaneados (imagem): ligada.";
    }
    if (/^OCR:\s*desligado/i.test(m)) {
      return "Leitura de PDFs escaneados: desligada.";
    }
    if (/Subcategorias fracassadas\/desertas/i.test(m)) {
      return "Também vamos incluir licitações fracassadas e desertas.";
    }
    if (/^IA local:\s*desligada/i.test(m)) {
      return "Ajuda com inteligência artificial: desligada.";
    }
    if (/^IA local/i.test(m) || /^IA\s*:/i.test(m)) {
      return "Ajuda com inteligência artificial: ligada (só quando faltar algum dado).";
    }
    if (/Cancelamento solicitado/i.test(m)) {
      return "Você pediu para parar. Encerrando com segurança…";
    }

    // Config
    mm = m.match(/^Entidade\s*:\s*(.+)$/i);
    if (mm) return `Órgão / site: ${mm[1]}`;
    mm = m.match(/^Listagem\s*:\s*(.+)$/i);
    if (mm) return `Página da lista: ${mm[1]}`;
    mm = m.match(/^Downloads\s*:\s*(.+)$/i);
    if (mm) return `Pasta onde salvamos os arquivos: ${mm[1]}`;
    mm = m.match(/^Planilha\s*:\s*(.+)$/i);
    if (mm) {
      return `Planilha que será gerada: ${mm[1].replace(/\s*\(modelo:[^)]*\)\s*$/i, "").trim()}`;
    }
    mm = m.match(/^Anos\s*:\s*(.+)$/i);
    if (mm) {
      const a = mm[1].trim();
      return a.toLowerCase() === "todos"
        ? "Anos: todos os disponíveis."
        : `Anos selecionados: ${a}.`;
    }
    mm = m.match(/^Renomear\s*:\s*(.+)$/i);
    if (mm) return `Renomear arquivos automaticamente: sim (${mm[1]}).`;
    mm = m.match(/^Pasta\s*:\s*(.+)$/i);
    if (mm) return `Pasta de trabalho: ${mm[1]}`;
    if (/OCR:\s*motor/i.test(m)) {
      return "Leitores de PDF escaneado: modo automático (escolhe o melhor disponível).";
    }
    if (/LinkDaPasta base/i.test(m)) {
      mm = m.match(/LinkDaPasta base:\s*(.+)$/i);
      return mm
        ? `Link base das pastas: ${mm[1]}`
        : "Link base das pastas configurado.";
    }

    // Coleta
    if (/Coletando via API REST/i.test(m)) {
      return "Buscando licitações pela API do site…";
    }
    if (/Coletando via HTML|Fallback HTML/i.test(m)) {
      return "Buscando licitações pelas páginas do site…";
    }
    mm = m.match(/raspando\s+(\S+)/i);
    if (mm) return `Lendo a página: ${mm[1]}`;
    mm = m.match(/(\d+)\s+licita[cç][aã]o\(ões\)\.\s*$/i);
    if (mm) {
      const n = Number(mm[1]);
      return n === 0
        ? "Nenhuma licitação encontrada nesta página."
        : n === 1
          ? "Encontramos 1 licitação nesta página."
          : `Encontramos ${n} licitações nesta página.`;
    }
    mm = m.match(/(\d+)\s+licita[cç][aã]o\(ões\)\s+a processar/i);
    if (mm) {
      const n = Number(mm[1]);
      return n === 1
        ? "Vamos processar 1 licitação."
        : `Vamos processar ${n} licitações.`;
    }
    if (/API REST indispon/i.test(m)) {
      return "A API do site não respondeu. Vamos buscar pelas páginas normalmente.";
    }

    // Item / etapas
    mm = m.match(/\[(\d+)\s*\/\s*(\d+)[^\]]*\]\s*(?:\[[\-=]+\]\s*)?(.+)$/);
    if (mm && (/^──/.test(m) || /%\]/.test(m) || /\[[\-=]+\]/.test(m))) {
      const titulo = (mm[3] || "").trim();
      return titulo
        ? `Agora: licitação ${mm[1]} de ${mm[2]} — ${titulo}`
        : `Agora: licitação ${mm[1]} de ${mm[2]}.`;
    }
    mm = m.match(/etapa:\s*baixar anexos\s*\((\d+)\s*link/i);
    if (mm) {
      const n = Number(mm[1]);
      return n === 1
        ? "Baixando 1 anexo…"
        : `Baixando ${n} anexos…`;
    }
    if (/etapa:\s*baixar/i.test(m)) return "Baixando os anexos…";
    if (/etapa:\s*ler documentos/i.test(m)) {
      return "Lendo os documentos principais…";
    }
    if (/etapa:\s*/i.test(m)) {
      return m.replace(/^.*etapa:\s*/i, "Próximo passo: ").replace(/\.\.\.$/, "…");
    }

    mm = m.match(/^\[DOWN\]\s*(.+)$/i);
    if (mm) return `Baixou: ${mm[1]}`;
    mm = m.match(/^\[REN\s*\]\s*(.+?)\s*->\s*(.+)$/i);
    if (mm) return `Renomeou o arquivo: ${mm[1]} → ${mm[2]}`;

    mm = m.match(/lendo\s+(.+?)\s+INTEIRO\s*\(([^)]+)\)/i);
    if (mm) return `Lendo ${mm[1].toLowerCase()} por completo: ${mm[2]}`;
    mm = m.match(/lendo\s+(.+)$/i);
    if (mm) return `Lendo: ${mm[1]}`;

    mm = m.match(/^\(OCR\)\s*(.+)$/i);
    if (mm) return `Li o PDF escaneado: ${mm[1]}`;
    if (/Baixando modelo OCR/i.test(m)) {
      return "Preparando a leitura de PDFs escaneados…";
    }
    if (/Modelo OCR carregado/i.test(m)) {
      return "Leitor de PDF escaneado pronto.";
    }

    // Planilha / fim
    if (/Preenchendo planilha/i.test(m)) {
      return "Preenchendo a planilha Excel com os dados encontrados…";
    }
    if (/Planilhas oficiais|licita[cç][aã]o primeiro, contratos depois/i.test(m)) {
      return "Gerando as planilhas oficiais para enviar ao portal…";
    }
    if (/Auditoria \(origem dos dados\)/i.test(m)) {
      return "A planilha tem uma aba “Auditoria” mostrando de onde veio cada informação.";
    }
    mm = m.match(/Resumo\s*[—\-–]\s*Prontas:\s*(\d+)\s*\|\s*Pendentes:\s*(\d+)/i);
    if (mm) {
      return `Resumo: ${mm[1]} prontas para upload · ${mm[2]} pendentes (faltou algum dado).`;
    }
    if (/^Conclu[ií]do\.?$/i.test(m) || /^CONCLUIDO/i.test(m)) {
      return "Tudo certo — processo concluído.";
    }
    if (/CANCELADO|fila interrompida|fila cancelada/i.test(m)) {
      return "Processo interrompido a seu pedido.";
    }
    if (/^1\)\s*Licita/i.test(m)) {
      return "Arquivos de licitação: subirLicitacoes.xlsx e subirDocumentosLicitacoes.xlsx";
    }
    if (/^2\)\s*Contratos/i.test(m)) {
      return "Contratos vão automaticamente para a pasta Contratos/";
    }
    if (/Veja também a aba 'Auditoria'/i.test(m)) {
      return "Se algo faltar, confira a aba Auditoria e a pasta PENDENTES.";
    }
    if (/Pendentes:/i.test(m) && /PENDENTES|relatorio|relatório/i.test(m)) {
      return m.replace(/Pendentes:/i, "Itens pendentes:");
    }

    // Publicação / repasses
    mm = m.match(/\[-> REPASSE\]\s*\[(\d+)\/(\d+)\]\s*(.+)$/i);
    if (mm) return `Publicando repasse ${mm[1]} de ${mm[2]}: ${mm[3]}`;
    if (/Clicou em Publicar/i.test(m)) return "Clicou em Publicar no portal.";
    if (/Clicou em Anexar/i.test(m)) return "Abriu a tela para anexar o PDF.";
    if (/Clicou em Finalizar/i.test(m)) return "Finalizou este item no portal.";
    if (/Clicou no lapis|Clicou no lápis/i.test(m)) {
      return "Abriu a edição do documento (lápis).";
    }
    if (/Dialogo 'Anexar/i.test(m)) return "Apareceu a janela de anexar documentos.";
    if (/Arquivo enviado|Upload na zona/i.test(m)) return "PDF enviado com sucesso.";
    if (/\[OK\]\s*Concluido|\[OK\]\s*Concluído/i.test(m)) {
      return "Item publicado com sucesso.";
    }
    if (/Campo 'Data de Publicacao' nao encontrado|Data de Publicação/i.test(m) && /n[aã]o encontrado|ERRO/i.test(m)) {
      return "Não achamos o campo “Data de Publicação” na tela. Pode ser que o portal tenha mudado.";
    }

    mm = m.match(/^ERRO:\s*(.+)$/i);
    if (mm) {
      const inner = String(mm[1] || "").trim();
      if (/NoneType.*clear/i.test(inner)) {
        return "Problema interno ao reiniciar o resultado. Tente rodar de novo.";
      }
      if (/assigned to before global/i.test(inner)) {
        return "Versão do script desatualizada. Atualize o código e reinicie o painel.";
      }
      return `Problema: ${inner}`;
    }
    if (/NoneType.*clear/i.test(m)) {
      return "Houve um erro interno ao reiniciar o resultado. Tente rodar de novo.";
    }
    if (/assigned to before global/i.test(m)) {
      return "Versão do script desatualizada. Atualize o código e reinicie o painel.";
    }

    // Limpeza genérica
    m = m.replace(/^====\s*/, "").replace(/\s*====$/, "");
    m = m.replace(/^►\s*/, "");
    m = m.replace(/^·\s*/, "");
    m = m.replace(/^──\s*/, "");
    m = m.replace(/^!\s*/, "");
    m = m.replace(/^\(ocr_multi falhou:[^)]*\)/i, "A leitura automática do PDF falhou; tentando outro método…");
    m = m.replace(/^\(EasyOCR n[aã]o instalado[^)]*\)/i, "EasyOCR não está instalado; usando outro leitor.");
    m = m.replace(/^\(Tesseract fraco[^)]*\)/i, "A leitura saiu fraca; tentando outro leitor…");

    if (m.length > 420) m = m.slice(0, 400).trim() + "…";
    return m;
  }

  function beautifyLogMsg(msg) {
    return shortPathInMsg(humanizeLogMsg(msg));
  }

  function findLogModule(box, id) {
    if (!box || !id) return null;
    const safe = String(id).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    return box.querySelector(`.log-module[data-module="${safe}"]`);
  }

  function collapseLogModule(block, userInitiated) {
    if (!block) return;
    block.classList.add("is-collapsed");
    block.classList.remove("is-open");
    const btn = block.querySelector(".log-module-toggle");
    if (btn) btn.setAttribute("aria-expanded", "false");
    if (userInitiated) block.dataset.userCollapsed = "1";
    _atualizarContagemGaveta(block);
  }

  function expandLogModule(block) {
    if (!block) return;
    block.classList.remove("is-collapsed");
    block.classList.add("is-open");
    delete block.dataset.userCollapsed;
    const btn = block.querySelector(".log-module-toggle");
    if (btn) btn.setAttribute("aria-expanded", "true");
    _atualizarContagemGaveta(block);
  }

  function collapseOtherLogModules(box, exceptId) {
    if (!box) return;
    box.querySelectorAll(".log-module").forEach((prev) => {
      if (prev.dataset.module === exceptId) return;
      if (!prev.classList.contains("is-collapsed")) {
        collapseLogModule(prev, false);
      }
    });
  }

  function collapseAllLogModules(box, opts) {
    const modules = [...(box?.querySelectorAll(".log-module") || [])];
    if (!modules.length) return;
    const keepId =
      opts && opts.exceptLast
        ? modules[modules.length - 1].dataset.module
        : opts && opts.exceptId;
    modules.forEach((block) => {
      if (keepId && block.dataset.module === keepId) {
        expandLogModule(block);
      } else {
        collapseLogModule(block, true);
      }
    });
  }

  function bindLogModuleToggle(block, box) {
    const toggle = block.querySelector(".log-module-toggle");
    if (!toggle || toggle.dataset.bound) return;
    toggle.dataset.bound = "1";
    toggle.addEventListener("click", () => {
      const willCollapse = !block.classList.contains("is-collapsed");
      if (willCollapse) {
        collapseLogModule(block, true);
      } else {
        expandLogModule(block);
        box._logActiveModule = block.dataset.module;
        box._logModuleId = block.dataset.module;
        box._logModuleBody = block.querySelector(".log-module-body");
      }
    });
  }

  function ensureLogModule(box, mod) {
    const id = (mod && mod.id) || "geral";
    const tone = (mod && mod.tone) || (LOG_MODULES[id] || LOG_MODULES.geral).tone;
    const label =
      (mod && mod.label) || (LOG_MODULES[id] || LOG_MODULES.geral).label;

    let block = findLogModule(box, id);
    if (block) {
      box._logModuleId = id;
      box._logModuleBody = block.querySelector(".log-module-body");
      const lbl = block.querySelector(".log-module-label");
      if (lbl && mod && mod.label && mod.label.length > (lbl.textContent || "").length) {
        lbl.textContent = mod.label;
      }
      bindLogModuleToggle(block, box);
      if (!block.dataset.userCollapsed) {
        expandLogModule(block);
        collapseOtherLogModules(box, id);
      }
      box._logActiveModule = id;
      return box._logModuleBody;
    }

    collapseOtherLogModules(box, id);
    box._logActiveModule = id;

    block = document.createElement("section");
    block.className = `log-module log-tone-${tone} is-open`;
    block.dataset.module = id;
    block.innerHTML =
      '<button type="button" class="log-module-head log-module-toggle" aria-expanded="true">' +
      '<span class="log-module-row">' +
      '<span class="log-module-dot" aria-hidden="true"></span>' +
      '<span class="log-module-label"></span>' +
      '<span class="log-module-count" hidden></span>' +
      '<span class="log-module-chevron" aria-hidden="true"></span>' +
      "</span>" +
      '<span class="log-module-preview" hidden></span>' +
      "</button>" +
      '<div class="log-module-body"></div>';
    block.querySelector(".log-module-label").textContent = label;
    bindLogModuleToggle(block, box);
    box.appendChild(block);
    box._logModuleId = id;
    box._logModuleBody = block.querySelector(".log-module-body");
    return box._logModuleBody;
  }

  function _atualizarContagemGaveta(block) {
    if (!block) return;
    const lines = block.querySelectorAll(".log-module-body .log-line");
    const n = lines.length;
    const badge = block.querySelector(".log-module-count");
    if (badge) {
      if (n > 0) {
        badge.hidden = false;
        badge.textContent = n === 1 ? "1 linha" : n + " linhas";
      } else {
        badge.hidden = true;
      }
    }
    const preview = block.querySelector(".log-module-preview");
    if (!preview) return;
    const lastMsg = block.querySelector(
      ".log-module-body .log-line:last-child .msg"
    );
    const aggMsg = block.querySelector(".log-line[data-agg] .msg");
    const src = lastMsg || aggMsg;
    const txt = src ? String(src.textContent || "").trim() : "";
    if (txt && block.classList.contains("is-collapsed")) {
      preview.hidden = false;
      preview.textContent = txt.length > 90 ? txt.slice(0, 88).trim() + "…" : txt;
    } else {
      preview.hidden = true;
      preview.textContent = "";
    }
  }

  function appendAggregatedLog(body, msg, lvl) {
    const kind = "downloads";
    let row = body.querySelector(`.log-line[data-agg="${kind}"]`);
    if (!row) {
      row = document.createElement("div");
      row.className = "log-line log-ok log-agg log-compact";
      row.dataset.agg = kind;
      row.innerHTML = '<span class="msg"></span>';
      body.appendChild(row);
    }
    const n = (parseInt(row.dataset.count || "0", 10) || 0) + 1;
    row.dataset.count = String(n);
    const short = String(msg || "")
      .replace(/^Baixou:\s*/i, "")
      .replace(/^\[OK\]\s*/i, "")
      .trim();
    const tail =
      short.length > 36 ? short.slice(0, 34).trim() + "…" : short;
    row.querySelector(".msg").textContent =
      n === 1
        ? msg
        : `${n} arquivos baixados · último: ${tail || "…"}`;
    const block = body.closest(".log-module");
    if (block) _atualizarContagemGaveta(block);
    return n;
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

    const rawMsg = String(msg || "").trim();
    msg = beautifyLogMsg(msg);
    if (!msg || msg === "— fim —" || msg === "- fim -") return;
    if (isNoisyLog(rawMsg) || isNoisyLog(msg)) return;

    if (/^=+$/.test(msg) || /^-+$/.test(msg) || /^·+$/.test(msg)) {
      const body = box._logModuleBody || box;
      const sep = document.createElement("div");
      sep.className = "log-sep";
      sep.setAttribute("aria-hidden", "true");
      body.appendChild(sep);
      box.scrollTop = box.scrollHeight;
      return;
    }

    const detected = detectLogModule(rawMsg, lvl, box._logModuleId);
    let mod =
      detected ||
      (box._logModuleId
        ? { id: box._logModuleId }
        : { id: "geral", label: LOG_MODULES.geral.label, tone: "mist" });
    if (/^PÁGINA:|^PAGINA:/i.test(rawMsg)) {
      box._paginaSeq = (box._paginaSeq || 0) + 1;
      const titulo = rawMsg
        .replace(/^PÁGINA:\s*/i, "")
        .replace(/^PAGINA:\s*/i, "")
        .trim()
        .slice(0, 42);
      mod = {
        id: `pagina-${box._paginaSeq}`,
        label: titulo
          ? `Página ${box._paginaSeq} · ${titulo}`
          : `Página ${box._paginaSeq}`,
        tone: "blue",
      };
    }
    const isNewItemBlock =
      detected &&
      String(detected.id).startsWith("item-") &&
      detected.id !== box._logModuleId;
    const body = ensureLogModule(box, mod);

    if (shouldAggregateLog(rawMsg, msg)) {
      const n = appendAggregatedLog(body, msg, lvl);
      const block = body.closest(".log-module");
      if (block && block.classList.contains("is-collapsed")) {
        _atualizarContagemGaveta(block);
      }
      if (n === 1 || n % 8 === 0) {
        box.scrollTop = box.scrollHeight;
      }
      return;
    }

    // Título do bloco já mostra a licitação — evita repetir a mesma frase
    if (isNewItemBlock) {
      msg = "Começando esta licitação…";
    }

    const last = body.querySelector(".log-line:last-child .msg");
    if (last && last.textContent === msg) return;

    const isSection =
      /^(fonte|resumo|download de normas|processando|p[aá]gina:)/i.test(rawMsg) ||
      rawMsg.includes("FONTE (") ||
      /^──\s*\[/.test(rawMsg) ||
      /^etapas?:/i.test(rawMsg) ||
      /\betapa:\s/i.test(rawMsg) ||
      /^►\s/.test(rawMsg) ||
      /^Baixando modelo OCR/i.test(rawMsg) ||
      /^Modelo OCR/i.test(rawMsg) ||
      /Processo iniciado|licita[cç][aã]o\(ões\) a processar|Planilhas oficiais|Conclu[ií]do/i.test(
        rawMsg
      );

    const labels = {
      info: "info",
      warn: "atenção",
      error: "erro",
      ok: "ok",
    };

    const isDownloadChild =
      /^(baixou:|baixado:|salvou:|arquivo:)/i.test(msg) ||
      /^\[DOWN\]/i.test(rawMsg);
    const isDownloadHead = /^baixando\b/i.test(msg);
    if (/^(baixou:|conclu[ií]da|pronto|✓)/i.test(msg) && lvl === "info") {
      lvl = "ok";
    }

    const div = document.createElement("div");
    div.className = `log-line log-${lvl}${isSection ? " log-section-line" : ""}`;
    if (isDownloadChild) div.classList.add("log-child");
    if (!(isDownloadHead || isSection) && lvl === "info") {
      div.classList.add("log-quiet");
    }
    div.innerHTML =
      '<span class="t"></span><span class="lv"></span><span class="msg"></span>';
    div.querySelector(".t").textContent = time || "--:--";
    div.querySelector(".lv").textContent = labels[lvl] || lvl;
    div.querySelector(".msg").textContent = msg;
    body.appendChild(div);

    const block = body.closest(".log-module");
    if (block) _atualizarContagemGaveta(block);

    if (!block || !block.dataset.userCollapsed) {
      box.scrollTop = box.scrollHeight;
    }
  }

  function resetLogConsole(box) {
    if (!box) return;
    box.innerHTML = '<p class="log-empty">Aguardando — o acompanhamento aparece aqui…</p>';
    box._logModuleId = null;
    box._logModuleBody = null;
    box._logActiveModule = null;
    box._paginaSeq = 0;
  }

  function ensureLogToolbar() {
    const box = el("log-console");
    const wrap = box && box.closest(".log-wrap");
    if (!wrap || wrap.querySelector(".log-toolbar")) return;
    const bar = document.createElement("div");
    bar.className = "log-toolbar";
    bar.innerHTML =
      '<button type="button" class="btn btn-ghost btn-sm" id="btn-log-collapse">Recolher gavetas</button>' +
      '<button type="button" class="btn btn-ghost btn-sm" id="btn-log-expand">Expandir tudo</button>' +
      '<span class="log-toolbar-hint">Clique no título da gaveta para abrir ou fechar. Downloads iguais são agrupados.</span>';
    box.parentNode.insertBefore(bar, box);
    bar.querySelector("#btn-log-collapse")?.addEventListener("click", () => {
      collapseAllLogModules(box, { exceptId: box._logActiveModule });
    });
    bar.querySelector("#btn-log-expand")?.addEventListener("click", () => {
      box.querySelectorAll(".log-module").forEach((b) => {
        delete b.dataset.userCollapsed;
        expandLogModule(b);
      });
    });
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
      kind === "error"
        ? "Erro"
        : kind === "warn"
          ? "Cancelado"
          : kind === "info"
            ? "Fila"
            : "Concluído";
    note.innerHTML = `<strong>${title}</strong><span>${message}</span>`;
    host.appendChild(note);
    requestAnimationFrame(() => note.classList.add("is-in"));
    setTimeout(() => {
      note.classList.remove("is-in");
      note.classList.add("is-out");
      setTimeout(() => note.remove(), 380);
    }, 6500);
  }
  setUploadNotifier(showNotice);

  const SERVICE_LABELS = {
    documentos: "Baixar Documentos",
    categorias: "Baixar por Categoria",
    normas: "Baixar Extração Pro",
    licitacoes: "Baixar Licitações CR2",
    tcm_licitacoes: "Baixar Licitações TCM-PA",
    repasses: "Baixar Extração de Repasses",
    contratos: "Contratos / Aditivos",
    publicacao: "Publicação CR2",
    sessao: "Publicação de Sessão",
    pub_repasses: "Publicação de Repasses",
    mapa: "Mapa do Site",
    dic_est_ter: "Publicação Dic/Est/Ter",
  };

  const STATUS_PT = {
    pending: "Na fila",
    running: "Em andamento",
    completed: "Finalizado",
    failed: "Com problema",
    cancelled: "Interrompido",
  };

  let es = null;
  let streamJobId = null;
  let currentJobId = null;
  let noticeShownFor = null;
  let zipRetryFor = null;
  let boundServiceId = null;
  let workspaceCache = null;
  let currentUsername = null;
  let authRequired = false;

  function ownerShortName(owner) {
    const raw = String(owner || currentUsername || "local").trim();
    if (!raw) return "local";
    const at = raw.indexOf("@");
    return (at > 0 ? raw.slice(0, at) : raw).trim() || "local";
  }

  function downloadLabel(serviceId, owner) {
    const base = SERVICE_LABELS[serviceId] || serviceId || "Download";
    const withBaixar = /^baixar\s/i.test(base) ? base : `Baixar ${base}`;
    return `${withBaixar} - ${ownerShortName(owner)}`;
  }

  function servicePrettyName(serviceId) {
    const raw = SERVICE_LABELS[serviceId] || serviceId || "Automação";
    return String(raw).replace(/^baixar\s+/i, "").trim() || "Automação";
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function ownersMatch(a, b) {
    if (!a || !b) return false;
    return String(a).trim().toLowerCase() === String(b).trim().toLowerCase();
  }
  let resumedOnce = false;

  const _PATH_FIELD_IDS = new Set([
    "pasta_base",
    "pasta_saida",
  ]);

  const _SKIP_WORKSPACE_FILL = new Set([
    "pasta_rgf",
    "pasta_rreo",
    "pasta_balancete",
    "pasta_balanco",
    "pasta_sessoes",
  ]);

  function _pathFieldWrap(node) {
    return node.closest(".field") || node.closest("label.field");
  }

  function _setPathFieldVisible(node, visible) {
    const wrap = _pathFieldWrap(node);
    if (wrap) {
      wrap.hidden = !visible;
      wrap.classList.toggle("field--path-server-hidden", !visible);
    }
    if (!visible) node.removeAttribute("required");
  }

  function _ensureWorkspaceHint(nearNode) {
    let hint = el("workspace-hint");
    if (hint || !nearNode) return hint;
    const fs = nearNode.closest("fieldset") || nearNode.closest("form");
    if (!fs) return null;
    hint = document.createElement("p");
    hint.id = "workspace-hint";
    hint.className = "field-hint workspace-hint";
    fs.insertBefore(hint, fs.firstChild);
    return hint;
  }

  async function loadWorkspace(fieldIds) {
    try {
      const r = await authFetch(`${API}/api/workspace`);
      if (!r.ok) return null;
      const ws = await r.json();
      workspaceCache = ws;
      const ids = fieldIds || [
        "pasta_base",
        "pasta_saida",
      ];

      if (ws.local_mode) {
        ids.forEach((id) => {
          const node = el(id);
          if (node) _setPathFieldVisible(node, true);
        });
        return ws;
      }

      const serverHint =
        "Os arquivos ficam na sua pasta no servidor (por usuário). Ao terminar, baixe o ZIP no seu PC.";

      ids.forEach((id) => {
        const node = el(id);
        if (!node || _SKIP_WORKSPACE_FILL.has(id)) return;
        node.value = ws.output_dir;
        if (!node.placeholder) node.placeholder = ws.output_dir;
        if (_PATH_FIELD_IDS.has(id)) _setPathFieldVisible(node, false);
      });

      const anchor = ids.map((id) => el(id)).find(Boolean);
      const hint = el("workspace-hint") || _ensureWorkspaceHint(anchor);
      if (hint) {
        hint.textContent = serverHint;
        hint.hidden = false;
      }
      return ws;
    } catch (_) {
      return null;
    }
  }

  async function downloadJobArtifact(jobId, opts) {
    const dismiss = !opts || opts.dismiss !== false;
    try {
      const r = await authFetch(`${API}/api/jobs/${jobId}/download`);
      if (!r.ok) return false;
      const blob = await r.blob();
      let fname = downloadLabel(boundServiceId, currentUsername) + ".zip";
      const cd = r.headers.get("content-disposition") || "";
      const m = /filename\*?=(?:UTF-8''|\"?)([^\";]+)/i.exec(cd);
      if (m) {
        try {
          fname = decodeURIComponent(m[1].replace(/\"/g, ""));
        } catch (_) {
          fname = m[1].replace(/\"/g, "");
        }
      }
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      if (dismiss) markDownloadDismissed(jobId);
      pollDownloadsReady().catch(() => {});
      return true;
    } catch (_) {
      return false;
    }
  }

  function markDownloadDismissed(jobId) {
    if (!jobId) return;
    try {
      sessionStorage.setItem("opto-dl-done-" + jobId, "1");
    } catch (_) {}
    try {
      const key = "opto-dl-dismissed:" + (currentUsername || "anon");
      const raw = localStorage.getItem(key);
      const map = raw ? JSON.parse(raw) : {};
      if (!map || typeof map !== "object") return;
      map[jobId] = Date.now();
      // limpa dismissões com mais de 14 dias
      const cut = Date.now() - 14 * 24 * 60 * 60 * 1000;
      Object.keys(map).forEach((id) => {
        if (!map[id] || map[id] < cut) delete map[id];
      });
      localStorage.setItem(key, JSON.stringify(map));
    } catch (_) {}
  }

  function isDownloadDismissed(jobId) {
    if (!jobId) return true;
    try {
      if (sessionStorage.getItem("opto-dl-done-" + jobId) === "1") return true;
    } catch (_) {}
    try {
      const key = "opto-dl-dismissed:" + (currentUsername || "anon");
      const raw = localStorage.getItem(key);
      const map = raw ? JSON.parse(raw) : {};
      return !!(map && map[jobId]);
    } catch (_) {
      return false;
    }
  }

  function myTrackedJobsKey() {
    return "opto-my-jobs:" + (currentUsername || "anon");
  }

  function trackMyJob(jobId) {
    if (!jobId) return;
    try {
      const raw = localStorage.getItem(myTrackedJobsKey());
      const map = raw ? JSON.parse(raw) : {};
      if (!map || typeof map !== "object") return;
      map[jobId] = Date.now();
      const cut = Date.now() - 7 * 24 * 60 * 60 * 1000;
      Object.keys(map).forEach((id) => {
        if (!map[id] || map[id] < cut) delete map[id];
      });
      localStorage.setItem(myTrackedJobsKey(), JSON.stringify(map));
    } catch (_) {}
  }

  function isTrackedMyJob(jobId) {
    if (!jobId) return false;
    try {
      const raw = localStorage.getItem(myTrackedJobsKey());
      const map = raw ? JSON.parse(raw) : {};
      return !!(map && map[jobId]);
    } catch (_) {
      return false;
    }
  }

  function ensureLogTitleRow() {
    const head = document.querySelector(".log-wrap .section-head");
    if (!head) return null;
    let row = head.querySelector(".log-title-row");
    if (!row) {
      row = document.createElement("div");
      row.className = "log-title-row";
      const h2 = head.querySelector(":scope > h2");
      if (h2) {
        head.insertBefore(row, h2);
        row.appendChild(h2);
      } else {
        head.insertBefore(row, head.firstChild);
      }
    }
    return row;
  }

  function ensureDownloadButton() {
    let btn = el("btn-download");
    if (btn && btn.tagName === "A") {
      const next = document.createElement("button");
      next.type = "button";
      next.id = "btn-download";
      next.className = "btn btn-download btn-download-idle btn-sm";
      next.innerHTML =
        '<span class="btn-download-icon" aria-hidden="true">↓</span><span class="btn-download-text">Baixar ZIP</span>';
      btn.replaceWith(next);
      btn = next;
    }
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-download btn-download-idle btn-sm";
      btn.id = "btn-download";
      btn.innerHTML =
        '<span class="btn-download-icon" aria-hidden="true">↓</span><span class="btn-download-text">Baixar ZIP</span>';
      btn.disabled = true;
      btn.setAttribute("aria-disabled", "true");
    } else {
      btn.classList.add("btn-download");
    }
    const titleRow = ensureLogTitleRow();
    if (titleRow) {
      titleRow.appendChild(btn);
      return btn;
    }
    let bar = document.querySelector(".log-wrap .job-bar") || document.querySelector(".job-bar");
    if (!bar) {
      const logWrap = document.querySelector(".log-wrap");
      if (logWrap) {
        bar = document.createElement("div");
        bar.className = "job-bar";
        logWrap.appendChild(bar);
      }
    }
    if (bar) bar.prepend(btn);
    else {
      const head =
        document.querySelector(".log-wrap .section-head") || document.querySelector(".acao-row");
      if (head) head.prepend(btn);
      else document.body.appendChild(btn);
    }
    return btn;
  }

  function applyDownloadButtonState(btn, jobId, ready, opts) {
    if (!btn) return;
    const waiting = !!(opts && opts.waiting);
    const svc = (opts && opts.serviceId) || boundServiceId;
    const owner = (opts && opts.owner) || currentUsername;
    const fullName = downloadLabel(svc, owner);
    const textEl = () => {
      let t = btn.querySelector(".btn-download-text");
      if (!t) {
        btn.innerHTML =
          '<span class="btn-download-icon" aria-hidden="true">↓</span><span class="btn-download-text"></span>';
        t = btn.querySelector(".btn-download-text");
      }
      return t;
    };
    if (ready && jobId) {
      btn.disabled = false;
      btn.removeAttribute("aria-disabled");
      btn.className = "btn btn-download btn-download-ready btn-sm";
      if (btn.id === "btn-download-nav") btn.classList.add("nav-download");
      textEl().textContent = "Baixar ZIP";
      btn.title = fullName;
      btn.setAttribute("aria-label", fullName);
      btn.onclick = () => downloadJobArtifact(jobId);
    } else {
      btn.disabled = true;
      btn.setAttribute("aria-disabled", "true");
      btn.className = "btn btn-download btn-download-idle btn-sm";
      if (btn.id === "btn-download-nav") btn.classList.add("nav-download");
      textEl().textContent = waiting ? "Preparando ZIP…" : "Baixar ZIP";
      btn.title = waiting
        ? "Disponível quando o processo terminar"
        : fullName;
      btn.setAttribute("aria-label", btn.title);
      btn.onclick = null;
    }
  }

  function isJobServicePage(serviceId) {
    return !!(
      boundServiceId &&
      serviceId &&
      boundServiceId === serviceId &&
      document.querySelector(".log-wrap")
    );
  }

  function ensureNavDownloadButton() {
    let btn = el("btn-download-nav");
    if (btn) return btn;
    btn = document.createElement("button");
    btn.type = "button";
    btn.id = "btn-download-nav";
    btn.className = "btn btn-download btn-download-idle btn-sm nav-download";
    btn.hidden = true;
    btn.innerHTML =
      '<span class="btn-download-icon" aria-hidden="true">↓</span><span class="btn-download-text">Baixar ZIP</span>';
    const logout = el("btn-logout");
    if (logout && logout.parentNode) {
      logout.insertAdjacentElement("beforebegin", btn);
    } else {
      const pill = el("api-pill");
      if (pill && pill.parentNode) {
        pill.insertAdjacentElement("afterend", btn);
      } else {
        const top = document.querySelector("header.top");
        if (top) top.appendChild(btn);
      }
    }
    return btn;
  }

  function hideNavDownloadButton() {
    const btn = el("btn-download-nav");
    if (btn) btn.hidden = true;
  }

  function setNavDownloadButton(jobId, ready, opts) {
    if (workspaceCache && workspaceCache.local_mode) {
      hideNavDownloadButton();
      return;
    }
    const btn = ensureNavDownloadButton();
    if (!btn) return;
    btn.hidden = !(ready && jobId);
    if (btn.hidden) return;
    applyDownloadButtonState(btn, jobId, ready, opts);
  }

  function syncDownloadUi(jobId, serviceId, ready, opts = {}) {
    if (workspaceCache && workspaceCache.local_mode) {
      hideNavDownloadButton();
      const logBtn = el("btn-download");
      if (logBtn) logBtn.hidden = true;
      return;
    }
    const sid = serviceId || boundServiceId;
    const waiting = !!(opts && opts.waiting);
    if (isJobServicePage(sid)) {
      hideNavDownloadButton();
      setJobDownloadButton(jobId, ready, { ...opts, serviceId: sid, waiting });
      return;
    }
    const logBtn = el("btn-download");
    if (logBtn) logBtn.hidden = true;
    if (ready && jobId && !isDownloadDismissed(jobId)) {
      setNavDownloadButton(jobId, true, { ...opts, serviceId: sid });
    } else if (waiting && isJobServicePage(boundServiceId)) {
      hideNavDownloadButton();
      setJobDownloadButton(jobId, false, {
        ...opts,
        serviceId: boundServiceId,
        waiting: true,
      });
    } else {
      hideNavDownloadButton();
    }
  }

  function setJobDownloadButton(jobId, ready, opts) {
    if (workspaceCache && workspaceCache.local_mode) {
      const hide = el("btn-download");
      if (hide) hide.hidden = true;
      hideNavDownloadButton();
      return;
    }
    const btn = ensureDownloadButton();
    if (!btn) return;
    btn.hidden = false;
    applyDownloadButtonState(btn, jobId, ready, opts);
  }

  function initJobDownloadButton() {
    if (workspaceCache && workspaceCache.local_mode) return;
    ensureLogTitleRow();
    ensureNavDownloadButton();
    setJobDownloadButton(null, false, { waiting: false });
  }

  function showJobDownloadButton(jobId, serviceId) {
    syncDownloadUi(jobId, serviceId || boundServiceId, true);
  }

  function ensureDownloadBanner() {
    // Banner flutuante removido — poluía a subnav. Só o botão da página.
    const bar = el("opto-dl-banner");
    if (bar) {
      bar.remove();
      document.body.classList.remove("has-dl-banner");
    }
    return null;
  }

  function downloadsForCurrentUser(items) {
    const list = items || [];
    const mine = list.filter((j) => {
      if (!j || !j.id) return false;
      if (currentUsername) {
        if (!ownersMatch(j.owner, currentUsername)) return false;
      } else if (authRequired) {
        return false;
      } else if (j.owner) {
        return false;
      }
      return isTrackedMyJob(j.id);
    });
    return mine.slice(0, 1);
  }

  function renderDownloadBanner(_items) {
    // Não renderiza banner flutuante.
    ensureDownloadBanner();
  }

  async function pollDownloadsReady() {
    if (workspaceCache && workspaceCache.local_mode) return;
    try {
      ensureDownloadBanner();
      ensureNavDownloadButton();
      const r = await authFetch(`${API}/api/jobs/downloads-ready`);
      if (!r.ok) return;
      const data = await r.json();
      const downloads = downloadsForCurrentUser(data.downloads || []);
      const ready = downloads.find(
        (d) => d && d.id && !isDownloadDismissed(d.id)
      );
      if (ready) {
        syncDownloadUi(ready.id, ready.service_id, true, { owner: ready.owner });
        return;
      }
      const mem = readRememberedJob(boundServiceId);
      const jid = currentJobId || (mem && mem.jobId);
      if (jid && boundServiceId && isJobServicePage(boundServiceId)) {
        syncDownloadUi(jid, boundServiceId, false, { waiting: true });
      } else {
        hideNavDownloadButton();
      }
    } catch (_) {}
  }

  let queuePollTimer = null;

  const JOB_SESSION_KEY = "opto-active-jobs";
  const JOB_SESSION_LEGACY = "opto-active-job";

  function readJobMap() {
    try {
      const raw = sessionStorage.getItem(JOB_SESSION_KEY);
      if (raw) {
        const map = JSON.parse(raw);
        if (map && typeof map === "object" && !map.jobId) return map;
      }
      const leg = sessionStorage.getItem(JOB_SESSION_LEGACY);
      if (leg) {
        const one = JSON.parse(leg);
        if (one && one.jobId && one.serviceId) {
          const map = { [one.serviceId]: one };
          sessionStorage.setItem(JOB_SESSION_KEY, JSON.stringify(map));
          sessionStorage.removeItem(JOB_SESSION_LEGACY);
          return map;
        }
      }
    } catch (_) {}
    return {};
  }

  function rememberJob(jobId, serviceId) {
    const sid = serviceId || boundServiceId;
    if (!sid) return;
    trackMyJob(jobId);
    try {
      const map = readJobMap();
      map[sid] = { jobId, serviceId: sid, t: Date.now() };
      sessionStorage.setItem(JOB_SESSION_KEY, JSON.stringify(map));
      sessionStorage.removeItem(JOB_SESSION_LEGACY);
    } catch (_) {}
  }

  function forgetJob(serviceId) {
    const sid = serviceId || boundServiceId;
    if (!sid) return;
    try {
      const map = readJobMap();
      delete map[sid];
      sessionStorage.setItem(JOB_SESSION_KEY, JSON.stringify(map));
    } catch (_) {}
  }

  function readRememberedJob(serviceId) {
    const sid = serviceId || boundServiceId;
    if (!sid) return null;
    try {
      const map = readJobMap();
      return map[sid] || null;
    } catch (_) {
      return null;
    }
  }

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
    if (visible) btn.disabled = false;
    else btn.disabled = true;
    if (!visible) btn.textContent = "Cancelar fila";
  }

  function closeStream() {
    if (es) {
      es.close();
      es = null;
    }
    streamJobId = null;
  }

  function attachStream(jobId) {
    if (!jobId || jobId !== currentJobId) return;
    closeStream();
    streamJobId = jobId;
    const streamFor = jobId;
    es = new EventSource(streamUrl(`/api/jobs/${jobId}/logs/stream`));
    es.onmessage = (ev) => {
      if (streamJobId !== streamFor || currentJobId !== streamFor) return;
      try {
        const data = JSON.parse(ev.data);
        if (data.level === "done") {
          closeStream();
          refreshStatus(streamFor);
          return;
        }
        appendLog(data, data.level);
        if ((data.msg || "").includes("— fim —")) {
          closeStream();
          refreshStatus(streamFor);
        }
      } catch (_) {}
    };
    es.onerror = () => {
      if (streamJobId !== streamFor) return;
      closeStream();
      refreshStatus(streamFor);
    };
  }

  function stopQueuePoll() {
    if (queuePollTimer) {
      clearInterval(queuePollTimer);
      queuePollTimer = null;
    }
  }

  function pollQueuePosition(jobId) {
    stopQueuePoll();
    queuePollTimer = setInterval(async () => {
      try {
        const r = await authFetch(`${API}/api/jobs/${jobId}`);
        if (!r.ok) return;
        const job = await r.json();
        if (job.status === "running") {
          stopQueuePoll();
          setLogState("Em andamento");
          const st = el("job-status");
          if (st) st.textContent = STATUS_PT.running;
          if (!es) attachStream(jobId);
          return;
        }
        if (job.status !== "pending") {
          stopQueuePoll();
          refreshStatus(jobId);
          return;
        }
        const pos = (job.queue && job.queue.position) || "?";
        setLogState(`Na fila — posição ${pos}`);
        const st = el("job-status");
        if (st) st.textContent = `Na fila (#${pos})`;
      } catch (_) {}
    }, 3000);
  }

  function watchJob(jobId, opts) {
    const preserveLogs = !!(opts && opts.preserveLogs);
    const initialStatus = opts && opts.initialStatus;
    currentJobId = jobId;
    noticeShownFor = null;
    rememberJob(jobId, boundServiceId);
    setCancelVisible(true);
    const runBtn = el("btn-run");
    if (runBtn) runBtn.disabled = true;
    const box = el("log-console");
    if (box && !preserveLogs) {
      resetLogConsole(box);
    }
    if (!workspaceCache?.local_mode) {
      setJobDownloadButton(jobId, false, { waiting: true });
    }
    if (initialStatus === "pending") {
      setLogState("Na fila…");
      pollQueuePosition(jobId);
    } else {
      setLogState("Em andamento");
      attachStream(jobId);
    }
  }

  async function fetchActiveJob() {
    try {
      const r = await authFetch(`${API}/api/health`);
      if (!r.ok) return null;
      const data = await r.json();
      return data.ativo || null;
    } catch (_) {
      return null;
    }
  }

  /** Após F5: religa no job desta aba (sessionStorage), não em outro processo. */
  async function resumeActiveJob(serviceId) {
    ensureCancelButton();
    let ativo = null;
    const mem = readRememberedJob(serviceId);
    if (mem && mem.jobId) {
      try {
        const r = await authFetch(`${API}/api/jobs/${mem.jobId}`);
        if (r.ok) {
          const job = await r.json();
          if (job.status === "running" || job.status === "pending") {
            if (!serviceId || job.service_id === serviceId) {
              ativo = {
                id: job.id,
                service_id: job.service_id,
                nome: SERVICE_LABELS[job.service_id] || job.service_id,
                cancel_requested: job.cancel_requested,
                status: job.status,
                queue: job.queue,
              };
            }
          } else if (job.status === "completed" && job.has_download) {
            if (!serviceId || job.service_id === serviceId) {
              restoreFinishedJob(job);
              return true;
            }
            forgetJob();
          } else {
            forgetJob();
          }
        }
      } catch (_) {}
    }
    if (!ativo || !ativo.id) {
      setCancelVisible(false);
      return false;
    }

    currentJobId = ativo.id;
    rememberJob(ativo.id, ativo.service_id);
    setCancelVisible(true);
    const runBtn = el("btn-run");
    if (runBtn) runBtn.disabled = true;

    try {
      const r = await authFetch(`${API}/api/jobs/${ativo.id}`);
      if (r.ok) {
        const job = await r.json();
        const box = el("log-console");
        if (box && Array.isArray(job.logs) && job.logs.length) {
          resetLogConsole(box);
          job.logs.forEach((entry) => appendLog(entry, entry.level));
          collapseAllLogModules(box, { exceptLast: true });
        }
        if (job.status === "pending") {
          const pos = (job.queue && job.queue.position) || "?";
          setLogState(`Na fila — posição ${pos}`);
          pollQueuePosition(ativo.id);
        } else if (!es) {
          attachStream(ativo.id);
          setLogState(ativo.cancel_requested ? "Parando…" : "Em andamento");
        }
      }
    } catch (_) {}
    return true;
  }

  function restoreFinishedJob(job) {
    stopQueuePoll();
    setCancelVisible(false);
    currentJobId = job.id;
    const st = el("job-status");
    if (st) st.textContent = STATUS_PT[job.status] || job.status;
    setLogState(STATUS_PT[job.status] || "Finalizado");
    const runBtn = el("btn-run");
    if (runBtn) runBtn.disabled = false;
    if (job.has_download) {
      showJobDownloadButton(job.id, job.service_id);
      showNotice(
        (job.result && job.result.mensagem) ||
          `${downloadLabel(job.service_id, job.owner || currentUsername)} finalizado — clique para baixar.`,
        "ok"
      );
    } else if (!workspaceCache?.local_mode) {
      setJobDownloadButton(job.id, false, { waiting: false });
    }
    pollDownloadsReady().catch(() => {});
  }

  function syncCancelFromHealth(ativo) {
    if (!el("btn-run") && !el("btn-cancel")) return;
    if (!boundServiceId) return;
    if (ativo && ativo.service_id && ativo.service_id !== boundServiceId) return;
    const mem = readRememberedJob(boundServiceId);
    if (!mem || !mem.jobId) return;
    if (ativo && ativo.id && ativo.id !== mem.jobId) return;
    if (!ativo || !ativo.id) {
      if (currentJobId === mem.jobId && !es) {
        refreshStatus(currentJobId).catch(() => {});
      }
      return;
    }
    if (ativo.id !== mem.jobId) return;
    currentJobId = ativo.id;
    setCancelVisible(true);
    const runBtn = el("btn-run");
    if (runBtn) runBtn.disabled = true;
    if (
      ativo.service_id === boundServiceId &&
      !es &&
      !resumedOnce &&
      ativo.status !== "pending"
    ) {
      resumedOnce = true;
      resumeActiveJob(boundServiceId).catch(() => {});
    }
  }

  async function cancelCurrentJob() {
    const btn = ensureCancelButton();
    btn.disabled = true;
    btn.textContent = "Cancelando…";
    try {
      const url = currentJobId
        ? `${API}/api/jobs/${currentJobId}/cancel`
        : `${API}/api/jobs/cancel-active`;
      const r = await authFetch(url, { method: "POST" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(data.detail || "Falha ao cancelar");
      }
      if (data.job_id) {
        currentJobId = data.job_id;
        rememberJob(data.job_id, boundServiceId);
      }
      if (data.estava_rodando === false && !currentJobId) {
        appendLog(
          { msg: data.msg || "Nenhuma fila ativa.", level: "info" },
          "info"
        );
        setCancelVisible(false);
        const runBtn = el("btn-run");
        if (runBtn) runBtn.disabled = false;
        forgetJob();
        return;
      }
      appendLog({ msg: "Cancelamento solicitado…", level: "warn" }, "warn");
      setLogState("Parando…");
      if (currentJobId && !es) attachStream(currentJobId);
    } catch (e) {
      appendLog({ msg: String(e.message || e), level: "error" }, "error");
      btn.disabled = false;
      btn.textContent = "Cancelar fila";
      // Último recurso: cancela o ativo global mesmo sem id local
      if (currentJobId) {
        try {
          const r2 = await authFetch(`${API}/api/jobs/cancel-active`, {
            method: "POST",
          });
          if (r2.ok) {
            appendLog(
              { msg: "Cancelamento solicitado (fila ativa)…", level: "warn" },
              "warn"
            );
            setLogState("Parando…");
          }
        } catch (_) {}
      }
    }
  }

  async function refreshStatus(jobId) {
    try {
      const r = await authFetch(`${API}/api/jobs/${jobId}`);
      const job = await r.json();
      const runBtn = el("btn-run");
      if (runBtn) runBtn.disabled = false;
      const cancelBtn = el("btn-cancel");
      if (cancelBtn) cancelBtn.textContent = "Cancelar fila";

      const dl = el("btn-download");
      if (!workspaceCache?.local_mode) {
        if (job.has_download) {
          syncDownloadUi(jobId, job.service_id, true, { owner: job.owner });
        } else if (job.zip_building) {
          syncDownloadUi(jobId, job.service_id, false, { waiting: true });
        } else if (
          job.status === "running" ||
          job.status === "pending" ||
          job.cancel_requested
        ) {
          syncDownloadUi(jobId, job.service_id, false, { waiting: true });
        } else if (job.status === "completed") {
          syncDownloadUi(jobId, job.service_id, false, { waiting: false });
        } else {
          hideNavDownloadButton();
          if (isJobServicePage(job.service_id)) {
            setJobDownloadButton(jobId, false, { waiting: false, serviceId: job.service_id });
          }
        }
      } else if (dl) {
        dl.hidden = true;
      }

      const label = downloadLabel(
        job.service_id,
        job.owner || currentUsername
      );
      const already = noticeShownFor === jobId;
      const finished = ["completed", "failed", "cancelled"].includes(job.status);
      const st = el("job-status");
      if (st) st.textContent = STATUS_PT[job.status] || job.status;

      if (finished) {
        stopQueuePoll();
        setCancelVisible(false);
        forgetJob();
        if (currentJobId === jobId) currentJobId = null;
      }

      if (job.status === "pending") {
        const pos = (job.queue && job.queue.position) || "?";
        setLogState(`Na fila — posição ${pos}`);
        setCancelVisible(true);
        if (runBtn) runBtn.disabled = true;
        if (!queuePollTimer) pollQueuePosition(jobId);
        return;
      }

      if (job.status === "failed") {
        setLogState("Com problema");
        if (job.error) {
          appendLog({ msg: "ERRO: " + job.error, level: "error" }, "error");
        }
        if (!already) {
          noticeShownFor = jobId;
          showNotice(job.error || `${label} terminou com erro.`, "error");
        }
      } else if (job.status === "cancelled") {
        setLogState("Interrompido");
        if (!already) {
          noticeShownFor = jobId;
          showNotice(
            (job.result && job.result.mensagem) || `${label}: fila cancelada.`,
            "warn"
          );
        }
      } else if (job.status === "completed") {
        setLogState("Finalizado");
        const zipErr =
          job.zip_error || (job.result && job.result._zip_error) || "";
        if (!already) {
          noticeShownFor = jobId;
          if (zipErr && !job.has_download) {
            showNotice(zipErr, "warn");
          } else {
            const fallback = job.has_download
              ? `${label} finalizado — clique para baixar.`
              : `${label} finalizado.`;
            showNotice((job.result && job.result.mensagem) || fallback, "ok");
          }
        }
        if (job.has_download && !workspaceCache?.local_mode) {
          syncDownloadUi(jobId, job.service_id, true, { owner: job.owner });
          pollDownloadsReady().catch(() => {});
        } else if (job.zip_building && !workspaceCache?.local_mode) {
          syncDownloadUi(jobId, job.service_id, false, { waiting: true });
          setTimeout(() => refreshStatus(jobId).catch(() => {}), 1200);
        } else if (
          !workspaceCache?.local_mode &&
          zipRetryFor !== jobId
        ) {
          zipRetryFor = jobId;
          setTimeout(() => refreshStatus(jobId).catch(() => {}), 900);
        }
      } else if (job.status === "running" && job.cancel_requested) {
        setLogState("Parando…");
        setCancelVisible(true);
        if (runBtn) runBtn.disabled = true;
      } else {
        setLogState("Em andamento");
        setCancelVisible(true);
        if (runBtn) runBtn.disabled = true;
      }
    } catch (_) {
      setLogState("Aguardando");
      setCancelVisible(false);
      const runBtn = el("btn-run");
      if (runBtn) runBtn.disabled = false;
    }
  }

  async function startJob(serviceId, config) {
    const btn = el("btn-run");
    if (btn) btn.disabled = true;
    try {
      const r = await authFetch(`${API}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service_id: serviceId, config }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(data.detail || "Falha ao iniciar");
      }
      const q = data.queue || {};
      if (data.status === "pending") {
        const pos = q.position || "?";
        showNotice(
          `Na fila — posição ${pos} (${q.running_slots || 0} rodando, máx. ${q.max_slots || 4})`,
          "info"
        );
      } else {
        showNotice("Processo iniciado.", "ok");
      }
      watchJob(data.job_id, { initialStatus: data.status });
    } catch (e) {
      appendLog({ msg: String(e.message || e), level: "error" }, "error");
      setLogState(currentJobId ? "Em andamento" : "Com problema");
      if (!currentJobId) setCancelVisible(false);
      else setCancelVisible(true);
      showNotice(String(e.message || e), "error");
      if (btn && !currentJobId) btn.disabled = false;
    }
  }

  function bindRun(serviceId, formId, fieldIds, readConfig, skipSensitive) {
    const form = el(formId);
    if (!form) return;
    boundServiceId = serviceId;
    ensureCancelButton();
    ensureDownloadButton();
    ensureLogToolbar();
    loadForm(serviceId, fieldIds);
    loadWorkspace(fieldIds.filter((f) => f.startsWith("pasta")))
      .then(() => initJobDownloadButton())
      .catch(() => initJobDownloadButton());
    resumeActiveJob(serviceId).catch(() => {});
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
    injectFooter,
    pingApi,
    bindRun,
    startJob,
    parallaxHero,
    appendLog,
    showNotice,
    cancelCurrentJob,
    resumeActiveJob,
    renderHomeHubs,
    renderHubTools,
    enableSpotlightCards,
    authFetch,
    authHeaders,
    authToken,
    streamUrl,
    setAuthToken,
    logout,
    guardAuth,
    loadWorkspace,
    uploadFile,
    bindFileUpload,
    downloadJobArtifact,
    applyPendingFolderPick,
    bindFolderPickButtons,
    fetchOutputHints,
    mountFileBrowser,
    pickFolderUrl,
    HUBS,
    TOOLS,
  };
  window.CR2Centro = window.OptoAutomacoes;

  function detectNavKey() {
    const path = (location.pathname || "").toLowerCase();
    if (path === "/" || path.endsWith("/index.html")) return "hub";
    if (path.includes("admin")) return null;
    const page = path.split("/").pop().replace(".html", "");
    const map = {
      extrair: "extrair",
      publicar: "publicar",
      mapa: "mapa",
      arquivos: "arquivos",
      documentos: "documentos",
      categorias: "categorias",
      normas: "normas",
      licitacoes: "licitacoes",
      "tcm-licitacoes": "tcm_licitacoes",
      repasses: "repasses",
      contratos: "contratos",
      publicacao: "publicacao",
      sessao: "sessao",
      "pub-repasses": "pub_repasses",
      "dic-est-ter": "dic_est_ter",
    };
    return map[page] || "hub";
  }

  function autoInjectNav() {
    if (!el("site-nav")) return;
    const key = detectNavKey();
    if (key) injectNav(key);
  }

  function autoInitHubContent() {
    const grid = el("hub-grid");
    if (!grid) return;
    const path = (location.pathname || "").toLowerCase();
    if (path === "/" || path.endsWith("/index.html")) {
      renderHomeHubs();
      return;
    }
    const page = path.split("/").pop().replace(".html", "");
    const hubPages = { extrair: "extrair", publicar: "publicar" };
    if (hubPages[page]) renderHubTools(hubPages[page]);
  }

  function autoPingApi() {
    if (el("api-pill")) pingApi();
  }

  guardAuth().catch(() => {});
  ensureLogoutButton();
  ensureNavDownloadButton();
  autoInjectNav();
  autoInitHubContent();
  autoPingApi();
  applyNavAuth().catch(() => {});
  injectFooter();
  applyPendingFolderPick();
  bindFolderPickButtons();
  loadWorkspace()
    .catch(() => null)
    .then(() => pollDownloadsReady().catch(() => {}));

  // Fundo WebGL (shader) em todas as páginas
  if (!window.OptoShaderBackground) {
    const s = document.createElement("script");
    s.src = "/assets/shader-background.js?v=home70";
    s.async = true;
    document.head.appendChild(s);
  } else if (window.OptoShaderBackground.init) {
    window.OptoShaderBackground.init();
  }
  markReady();
