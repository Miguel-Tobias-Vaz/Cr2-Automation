/** Navegação e rodapé (ES module). */
import { el } from "./core.js";

export function injectFooter() {
  const body = document.body;
  if (!body || body.classList.contains("login-page") || body.classList.contains("admin-page")) {
    return;
  }
  if (el("site-minimal-footer")) return;

  const year = new Date().getFullYear();
  const footer = document.createElement("footer");
  footer.id = "site-minimal-footer";
  footer.className = "minimal-footer minimal-footer--compact";
  footer.innerHTML = `
      <div class="minimal-footer__shell">
        <div class="minimal-footer__grid minimal-footer__grid--compact">
          <div class="minimal-footer__brand">
            <a class="minimal-footer__logo" href="/" aria-label="Opto Automações">
              <img src="/assets/OPTO%20-%20Azul.png" alt="" width="36" height="36" />
            </a>
            <p class="minimal-footer__tagline">
              Automações para administração pública — baixar, publicar e integrar sistemas.
            </p>
          </div>
        </div>
        <p class="minimal-footer__copy">
          © ${year} — Direitos reservados a
          <a href="https://github.com/Miguel-Tobias-Vaz" target="_blank" rel="noopener noreferrer">Miguel Vaz</a>
          e
          <a href="https://github.com/CLCarmo" target="_blank" rel="noopener noreferrer">Caio Lucas</a>.
        </p>
      </div>`;

  const main = document.querySelector("main");
  if (main) main.insertAdjacentElement("afterend", footer);
  else body.appendChild(footer);
}
