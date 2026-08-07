export function MinimalFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="relative">
      <div className="bg-[radial-gradient(35%_80%_at_30%_0%,--theme(--color-foreground/.1),transparent)] mx-auto max-w-4xl md:border-x">
        <div className="bg-border absolute inset-x-0 h-px w-full" />
        <div className="flex max-w-4xl flex-col items-center gap-4 p-6 text-center">
          <p className="text-muted-foreground max-w-md font-mono text-sm text-balance">
            Automações para administração pública — baixar, publicar e integrar sistemas.
          </p>
        </div>
        <div className="bg-border absolute inset-x-0 h-px w-full" />
        <div className="flex max-w-4xl flex-col justify-between gap-2 px-4 pt-2 pb-5">
          <p className="text-muted-foreground text-center text-sm font-light">
            © {year} — Direitos reservados a{" "}
            <a
              href="https://github.com/Miguel-Tobias-Vaz"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
            >
              Miguel Vaz
            </a>{" "}
            e{" "}
            <a
              href="https://github.com/CLCarmo"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
            >
              Caio Lucas
            </a>
            .
          </p>
        </div>
      </div>
    </footer>
  );
}
