#!/usr/bin/env python3
"""
TCM-PA – Painel de Download de Licitações

Interface gráfica: cole o link do mural, escolha os anos e clique em Iniciar.
Funciona para qualquer município/órgão do TCM-PA.

Requer o arquivo tcmpa_licitacoes.py na MESMA PASTA.

Executar:  python painel_tcm.py
"""

import os, sys, re, threading, queue, importlib.util, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

APP_TITULO = "TCM-PA · Download de Licitações"
MOTOR      = "tcmpa_licitacoes.py"   # script principal (mesmo diretório)

# ═══════════════════════════════════════════════════════════════════════════════
#  CARGA DO MOTOR
# ═══════════════════════════════════════════════════════════════════════════════

def carregar_motor():
    """Importa tcmpa_licitacoes.py sem executar o main()."""
    base = os.path.dirname(os.path.abspath(__file__))
    caminho = os.path.join(base, MOTOR)
    if not os.path.exists(caminho):
        raise FileNotFoundError(
            f"'{MOTOR}' não encontrado em:\n{base}\n\n"
            "Coloque os dois arquivos na mesma pasta."
        )
    src = open(caminho, encoding="utf-8").read()
    src = src.replace('if __name__ == "__main__":\n    main()', "pass")
    mod = {"__name__": "motor_tcm"}
    exec(compile(src, caminho, "exec"), mod)
    return mod


# ═══════════════════════════════════════════════════════════════════════════════
#  REDIRECIONAMENTO DO CONSOLE PARA O PAINEL
# ═══════════════════════════════════════════════════════════════════════════════

class SaidaParaFila:
    """Captura print() do motor e envia para a fila da interface."""
    def __init__(self, fila):
        self.fila = fila
        self.buf  = ""

    def write(self, texto):
        self.buf += texto
        while "\n" in self.buf:
            linha, self.buf = self.buf.split("\n", 1)
            self.fila.put(("log", linha))

    def flush(self):
        if self.buf:
            self.fila.put(("log", self.buf))
            self.buf = ""


# ═══════════════════════════════════════════════════════════════════════════════
#  PAINEL
# ═══════════════════════════════════════════════════════════════════════════════

class Painel(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(APP_TITULO)
        self.geometry("880x720")
        self.minsize(760, 600)

        self.fila       = queue.Queue()
        self.rodando    = False
        self.cancelar   = threading.Event()
        self.motor      = None

        self._montar()
        self.after(100, self._drenar_fila)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _montar(self):
        pad = {"padx": 12, "pady": 6}

        cab = tk.Frame(self, bg="#1F4E79")
        cab.pack(fill="x")
        tk.Label(cab, text="Download de Licitações · TCM-PA",
                 bg="#1F4E79", fg="white",
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(cab, text="Documentos, contratos e planilha — para qualquer município ou órgão",
                 bg="#1F4E79", fg="#CFE2F3",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(0, 12))

        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True, padx=14, pady=10)

        # ── Link ──────────────────────────────────────────────────────────────
        gl = ttk.LabelFrame(corpo, text=" 1. Link do mural ")
        gl.pack(fill="x", pady=(0, 10))
        ttk.Label(gl, text="Abra o mural do TCM, aplique os filtros da entidade e cole a URL aqui:",
                  foreground="#555").pack(anchor="w", **pad)
        self.txt_link = tk.Text(gl, height=4, wrap="word",
                                font=("Consolas", 8), relief="solid", bd=1)
        self.txt_link.pack(fill="x", padx=12, pady=(0, 4))
        lb = ttk.Frame(gl); lb.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(lb, text="Colar",  command=self._colar).pack(side="left")
        ttk.Button(lb, text="Limpar", command=lambda: self.txt_link.delete("1.0","end")).pack(side="left", padx=6)
        self.lbl_link = ttk.Label(lb, text="", foreground="#1F4E79")
        self.lbl_link.pack(side="left", padx=12)
        ttk.Button(lb, text="Verificar link", command=self._verificar).pack(side="right")

        # ── Anos ──────────────────────────────────────────────────────────────
        ga = ttk.LabelFrame(corpo, text=" 2. Período ")
        ga.pack(fill="x", pady=(0, 10))
        fa = ttk.Frame(ga); fa.pack(fill="x", **pad)

        self.modo_ano = tk.StringVar(value="faixa")
        ttk.Radiobutton(fa, text="Todos os anos", value="todos",
                        variable=self.modo_ano, command=self._alt_ano).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(fa, text="Ano específico", value="unico",
                        variable=self.modo_ano, command=self._alt_ano).grid(row=0, column=1, sticky="w", padx=18)
        ttk.Radiobutton(fa, text="Faixa de anos", value="faixa",
                        variable=self.modo_ano, command=self._alt_ano).grid(row=0, column=2, sticky="w")

        fb = ttk.Frame(ga); fb.pack(fill="x", padx=12, pady=(4, 10))
        ano_atual = datetime.now().year
        self.sp_de  = ttk.Spinbox(fb, from_=2000, to=ano_atual + 1, width=8)
        self.sp_ate = ttk.Spinbox(fb, from_=2000, to=ano_atual + 1, width=8)
        self.sp_de.set(2023); self.sp_ate.set(ano_atual)
        self.lbl_de  = ttk.Label(fb, text="De:");  self.lbl_de.grid(row=0, column=0)
        self.sp_de.grid(row=0, column=1, padx=(4, 16))
        self.lbl_ate = ttk.Label(fb, text="Até:"); self.lbl_ate.grid(row=0, column=2)
        self.sp_ate.grid(row=0, column=3, padx=4)
        self.lbl_dica = ttk.Label(fb, text="", foreground="#777")
        self.lbl_dica.grid(row=0, column=4, padx=16)

        # ── Opções ────────────────────────────────────────────────────────────
        go = ttk.LabelFrame(corpo, text=" 3. Opções ")
        go.pack(fill="x", pady=(0, 10))

        f1 = ttk.Frame(go); f1.pack(fill="x", **pad)
        ttk.Label(f1, text="Nome da pasta:").grid(row=0, column=0, sticky="w")
        self.ent_entidade = ttk.Entry(f1, width=34)
        self.ent_entidade.grid(row=0, column=1, padx=8)
        ttk.Label(f1, text="(vazio = detecta sozinho, ex.: PM Cametá)",
                  foreground="#777").grid(row=0, column=2, sticky="w")

        f2 = ttk.Frame(go); f2.pack(fill="x", padx=12, pady=4)
        ttk.Label(f2, text="Salvar em:").grid(row=0, column=0, sticky="w")
        self.ent_pasta = ttk.Entry(f2, width=52)
        self.ent_pasta.insert(0, r"C:\Downloads" if os.name == "nt"
                              else os.path.expanduser("~/Downloads"))
        self.ent_pasta.grid(row=0, column=1, padx=8)
        ttk.Button(f2, text="Procurar...", command=self._escolher_pasta).grid(row=0, column=2)

        f3 = ttk.Frame(go); f3.pack(fill="x", padx=12, pady=(4, 10))
        self.var_ocr    = tk.BooleanVar(value=True)
        self.var_so_pl  = tk.BooleanVar(value=False)
        ttk.Checkbutton(f3, text="Ler PDFs com OCR para achar o nº real da licitação",
                        variable=self.var_ocr).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(f3, text="Somente planilha (não baixar arquivos)",
                        variable=self.var_so_pl).grid(row=1, column=0, sticky="w", pady=(2,0))

        # ── Ações ─────────────────────────────────────────────────────────────
        fac = ttk.Frame(corpo); fac.pack(fill="x", pady=(0, 8))
        self.btn_iniciar = tk.Button(fac, text="▶  Iniciar", command=self._iniciar,
                                     bg="#1F4E79", fg="white", font=("Segoe UI", 10, "bold"),
                                     relief="flat", padx=26, pady=8, cursor="hand2")
        self.btn_iniciar.pack(side="left")
        self.btn_parar = tk.Button(fac, text="■  Parar", command=self._parar,
                                   bg="#C00000", fg="white", font=("Segoe UI", 10, "bold"),
                                   relief="flat", padx=20, pady=8, state="disabled")
        self.btn_parar.pack(side="left", padx=8)
        ttk.Button(fac, text="Abrir pasta", command=self._abrir_pasta).pack(side="left", padx=4)
        ttk.Button(fac, text="Limpar log", command=self._limpar_log).pack(side="right")

        self.barra = ttk.Progressbar(corpo, mode="determinate")
        self.barra.pack(fill="x", pady=(0, 6))

        # ── Log ───────────────────────────────────────────────────────────────
        gr = ttk.LabelFrame(corpo, text=" Andamento ")
        gr.pack(fill="both", expand=True)
        wrap = ttk.Frame(gr); wrap.pack(fill="both", expand=True, padx=10, pady=8)
        self.log = tk.Text(wrap, height=14, wrap="word", bg="#1E1E1E", fg="#D4D4D4",
                           font=("Consolas", 9), relief="flat", state="disabled")
        sb = ttk.Scrollbar(wrap, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        for tag, cor in [("ok", "#4EC9B0"), ("erro", "#F48771"),
                         ("aviso", "#DCDCAA"), ("info", "#569CD6")]:
            self.log.tag_configure(tag, foreground=cor)

        self.status = ttk.Label(self, text="Pronto.", relief="sunken", anchor="w")
        self.status.pack(fill="x", side="bottom")

        self._alt_ano()
        self._escrever("Cole o link do mural e clique em Iniciar.", "info")

    # ── Ações da interface ────────────────────────────────────────────────────

    def _colar(self):
        try:
            self.txt_link.delete("1.0", "end")
            self.txt_link.insert("1.0", self.clipboard_get())
            self._verificar()
        except tk.TclError:
            messagebox.showwarning(APP_TITULO, "Não há nada copiado.")

    def _escolher_pasta(self):
        d = filedialog.askdirectory(title="Onde salvar")
        if d:
            self.ent_pasta.delete(0, "end")
            self.ent_pasta.insert(0, d)

    def _alt_ano(self):
        modo = self.modo_ano.get()
        if modo == "todos":
            self.sp_de.state(["disabled"]); self.sp_ate.state(["disabled"])
            self.lbl_dica.config(text="Atenção: pode ser um volume grande.")
        elif modo == "unico":
            self.sp_de.state(["!disabled"]); self.sp_ate.state(["disabled"])
            self.lbl_de.config(text="Ano:")
            self.lbl_dica.config(text="")
        else:
            self.sp_de.state(["!disabled"]); self.sp_ate.state(["!disabled"])
            self.lbl_de.config(text="De:")
            self.lbl_dica.config(text="")

    def _verificar(self):
        link = self.txt_link.get("1.0", "end").strip()
        if not link:
            self.lbl_link.config(text="")
            return False
        mun = re.search(r"ID_MUNICIPIO%5D=(\d+)|ID_MUNICIPIO\]=(\d+)", link)
        org = re.search(r"ORGAO_ID%5D=(\d+)|ORGAO_ID\]=(\d+)", link)
        if not mun:
            self.lbl_link.config(text="✗ Link sem filtro de município", foreground="#C00000")
            return False
        m = mun.group(1) or mun.group(2)
        o = (org.group(1) or org.group(2)) if org else ""
        self.lbl_link.config(text=f"✓ Município {m}" + (f" · Órgão {o}" if o else " · todos os órgãos"),
                             foreground="#107C10")
        return True

    def _limpar_log(self):
        self.log.configure(state="normal"); self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _abrir_pasta(self):
        p = self.ent_pasta.get().strip()
        if not os.path.isdir(p):
            messagebox.showwarning(APP_TITULO, "Pasta ainda não existe.")
            return
        if os.name == "nt":       os.startfile(p)
        elif sys.platform == "darwin": os.system(f'open "{p}"')
        else:                     os.system(f'xdg-open "{p}"')

    # ── Log ───────────────────────────────────────────────────────────────────

    def _escrever(self, texto, tag=None):
        if tag is None:
            t = texto
            if   "[✓]" in t or "[↓]" in t: tag = "ok"
            elif "[!]" in t or "Erro" in t: tag = "erro"
            elif "[~]" in t:                tag = "aviso"
            elif "[i]" in t or "[*]" in t:  tag = "info"
        self.log.configure(state="normal")
        self.log.insert("end", texto + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drenar_fila(self):
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if   tipo == "log":      self._escrever(dado)
                elif tipo == "status":   self.status.config(text=dado)
                elif tipo == "progresso":
                    atual, total = dado
                    self.barra["maximum"] = total
                    self.barra["value"]   = atual
                elif tipo == "fim":      self._finalizar(dado)
        except queue.Empty:
            pass
        self.after(100, self._drenar_fila)

    # ── Execução ──────────────────────────────────────────────────────────────

    def _iniciar(self):
        if self.rodando:
            return
        if not self._verificar():
            messagebox.showerror(APP_TITULO,
                "Cole um link válido do mural do TCM-PA.\n\n"
                "O link precisa conter o filtro de município "
                "(LINCEMVWLICITACOESSearch[ID_MUNICIPIO]).")
            return

        pasta = self.ent_pasta.get().strip()
        if not pasta:
            messagebox.showerror(APP_TITULO, "Escolha a pasta de destino.")
            return

        modo = self.modo_ano.get()
        try:
            if modo == "todos":
                ano_min = ano_max = None
            elif modo == "unico":
                ano_min = ano_max = int(self.sp_de.get())
            else:
                ano_min, ano_max = int(self.sp_de.get()), int(self.sp_ate.get())
                if ano_min > ano_max:
                    ano_min, ano_max = ano_max, ano_min
        except ValueError:
            messagebox.showerror(APP_TITULO, "Ano inválido.")
            return

        if modo == "todos" and not self.var_so_pl.get():
            if not messagebox.askyesno(APP_TITULO,
                "Baixar TODOS os anos pode gerar muitos arquivos "
                "e levar bastante tempo.\n\nDeseja continuar?"):
                return

        cfg = {
            "link":      self.txt_link.get("1.0", "end").strip(),
            "pasta":     pasta,
            "entidade":  self.ent_entidade.get().strip(),
            "ano_min":   ano_min,
            "ano_max":   ano_max,
            "ocr":       self.var_ocr.get(),
            "so_planilha": self.var_so_pl.get(),
        }

        self.rodando = True
        self.cancelar.clear()
        self.btn_iniciar.config(state="disabled")
        self.btn_parar.config(state="normal")
        self.barra["value"] = 0
        self._limpar_log()
        self.status.config(text="Executando...")

        threading.Thread(target=self._executar, args=(cfg,), daemon=True).start()

    def _parar(self):
        if messagebox.askyesno(APP_TITULO, "Interromper o processo?"):
            self.cancelar.set()
            self.fila.put(("log", "\n[!] Parando após a licitação atual..."))
            self.btn_parar.config(state="disabled")

    def _executar(self, cfg):
        original = sys.stdout
        try:
            sys.stdout = SaidaParaFila(self.fila)

            if self.motor is None:
                self.motor = carregar_motor()
            M = self.motor

            # Aplica a configuração do painel no motor
            M["LINK_MURAL"]    = self._normalizar_link(cfg["link"])
            M["PASTA_SAIDA"]   = cfg["pasta"]
            M["NOME_ENTIDADE"] = cfg["entidade"]
            M["ANO_MINIMO"]    = cfg["ano_min"]
            M["ANO_MAXIMO"]    = cfg["ano_max"]
            M["OCR_ATIVO"]     = cfg["ocr"]

            print("=" * 58)
            print("  Iniciando")
            print(f"  Período : {self._rotulo_periodo(cfg)}")
            print(f"  OCR     : {'ativo' if cfg['ocr'] else 'desligado'}")
            print(f"  Modo    : {'somente planilha' if cfg['so_planilha'] else 'download completo'}")
            print("=" * 58)

            sessao = M["make_session"]()
            conf   = M["_parse_link"](M["LINK_MURAL"])
            conf   = M["_enriquecer_nome"](conf, sessao)

            nome   = M["sanitize_pasta"](cfg["entidade"] or conf.get("entidade") or conf["nome"])
            destino = os.path.join(cfg["pasta"], f"{nome} {self._sufixo_periodo(cfg)}".strip())
            conf["output_dir"] = destino
            os.makedirs(destino, exist_ok=True)
            print(f"\n  Saída: {destino}\n")

            licitacoes = M["get_all_licitacoes"](sessao, conf)
            if not licitacoes:
                self.fila.put(("fim", "Nenhuma licitação encontrada para o filtro."))
                return

            total = len(licitacoes)
            self.fila.put(("progresso", (0, total)))

            resultados = []
            for i, lic in enumerate(licitacoes, 1):
                if self.cancelar.is_set():
                    print(f"\n[!] Interrompido pelo usuário em {i-1}/{total}.")
                    break
                self.fila.put(("status", f"Licitação {i} de {total} — {lic.get('numero','')}"))
                print(f"\n[{i}/{total}]")
                try:
                    if cfg["so_planilha"]:
                        resultados.append({**lic, "contratos": []})
                    else:
                        r = M["process_licitacao"](sessao, lic, destino)
                        if r:
                            resultados.append(r)
                except Exception as e:
                    print(f"  [!] Erro em {lic.get('numero','?')}: {e}")
                self.fila.put(("progresso", (i, total)))
                M["time"].sleep(M["DELAY"])

            excel = os.path.join(
                destino,
                f"licitacoes_{nome}_{self._sufixo_periodo(cfg)}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            )
            M["gerar_excel"](resultados, excel, conf)

            n_contratos = sum(len(r.get("contratos", [])) for r in resultados)
            print(f"\n  Licitações : {len(resultados)}")
            print(f"  Contratos  : {n_contratos}")
            print(f"  Planilha   : {os.path.basename(excel)}")

            self.fila.put(("fim",
                f"Concluído: {len(resultados)} licitações e {n_contratos} contratos."))

        except Exception as e:
            traceback.print_exc()
            self.fila.put(("fim", f"ERRO: {e}"))
        finally:
            sys.stdout = original

    # ── Auxiliares ────────────────────────────────────────────────────────────

    @staticmethod
    def _normalizar_link(link: str) -> str:
        """Garante domínio atual, rota de listagem e per-page=30."""
        link = link.strip()
        link = re.sub(r"https?://[^/]*tcmpa\.tc\.br", "https://www.tcm.pa.gov.br", link)
        link = re.sub(r"https?://[^/]*tcm\.pa\.gov\.br", "https://www.tcm.pa.gov.br", link)
        if "/licitacoes/listagem" not in link:
            link = link.replace("/mural-de-licitacoes/",
                                "/mural-de-licitacoes/licitacoes/listagem", 1)
        link = re.sub(r"[&?]page=\d+", "", link)
        if "per-page=" not in link:
            link += ("&" if "?" in link else "?") + "per-page=30"
        return link

    @staticmethod
    def _rotulo_periodo(cfg) -> str:
        a, b = cfg["ano_min"], cfg["ano_max"]
        if a is None and b is None: return "todos os anos"
        if a == b:                  return str(a)
        return f"{a} a {b}"

    @staticmethod
    def _sufixo_periodo(cfg) -> str:
        a, b = cfg["ano_min"], cfg["ano_max"]
        if a is None and b is None: return "todos_anos"
        if a == b:                  return str(a)
        return f"{a}-{b}"

    def _finalizar(self, msg):
        self.rodando = False
        self.btn_iniciar.config(state="normal")
        self.btn_parar.config(state="disabled")
        self.status.config(text=msg)
        if msg.startswith("ERRO"):
            self._escrever(f"\n{msg}", "erro")
            messagebox.showerror(APP_TITULO, msg)
        else:
            self._escrever(f"\n{msg}", "ok")
            messagebox.showinfo(APP_TITULO, msg)


if __name__ == "__main__":
    try:
        Painel().mainloop()
    except Exception as exc:
        print(f"Erro ao abrir o painel: {exc}")
        input("Enter para sair...")
