/** Upload de arquivos para a VPS (ES module). */
import { API, el } from "./core.js";
import { authFetch } from "./auth.js";

let _notify = (msg, kind) => {
  if (kind === "error") console.error(msg);
};

export function setUploadNotifier(fn) {
  if (typeof fn === "function") _notify = fn;
}

export async function uploadFile(file, { extract = false } = {}) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("extract", extract ? "true" : "false");
  const r = await authFetch(`${API}/api/uploads`, { method: "POST", body: fd });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Falha no upload");
  return data;
}

export function applySuggestedPublicacao(meta) {
  const pub = meta && meta.suggested_publicacao;
  if (!pub) return;
  for (const [key, path] of Object.entries(pub)) {
    const node = el(key);
    if (node && path) node.value = path;
  }
}

export function bindFileUpload(opts) {
  const zone = el(opts.zoneId);
  const input = el(opts.inputId);
  if (!zone || !input) return;
  const statusEl = opts.statusId ? el(opts.statusId) : null;
  const pick = zone.querySelector("[data-upload-pick]");
  const setStatus = (msg, ok) => {
    if (!statusEl) return;
    statusEl.hidden = !msg;
    statusEl.textContent = msg || "";
    statusEl.classList.toggle("upload-status--ok", !!ok);
    statusEl.classList.toggle("upload-status--err", ok === false);
  };

  const handle = async (file) => {
    if (!file) return;
    setStatus("Enviando…", null);
    zone.classList.add("is-uploading");
    try {
      const ext = (file.name.split(".").pop() || "").toLowerCase();
      const doExtract = opts.extractZip && ext === "zip";
      const meta = await uploadFile(file, { extract: doExtract });
      const target = opts.targetFieldId ? el(opts.targetFieldId) : null;
      if (target) {
        if (doExtract && meta.suggested_pasta_base) {
          target.value = meta.suggested_pasta_base;
        } else if (meta.path) {
          target.value = meta.path;
        }
      }
      if (typeof opts.onDone === "function") opts.onDone(meta);
      applySuggestedPublicacao(meta);
      const msg = doExtract
        ? `ZIP extraído (${meta.extracted_files || "?"} arquivos)`
        : `Arquivo recebido: ${meta.filename}`;
      setStatus(msg, true);
      _notify(msg, "ok");
    } catch (e) {
      setStatus(String(e.message || e), false);
      _notify(String(e.message || e), "error");
    } finally {
      zone.classList.remove("is-uploading");
      input.value = "";
    }
  };

  if (opts.accept) input.accept = opts.accept;
  if (pick) pick.addEventListener("click", () => input.click());
  zone.addEventListener("click", (ev) => {
    if (ev.target.closest("[data-upload-pick]") || ev.target === input) return;
    if (!ev.target.closest("button") && !ev.target.closest("a")) input.click();
  });
  input.addEventListener("change", () => handle(input.files && input.files[0]));
  zone.addEventListener("dragover", (ev) => {
    ev.preventDefault();
    zone.classList.add("is-dragover");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("is-dragover"));
  zone.addEventListener("drop", (ev) => {
    ev.preventDefault();
    zone.classList.remove("is-dragover");
    const f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
    handle(f);
  });
}
