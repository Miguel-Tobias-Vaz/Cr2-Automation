/** Núcleo compartilhado do front (ES module). */
export const API = "";

export function el(id) {
  return document.getElementById(id);
}

const _readyCallbacks = [];

export function whenReady(fn) {
  if (window.OptoAutomacoes) {
    fn();
    return;
  }
  _readyCallbacks.push(fn);
}

export function markReady() {
  for (const fn of _readyCallbacks.splice(0)) {
    try {
      fn();
    } catch (_) {}
  }
  window.dispatchEvent(new CustomEvent("opto-ready"));
}

export function formatBytes(n) {
  const num = Number(n);
  if (!Number.isFinite(num) || num < 0) return "—";
  if (num < 1024) return `${num} B`;
  if (num < 1024 * 1024) return `${(num / 1024).toFixed(1)} KB`;
  return `${(num / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(ms) {
  try {
    return new Date(ms).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (_) {
    return "—";
  }
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
