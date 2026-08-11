(() => {
  const KEY = "opto-dic-est-ter-v1";
  const JOB_KEY = "opto-dic-job-id";
  const API = "";

  const el = (id) => document.getElementById(id);

  const ids = {
    usuario: "portal-usuario",
    senha: "portal-senha",
    estagiario: "link-estagiario",
    terceirizado: "link-terceirizado",
    divida: "link-divida",
    portal_estagiario: "portal-estagiario",
    portal_terceirizado: "portal-terceirizado",
    portal_divida: "portal-divida",
  };

  const wrapIds = {
    usuario: "wrap-usuario",
    senha: "wrap-senha",
    estagiario: "wrap-estagiario",
    terceirizado: "wrap-terceirizado",
    divida: "wrap-divida",
    portal_estagiario: "wrap-portal-estagiario",
    portal_terceirizado: "wrap-portal-terceirizado",
    portal_divida: "wrap-portal-divida",
  };

  const hintIds = {
    usuario: "hint-usuario",
    senha: "hint-senha",
    estagiario: "hint-estagiario",
    terceirizado: "hint-terceirizado",
    divida: "hint-divida",
    portal_estagiario: "hint-portal-estagiario",
    portal_terceirizado: "hint-portal-terceirizado",
    portal_divida: "hint-portal-divida",
  };

  const statusEl = el("painel-status");
  const errosBox = el("erros-box");
  const errosLista = el("erros-lista");
  const resumoLinhas = el("resumo-linhas");
  const resumoGrid = el("resumo-grid");
  const logConsole = el("log-console");
  const logState = el("log-state");
  const apiPill = el("api-pill");
  const modoTeste = el("modo-teste");
  const lembrarSenha = el("lembrar-senha");

  let publishing = false;
  let es = null;
  let queuePollTimer = null;

  const labelsFluxo = {
    estagiario: "Estagiários",
    terceirizado: "Terceirizados",
    divida: "Dívida ativa",
  };

  function val(id) {
    const n = el(id);
    return n ? (n.value || "").trim() : "";
  }

  function readValues() {
    return {
      usuario: val(ids.usuario),
      senha: val(ids.senha),
      estagiario: val(ids.estagiario),
      terceirizado: val(ids.terceirizado),
      divida: val(ids.divida),
      portal_estagiario: val(ids.portal_estagiario),
      portal_terceirizado: val(ids.portal_terceirizado),
      portal_divida: val(ids.portal_divida),
      teste: !!modoTeste.checked,
      lembrar_senha: !!lembrarSenha.checked,
    };
  }

  function saveLocal(data) {
    const payload = { ...data };
    if (!payload.lembrar_senha) delete payload.senha;
    delete payload.teste;
    localStorage.setItem(KEY, JSON.stringify(payload));
  }

  function fill(id, value) {
    const n = el(id);
    if (n && value != null && value !== "") n.value = value;
  }

  async function loadDefaults() {
    try {
      const d = await api("/api/defaults");
      if (!d) return;
      fill(ids.usuario, d.usuario);
      fill(ids.portal_estagiario, d.portal_estagiario);
      fill(ids.portal_terceirizado, d.portal_terceirizado);
      fill(ids.portal_divida, d.portal_divida);
      fill(ids.estagiario, d.estagiario);
      fill(ids.terceirizado, d.terceirizado);
      fill(ids.divida, d.divida);
      const hintPub = el("hint-modo-publicacao");
      if (hintPub) {
        hintPub.textContent =
          "Igual ao RGF: botão Criar Publicação, uma linha por vez.";
      }
    } catch (_) {
      /* offline */
    }
  }

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      Object.entries(ids).forEach(([key, id]) => {
        if (data[key]) fill(id, data[key]);
      });
      if (data.lembrar_senha) lembrarSenha.checked = true;
    } catch (_) {
      /* ignore */
    }
  }

  function clearFieldState() {
    Object.values(wrapIds).forEach((id) => {
      const w = el(id);
      if (w) w.classList.remove("has-error", "has-ok");
    });
    Object.values(hintIds).forEach((id) => {
      const h = el(id);
      if (h) h.textContent = "";
    });
  }

  function mark(key, kind, hint) {
    const w = el(wrapIds[key]);
    const h = el(hintIds[key]);
    if (w) {
      w.classList.remove("has-error", "has-ok");
      if (kind) w.classList.add(kind);
    }
    if (h) h.textContent = hint || "";
  }

  function setStatus(msg, isError) {
    statusEl.textContent = msg || "";
    statusEl.style.color = isError ? "#f0a090" : "";
  }

  function showErros(items) {
    errosLista.innerHTML = "";
    if (!items || !items.length) {
      errosBox.hidden = true;
      return;
    }
    errosBox.hidden = false;
    items.forEach((it) => {
      const li = document.createElement("li");
      if (it.warn) li.classList.add("warn");
      li.textContent = it.text;
      errosLista.appendChild(li);
    });
  }

  function showResumoLinhas(val) {
    if (!resumoLinhas || !resumoGrid) return;
    resumoGrid.innerHTML = "";
    const fluxos = val.fluxos || {};
    let algum = false;
    Object.entries(fluxos).forEach(([tipo, fluxo]) => {
      if (!fluxo.ativo) return;
      algum = true;
      const card = document.createElement("div");
      card.className = "resumo-card";
      const total = fluxo.total || 0;
      const ok = fluxo.itens_ok || 0;
      const err = Math.max(0, total - ok);
      const seg = fluxo.segundos != null ? fluxo.segundos + "s" : "";
      card.innerHTML =
        "<strong></strong><div class='num'></div><span></span>";
      card.querySelector("strong").textContent = labelsFluxo[tipo] || tipo;
      card.querySelector(".num").textContent = total.toLocaleString("pt-BR");
      card.querySelector("span").textContent =
        ok.toLocaleString("pt-BR") +
        " ok · " +
        err.toLocaleString("pt-BR") +
        " com erro" +
        (seg ? " · " + seg : "");
      resumoGrid.appendChild(card);
    });

    const antigo = resumoLinhas.querySelector(".resumo-total");
    if (antigo) antigo.remove();

    if (!algum) {
      resumoLinhas.hidden = true;
      return;
    }

    const r = val.resumo_linhas || {};
    const tot = document.createElement("div");
    tot.className = "resumo-total";
    tot.textContent =
      "Total: " +
      (r.total || 0).toLocaleString("pt-BR") +
      " linhas · " +
      (r.ok || 0).toLocaleString("pt-BR") +
      " prontas · " +
      (r.com_erro || 0).toLocaleString("pt-BR") +
      " com campo obrigatório em branco";
    resumoLinhas.appendChild(tot);

    const avisoTxt = val.aviso_publicacao || val.aviso_lote;
    if (avisoTxt) {
      const aviso = document.createElement("div");
      aviso.className = "resumo-aviso linha";
      aviso.textContent = avisoTxt;
      resumoLinhas.appendChild(aviso);
    }
    if (val.aviso_pular) {
      const avisoP = document.createElement("div");
      avisoP.className = "resumo-aviso";
      avisoP.textContent = val.aviso_pular;
      resumoLinhas.appendChild(avisoP);
    }
    resumoLinhas.hidden = false;
  }

  function showNaoPublicadas(lista, downloadUrl) {
    const box = el("nao-pub-box");
    const ul = el("nao-pub-lista");
    const btn = el("btn-download-nao-pub");
    if (!box || !ul) return;
    ul.innerHTML = "";
    if (!lista || !lista.length) {
      box.hidden = true;
      if (btn) btn.hidden = true;
      return;
    }
    box.hidden = false;
    if (btn) {
      btn.hidden = !downloadUrl;
      if (downloadUrl) {
        btn.href = downloadUrl;
        btn.setAttribute("download", "");
      }
    }
    lista.slice(0, 100).forEach((item) => {
      const li = document.createElement("li");
      li.textContent =
        "[" +
        (labelsFluxo[item.kind] || item.kind || "?") +
        "] L" +
        (item.linha != null ? item.linha : "?") +
        " — " +
        (item.nome || "") +
        ": " +
        (item.motivo || "");
      ul.appendChild(li);
    });
    if (lista.length > 100) {
      const li = document.createElement("li");
      li.className = "warn";
      li.textContent =
        "… e mais " + (lista.length - 100).toLocaleString("pt-BR") + " linha(s)";
      ul.appendChild(li);
    }
  }

  const seenLogs = new Set();

  function logKey(entry) {
    return (
      (entry.t || "") +
      "|" +
      (entry.level || "") +
      "|" +
      (entry.msg || "")
    );
  }

  function renderDashboard(p) {
    const box = el("dash-job");
    if (!box) return;
    if (!p || (!p.total && !p.chunk_total && p.fase === "parado")) {
      // ainda mostra se houver atividade
      if (!p || p.fase === "parado") {
        box.hidden = true;
        return;
      }
    }
    box.hidden = false;
    const total = p.total || 0;
    const pubN = p.publicadas || 0;
    const errN = p.erros || 0;
    const retryN = p.retries || 0;
    const ca = p.chunk_atual || 0;
    const ct = p.chunk_total || 0;
    el("dash-total").textContent =
      total.toLocaleString("pt-BR") + " linhas";
    el("dash-pub").textContent = "✓ " + pubN.toLocaleString("pt-BR");
    el("dash-err").textContent = "✗ " + errN.toLocaleString("pt-BR");
    el("dash-retry").textContent = "↺ " + retryN.toLocaleString("pt-BR");
    el("dash-chunk").textContent =
      "⏳ " +
      (ct > 0
        ? ca.toLocaleString("pt-BR") + "/" + ct.toLocaleString("pt-BR")
        : pubN.toLocaleString("pt-BR") + "/" + total.toLocaleString("pt-BR"));
    el("dash-fase").textContent = p.fase || "—";
    el("dash-eta").textContent = p.eta_txt || "—";
    let pct = 0;
    if (ct > 0) pct = Math.min(100, Math.round((ca / ct) * 100));
    else if (total > 0)
      pct = Math.min(
        100,
        Math.round((((p.linhas_processadas || pubN) / total) * 100))
      );
    const fill = el("dash-bar-fill");
    if (fill) fill.style.width = pct + "%";
  }

  function appendLog(entry, opts) {
    if (entry && entry.level === "progress") {
      if (entry.progresso) renderDashboard(entry.progresso);
      return;
    }
    const force = opts && opts.force;
    const key = logKey(entry);
    if (!force && seenLogs.has(key)) return;
    seenLogs.add(key);

    const empty = logConsole.querySelector(".log-empty");
    if (empty) empty.remove();
    const line = document.createElement("div");
    line.className = "log-line " + (entry.level || "info");
    line.innerHTML =
      '<span class="t"></span><span class="lv"></span><span class="msg"></span>';
    line.querySelector(".t").textContent = entry.t || "--:--:--";
    line.querySelector(".lv").textContent = entry.level || "info";
    line.querySelector(".msg").textContent = entry.msg || "";
    logConsole.appendChild(line);
    logConsole.scrollTop = logConsole.scrollHeight;
  }

  function clearLog() {
    seenLogs.clear();
    logConsole.innerHTML =
      '<p class="log-empty">Aguardando validação ou publicação…</p>';
  }

  function applyResumoPublicacao(r) {
    if (!r) return;
    const np = r.nao_publicadas || [];
    showNaoPublicadas(
      np,
      r.download_nao_publicadas ||
        (np.length ? "/api/download/nao-publicadas" : null)
    );
  }

  function rememberJobId(id) {
    try {
      if (id) sessionStorage.setItem(JOB_KEY, id);
      else sessionStorage.removeItem(JOB_KEY);
    } catch (_) {}
  }

  function stopQueuePoll() {
    if (queuePollTimer) {
      clearInterval(queuePollTimer);
      queuePollTimer = null;
    }
  }

  function pollQueueStatus(jobId) {
    stopQueuePoll();
    queuePollTimer = setInterval(async () => {
      try {
        const st = await api("/api/status");
        if (st.global_job_id !== jobId && st.job_id !== jobId) return;
        if (st.pending || st.status === "pending") {
          const pos = (st.queue && st.queue.position) || "?";
          setStatus(
            "Na fila — posição " +
              pos +
              " (até 4 rodando ao mesmo tempo no painel)."
          );
          return;
        }
        stopQueuePoll();
        if (st.running) {
          setLogState("running");
          setStatus("Publicação em andamento — acompanhe o log.");
        }
      } catch (_) {}
    }, 3000);
  }

  async function restoreSession() {
    try {
      const st = await api("/api/status");
      apiPill.textContent = "Servidor online";
      apiPill.classList.add("ok");
      apiPill.classList.remove("err");

      const logs = st.logs || [];
      if (logs.length) {
        logs.forEach((entry) => appendLog(entry));
      }
      if (st.progresso) renderDashboard(st.progresso);

      if (st.global_job_id) rememberJobId(st.global_job_id);

      if (st.pending || st.status === "pending") {
        publishing = true;
        el("btn-publicar").disabled = true;
        setLogState("running");
        const pos = (st.queue && st.queue.position) || "?";
        setStatus(
          "Na fila — posição " +
            pos +
            " (até 4 processos simultâneos no painel)."
        );
        ensureEventSource();
        pollQueueStatus(st.global_job_id || st.job_id);
      } else if (st.running) {
        publishing = true;
        el("btn-publicar").disabled = true;
        setLogState("running");
        setStatus(
          "Worker em andamento (pode fechar o navegador). Acompanhe o dashboard."
        );
        ensureEventSource();
      } else if (st.resumo) {
        applyResumoPublicacao(st.resumo);
        const np = (st.resumo.nao_publicadas || []).length;
        if (np) {
          setStatus(
            "Última publicação: " +
              np.toLocaleString("pt-BR") +
              " linha(s) não publicada(s). Baixe o .xlsx se precisar."
          );
          setLogState("done");
        } else if (logs.length) {
          setLogState("done");
        }
        rememberJobId(null);
      }
      return true;
    } catch (_) {
      apiPill.textContent = "Servidor offline";
      apiPill.classList.add("err");
      apiPill.classList.remove("ok");
      return false;
    }
  }

  function setLogState(state) {
    logState.classList.remove("running", "done");
    if (state === "running") {
      logState.textContent = "publicando";
      logState.classList.add("running");
    } else if (state === "done") {
      logState.textContent = "concluído";
      logState.classList.add("done");
    } else {
      logState.textContent = "parado";
    }
  }

  function isDriveUrl(v) {
    return (
      /docs\.google\.com\/spreadsheets/i.test(v) ||
      /drive\.google\.com/i.test(v)
    );
  }

  function isHttpUrl(v) {
    return /^https?:\/\//i.test(v);
  }

  function clientValidate(data) {
    const itens = [];
    clearFieldState();

    if (!data.usuario) {
      mark("usuario", "has-error", "Obrigatório");
      itens.push({ text: "Informe o usuário / e-mail do portal." });
    } else {
      mark("usuario", "has-ok", "");
    }

    if (!data.senha) {
      mark("senha", "has-error", "Obrigatória");
      itens.push({ text: "Informe a senha do portal." });
    } else {
      mark("senha", "has-ok", "");
    }

    const fluxos = ["estagiario", "terceirizado", "divida"];
    const ativos = fluxos.filter((k) => data[k]);
    if (!ativos.length) {
      fluxos.forEach((k) => mark(k, "has-error", "Preencha pelo menos um"));
      itens.push({
        text: "Informe ao menos uma planilha (estagiários, terceirizados ou dívida).",
      });
      return itens;
    }

    fluxos.forEach((k) => {
      const planilha = data[k];
      const portalKey = "portal_" + k;
      const portal = data[portalKey];

      if (!planilha) {
        mark(k, "", "Fluxo desligado");
        mark(portalKey, "", "—");
        return;
      }

      if (!isDriveUrl(planilha)) {
        mark(k, "has-error", "Use Sheets ou Drive");
        itens.push({
          text: labelsFluxo[k] + ": link da planilha inválido.",
        });
      } else {
        mark(k, "has-ok", "");
      }

      if (!portal) {
        mark(portalKey, "has-error", "Obrigatória com planilha");
        itens.push({
          text:
            labelsFluxo[k] +
            ": informe a URL do local de publicação no portal.",
        });
      } else if (!isHttpUrl(portal)) {
        mark(portalKey, "has-error", "URL inválida");
        itens.push({
          text: labelsFluxo[k] + ": URL do portal inválida.",
        });
      } else {
        mark(portalKey, "has-ok", "");
      }
    });

    return itens;
  }

  function renderValidacao(val) {
    const itens = [];
    (val.erros_gerais || []).forEach((msg) => itens.push({ text: msg }));

    Object.entries(val.fluxos || {}).forEach(([tipo, fluxo]) => {
      if (!fluxo.ativo) {
        mark(tipo, "", "Fluxo desligado");
        return;
      }
      const bloqueantes = (fluxo.erros || []).filter((e) => e.level !== "warn");
      const avisos = (fluxo.erros || []).filter((e) => e.level === "warn");
      const total = fluxo.total || 0;
      const ok = fluxo.itens_ok || 0;

      if (bloqueantes.length) {
        mark(
          tipo,
          "has-error",
          "Cabeçalho inválido"
        );
        bloqueantes.forEach((e) => {
          itens.push({
            text:
              labelsFluxo[tipo] +
              " · linha " +
              (e.linha || "?") +
              ": " +
              e.msg,
          });
        });
      } else {
        const pulaveis =
          (fluxo.linhas_a_pular || 0) + (fluxo.erros_omitidos || 0);
        mark(
          tipo,
          "has-ok",
          total.toLocaleString("pt-BR") +
            " linhas · " +
            ok.toLocaleString("pt-BR") +
            " prontas" +
            (pulaveis
              ? " · " + pulaveis.toLocaleString("pt-BR") + " a pular"
              : "")
        );
      }
      avisos.forEach((e) => {
        itens.push({
          warn: true,
          text:
            labelsFluxo[tipo] +
            " · linha " +
            (e.linha || "?") +
            " (será pulada): " +
            e.msg,
        });
      });
      if (fluxo.erros_omitidos) {
        itens.push({
          warn: true,
          text:
            labelsFluxo[tipo] +
            ": +" +
            Number(fluxo.erros_omitidos).toLocaleString("pt-BR") +
            " linhas a pular não listadas (limite na tela)",
        });
      }
    });

    showResumoLinhas(val);
    showErros(itens);
    return itens;
  }

  function streamUrl(path) {
    if (window.OptoAutomacoes && OptoAutomacoes.streamUrl) {
      return OptoAutomacoes.streamUrl(path);
    }
    return API + path;
  }

  async function api(path, opts) {
    const headers = { "Content-Type": "application/json" };
    if (window.OptoAutomacoes && OptoAutomacoes.authHeaders) {
      Object.assign(headers, OptoAutomacoes.authHeaders());
    }
    const res = await fetch(API + path, {
      headers,
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      const msg =
        data.erro ||
        (typeof detail === "string" ? detail : detail && detail.erro) ||
        "Falha no servidor (" + res.status + ")";
      const err = new Error(msg);
      err.status = res.status;
      err.data = typeof detail === "object" && detail ? detail : data;
      throw err;
    }
    return data;
  }

  async function pingApi() {
    try {
      await api("/api/status");
      apiPill.textContent = "Servidor online";
      apiPill.classList.add("ok");
      apiPill.classList.remove("err");
      return true;
    } catch (_) {
      apiPill.textContent = "Servidor offline";
      apiPill.classList.add("err");
      apiPill.classList.remove("ok");
      return false;
    }
  }

  function ensureEventSource() {
    if (es) return;
    try {
      es = new EventSource(streamUrl("/api/logs"));
      es.onmessage = (ev) => {
        try {
          const entry = JSON.parse(ev.data);
          appendLog(entry);
          if (entry.progresso) renderDashboard(entry.progresso);
          if ((entry.msg || "").includes("— fim —")) {
            publishing = false;
            setLogState("done");
            el("btn-publicar").disabled = false;
            api("/api/status")
              .then((st) => {
                if (st.progresso) renderDashboard(st.progresso);
                applyResumoPublicacao(st.resumo || {});
                const np = ((st.resumo || {}).nao_publicadas || []).length;
                const msg = np
                  ? "Publicação encerrada — " +
                    np.toLocaleString("pt-BR") +
                    " linha(s) não publicada(s). Baixe o .xlsx para corrigir."
                  : "Publicação Dic/Est/Ter concluída com sucesso.";
                setStatus(
                  np
                    ? "Publicação encerrada — " +
                        np.toLocaleString("pt-BR") +
                        " linha(s) não publicada(s). Baixe o .xlsx para corrigir."
                    : "Publicação encerrada. Todas as linhas válidas foram processadas."
                );
                if (window.CR2Centro && window.CR2Centro.showNotice) {
                  window.CR2Centro.showNotice(msg, np ? "error" : "ok");
                }
              })
              .catch(() => {
                setStatus("Publicação encerrada. Veja o log abaixo.");
                if (window.CR2Centro && window.CR2Centro.showNotice) {
                  window.CR2Centro.showNotice("Publicação Dic/Est/Ter encerrada.", "ok");
                }
              });
          }
        } catch (_) {
          /* ignore */
        }
      };
    } catch (_) {
      /* ignore */
    }
  }

  async function onValidar() {
    const data = readValues();
    saveLocal(data);

    const locais = clientValidate(data);
    if (locais.length) {
      showErros(locais);
      setStatus("Preencha os campos obrigatórios do controle.", true);
      return false;
    }

    if (!(await pingApi())) {
      showErros([
        { text: "Servidor offline. Reinicie o painel no servidor." },
      ]);
      setStatus("Servidor offline.", true);
      return false;
    }

    setStatus("Validando planilhas…");
    ensureEventSource();
    appendLog({
      t: new Date().toLocaleTimeString("pt-BR", { hour12: false }),
      level: "info",
      msg: "Validação solicitada",
    });

    try {
      const val = await api("/api/validar", {
        method: "POST",
        body: JSON.stringify(data),
      });
      const itens = renderValidacao(val);
      if (val.ok) {
        const r = val.resumo_linhas || {};
        let msg =
          "Validação OK — " +
          (r.total || 0).toLocaleString("pt-BR") +
          " linhas (" +
          (r.ok || 0).toLocaleString("pt-BR") +
          " prontas).";
        const avisoTxt = val.aviso_publicacao || val.aviso_lote;
        if (avisoTxt) msg += " " + avisoTxt;
        setStatus(msg);
        appendLog({
          t: new Date().toLocaleTimeString("pt-BR", { hour12: false }),
          level: "ok",
          msg:
            "Validação OK — " +
            (r.total || 0).toLocaleString("pt-BR") +
            " linhas" +
            (avisoTxt ? " · " + avisoTxt : ""),
        });
        return true;
      }
      setStatus("Validação encontrou problemas.", true);
      appendLog({
        t: new Date().toLocaleTimeString("pt-BR", { hour12: false }),
        level: "error",
        msg: "Validação falhou (" + itens.length + ")",
      });
      return false;
    } catch (e) {
      setStatus(e.message, true);
      showErros([{ text: e.message }]);
      return false;
    }
  }

  async function onPublicar() {
    if (publishing) return;
    const data = readValues();
    saveLocal(data);

    const locais = clientValidate(data);
    if (locais.length) {
      showErros(locais);
      setStatus("Corrija o painel antes de publicar.", true);
      el("painel").scrollIntoView({ behavior: "smooth" });
      return;
    }

    if (!(await pingApi())) {
      showErros([
        { text: "Servidor offline. Reinicie o painel no servidor." },
      ]);
      setStatus("Servidor offline.", true);
      return;
    }

    ensureEventSource();
    publishing = true;
    el("btn-publicar").disabled = true;
    setLogState("running");
    setStatus("Publicação iniciada — acompanhe o log.");
    el("log").scrollIntoView({ behavior: "smooth" });

    try {
      const resp = await api("/api/publicar", {
        method: "POST",
        body: JSON.stringify(data),
      });
      const jobId = resp.job_id || resp.global_job_id;
      if (jobId) rememberJobId(jobId);
      if (resp.status === "pending") {
        const q = resp.queue || {};
        setStatus(
          "Na fila — posição " +
            (q.position || "?") +
            " (" +
            (q.running_slots ?? 0) +
            "/" +
            (q.max_slots || 4) +
            " rodando)."
        );
        pollQueueStatus(jobId);
      } else {
        setStatus("Publicação iniciada — acompanhe o log.");
      }
    } catch (e) {
      publishing = false;
      el("btn-publicar").disabled = false;
      setLogState("parado");
      if (e.status === 503) {
        setStatus("Fila cheia — aguarde algum processo terminar.", true);
        showErros([{ text: e.message }]);
      } else if (e.data && e.data.validacao) {
        renderValidacao(e.data.validacao);
        setStatus("Publicação bloqueada pela validação.", true);
      } else {
        setStatus(e.message, true);
        showErros([{ text: e.message }]);
      }
      appendLog({
        t: new Date().toLocaleTimeString("pt-BR", { hour12: false }),
        level: "error",
        msg: e.message,
      });
    }
  }

  async function onCancelarLiberar() {
    if (!(await pingApi())) {
      setStatus("Servidor offline. Reinicie o painel no servidor.", true);
      return;
    }
    const btn = el("btn-cancelar");
    const btnLog = el("btn-cancelar-log");
    if (btn) btn.disabled = true;
    if (btnLog) btnLog.disabled = true;
    try {
      let r;
      try {
        r = await api("/api/cancelar", {
          method: "POST",
          body: JSON.stringify({}),
        });
      } catch (e1) {
        r = await api("/api/cancelar");
      }
      setLogState(r.estava_rodando ? "cancelando" : "parado");
      setStatus(r.msg || "Cancelamento solicitado.");
      appendLog({
        t: new Date().toLocaleTimeString("pt-BR", { hour12: false }),
        level: "warn",
        msg: r.msg || "Cancelar fila",
      });
      if (!r.estava_rodando) {
        publishing = false;
        el("btn-publicar").disabled = false;
      }
    } catch (e) {
      setStatus(
        "Cancelar falhou (" +
          e.message +
          "). Reinicie o painel no servidor",
        true
      );
      showErros([
        {
          text:
            "O servidor parou de responder. Reinicie o painel no servidor.",
        },
      ]);
    } finally {
      if (btn) btn.disabled = false;
      if (btnLog) btnLog.disabled = false;
    }
  }

  el("btn-validar").addEventListener("click", () => onValidar());
  el("btn-publicar").addEventListener("click", () => onPublicar());
  el("btn-cancelar").addEventListener("click", () => onCancelarLiberar());
  const btnCancelarLog = el("btn-cancelar-log");
  if (btnCancelarLog) {
    btnCancelarLog.addEventListener("click", () => onCancelarLiberar());
  }
  el("btn-limpar").addEventListener("click", () => {
    Object.values(ids).forEach((id) => {
      const n = el(id);
      if (n) n.value = "";
    });
    localStorage.removeItem(KEY);
    lembrarSenha.checked = false;
    clearFieldState();
    showErros([]);
    showNaoPublicadas([]);
    setStatus("Controle limpo.");
  });
  el("btn-limpar-log").addEventListener("click", clearLog);

  Object.values(ids).forEach((id) => {
    const n = el(id);
    if (!n) return;
    n.addEventListener("input", () => {
      clearFieldState();
      setStatus("");
    });
  });

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-in");
          io.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.18, rootMargin: "0px 0px -8% 0px" }
  );
  document.querySelectorAll("[data-reveal]").forEach((n) => io.observe(n));

  const docs = document.querySelectorAll(".hero-doc");
  window.addEventListener(
    "pointermove",
    (e) => {
      const x = (e.clientX / window.innerWidth - 0.5) * 12;
      const y = (e.clientY / window.innerHeight - 0.5) * 10;
      docs.forEach((doc, i) => {
        doc.style.translate = `${x * (i + 1) * 0.35}px ${y * (i + 1) * 0.35}px`;
      });
    },
    { passive: true }
  );

  function boot() {
    clearLog();
    load();
    loadDefaults().then(() => load());
    restoreSession().then(() => {
      ensureEventSource();
    });
    setInterval(pingApi, 8000);
  }
  if (window.OptoAutomacoes) boot();
  else document.addEventListener("opto-ready", boot);
})();
