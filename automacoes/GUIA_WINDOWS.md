# Guia Windows — Automações CR2

Passo a passo para **instalar**, **configurar** e **rodar** os scripts da pasta `automacoes` no notebook (Windows 10/11).

---

## Índice

1. [O que tem nesta pasta](#1-o-que-tem-nesta-pasta)
2. [Copiar para o notebook](#2-copiar-para-o-notebook)
3. [Instalar Python no Windows](#3-instalar-python-no-windows)
4. [Instalar dependências dos scripts](#4-instalar-dependências-dos-scripts)
5. [Como editar a configuração](#5-como-editar-a-configuração)
6. [Script 1 — Download de documentos](#6-script-1--download-de-documentos)
7. [Script 2 — Download por categoria](#7-script-2--download-por-categoria)
8. [Script 3 — Publicação no portal CR2](#8-script-3--publicação-no-portal-cr2)
9. [Script 4 — Mapa do site WordPress](#9-script-4--mapa-do-site-wordpress)
10. [Fluxo recomendado](#10-fluxo-recomendado)
11. [Erros comuns e soluções](#11-erros-comuns-e-soluções)
12. [Checklist rápido por entidade](#12-checklist-rápido-por-entidade)

---

## 1. O que tem nesta pasta

| Arquivo | Para que serve |
|---------|----------------|
| `download-documentos/script.py` | Baixa PDFs de **páginas** do site da entidade (RGF, balancete, relatórios…) |
| `download-categorias/script.py` | Baixa PDFs de uma **categoria WordPress** (lista de posts com paginação) |
| `publicacao-cr2/script.py` | Sobe os PDFs para o **portal administrativo CR2** (Bubble) |
| `mapa-site/script.py` | Cria páginas no **WordPress** e monta o **mapa do site** |
| `instalar_dependencias.bat` | Instala tudo com um clique |
| `requirements.txt` | Lista de bibliotecas Python |

---

## 2. Copiar para o notebook

1. Copie a pasta **`automacoes`** para um local simples, por exemplo:
   ```
   C:\Users\SEU_NOME\Documentos\CR2\automacoes
   ```
2. **Não** coloque dentro de `OneDrive` ou pastas que sincronizam enquanto o script roda (pode travar downloads).
3. Mantenha os **4 scripts `.py`** juntos na mesma pasta.

---

## 3. Instalar Python no Windows

### Se ainda não tem Python

1. Acesse [python.org/downloads](https://www.python.org/downloads/)
2. Baixe **Python 3.11** ou **3.12** (evite 3.13 se der erro com bibliotecas antigas)
3. Na instalação, marque:
   - **Add python.exe to PATH**
   - **Install pip**
4. Feche e abra o **Prompt de Comando** ou **PowerShell**
5. Teste:
   ```powershell
   python --version
   ```
   Deve aparecer algo como `Python 3.12.x`

### Abrir a pasta no terminal

1. Abra a pasta `automacoes` no Explorador de Arquivos
2. Clique na barra de endereço, digite `cmd` e Enter  
   **ou** Shift + botão direito → **Abrir janela do PowerShell aqui**

---

## 4. Instalar dependências dos scripts

### Opção A — automática (recomendada)

Dê **duplo clique** em:

```
instalar_dependencias.bat
```

Isso cria a pasta `venv`, instala `requests`, `beautifulsoup4`, `playwright` e o navegador Chromium.

### Opção B — manual

No PowerShell, dentro da pasta `automacoes`:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

### Qual Python usar para rodar?

Sempre prefira o da pasta `venv`:

```powershell
.\venv\Scripts\python.exe "download-documentos\script.py"
```

> **Dica:** No VS Code / Cursor, abra a pasta `automacoes` e selecione o interpretador `venv\Scripts\python.exe`.

---

## 5. Como editar a configuração

1. Abra o script no **Bloco de Notas**, **VS Code** ou **Cursor**
2. Vá até o bloco **`CONFIG`** ou **`CONFIGURAÇÕES`** no **início do arquivo**
3. Altere só o que está indicado (URLs, pastas, login)
4. **Salve** (`Ctrl+S`) antes de rodar
5. **Nunca** commite senhas em repositório público — use só no notebook local

### Caminhos no Windows

Use o formato com `r` na frente das aspas:

```python
PASTA_BASE = r"C:\Downloads"
```

Ou barras duplas:

```python
PASTA_BASE = "C:\\Downloads"
```

---

## 6. Script 1 — Download de documentos

**Arquivo:** `download-documentos\script.py`

### O que faz

- Acessa uma ou várias **URLs de páginas** de transparência
- Encontra links de PDF (inclui Google Drive público)
- Salva em: `PASTA_BASE\NomeDoTipo\Ano\arquivo.pdf`
- Em balancete, separa **Despesa** e **Receita** quando a página tiver esses títulos
- No final, mostra resumo e **mini relatório** de pulados/erros (se houver)

### O que configurar

Abra o script e edite:

| Variável | O que colocar | Exemplo |
|----------|---------------|---------|
| `PASTA_BASE` | Onde salvar os PDFs | `r"C:\Downloads"` |
| `TIPO_DOCUMENTO` | Nome fixo da pasta (opcional) | `""` = usa o título da página |
| `URLS_PAGINAS` | Lista de páginas para baixar | ver abaixo |

**Exemplo de `URLS_PAGINAS`:**

```python
URLS_PAGINAS = [
    "https://camarasuaentidade.pa.gov.br/portal-da-transparencia/relatorio-de-gestao-fiscal-rgf/",
    "https://camarasuaentidade.pa.gov.br/portal-da-transparencia/balancete-financeiro/",
    {"url": "https://...", "tipo": "Relatório de Gestão"},
]
```

### Como rodar

```powershell
cd C:\Users\SEU_NOME\Documentos\CR2\automacoes
.\venv\Scripts\python.exe "download-documentos\script.py"
```

**URLs extras sem editar o arquivo:**

```powershell
.\venv\Scripts\python.exe "download-documentos\script.py" --url "https://site.gov.br/pagina/"
```

**Ver ajuda:**

```powershell
.\venv\Scripts\python.exe "download-documentos\script.py" --help
```

### Estrutura de pastas gerada

```
C:\Downloads\
└── Relatório de Gestão Fiscal (RGF)\    ← título da página ou TIPO_DOCUMENTO
    └── 2024\
        └── 1º Quadrimestre-2024.pdf
```

### Passo a passo na prática

1. Abra o site da entidade e copie a URL da página de transparência (ex.: RGF)
2. Cole em `URLS_PAGINAS`
3. Confira `PASTA_BASE`
4. Rode o script
5. Acompanhe no terminal: `[OK]`, `[PULADO]` (já existe), `[ERRO]`
6. Se houver problemas, veja o arquivo `relatorio_download_AAAAAMMDD_HHMMSS.txt` em `PASTA_BASE`

---

## 7. Script 2 — Download por categoria

**Arquivo:** `download-categorias\script.py`

### O que faz

- Entra na **listagem** de uma categoria WordPress (`/page/2/`, `/page/3/`…)
- Abre **cada post** da listagem
- Baixa todos os PDFs do corpo do artigo
- Organiza em subpastas por ano

### O que configurar

| Variável | O que colocar | Exemplo |
|----------|---------------|---------|
| `PASTA_BASE` | Pasta raiz dos downloads | `r"C:\Downloads"` |
| `URL_CATEGORIA` | URL da categoria (com `/` no final) | `https://camara.../legislacao/` |
| `SITE` | Domínio do site (sem path) | `https://camara...pa.gov.br` |

### Como rodar

```powershell
.\venv\Scripts\python.exe "download-categorias\script.py"
```

### Passo a passo na prática

1. No WordPress da entidade, abra a **página da categoria** que lista os posts (não um post individual)
2. Copie a URL completa para `URL_CATEGORIA`
3. Preencha `SITE` com o mesmo domínio
4. Rode e aguarde — pode demorar se houver muitas páginas de listagem

---

## 8. Script 3 — Publicação no portal CR2

**Arquivo:** `publicacao-cr2\script.py`

### O que faz

- Abre o **navegador** (Chromium via Playwright)
- Faz login no portal CR2
- Para cada PDF nas pastas locais, preenche o formulário Bubble e publica
- Tipos: **RGF**, **RREO**, **Balancete**, **Balanço e Relatórios Anuais**

### Pré-requisito

- PDFs já baixados e nas **pastas corretas** (geralmente pelo script de documentos)
- URLs do **painel admin** de cada tipo no portal CR2
- Usuário e senha do portal

### O que configurar

| Variável | O que colocar |
|----------|---------------|
| `PASTA_RGF` | Pasta local dos PDFs de RGF |
| `PASTA_RREO` | Pasta local dos PDFs de RREO |
| `PASTA_BALANCETE` | Pasta do balancete |
| `PASTA_BALANCO_REL_ANUAIS` | Pasta de balanço/relatórios anuais |
| `URL_PORTAL_RGF` | URL admin RGF no Bubble (**vazio = desligado**) |
| `URL_PORTAL_RREO` | URL admin RREO |
| `URL_PORTAL_BALANCETE` | URL admin Balancete |
| `URL_PORTAL_BALANCO_REL_ANUAIS` | URL admin Balanço/Rel. Anuais |
| `PORTAL_USUARIO` | Login do portal |
| `PORTAL_SENHA` | Senha do portal |
| `HEADLESS` | `False` = vê o navegador; `True` = invisível |
| `MODO_TESTE` | `True` ou use `--test` = só 1 PDF por fila |

**Regra importante:** URL vazia (`""`) = aquele tipo **não roda**.

### Estrutura esperada das pastas

**RGF / RREO** (por ano):
```
C:\Downloads\Relatório de Gestão Fiscal (RGF)\
  2024\
    1º Quadrimestre-2024.pdf
```

**Balancete** (mês-ano):
```
C:\Downloads\Balancete Financeiro\
  Balancete de Despesa\
    2025\
      Janeiro-2025.pdf
```

**Balanço / Relatórios Anuais:**
```
C:\Downloads\Balanço e Relatórios Anuais\
  Relatorio de Gestao-2024\
    documento.pdf
```

### Como rodar

**Primeira vez — teste com 1 PDF:**

```powershell
.\venv\Scripts\python.exe "publicacao-cr2\script.py" --test --yes
```

**Só RGF, ano 2024:**

```powershell
.\venv\Scripts\python.exe "publicacao-cr2\script.py" --so-rgf --ano 2024
```

**Ver todas as opções:**

```powershell
.\venv\Scripts\python.exe "publicacao-cr2\script.py" --help
```

| Opção | Significado |
|-------|-------------|
| `--test` / `-t` | Máximo 1 PDF por fila |
| `--yes` / `-y` | Pula confirmações |
| `--ano 2024` / `-a 2024` | Só subpasta desse ano (RGF/RREO) |
| `--todos` | Todos os anos |
| `--so-rgf` | Só RGF |
| `--so-rreo` | Só RREO |
| `--so-balancete` | Só balancete |
| `--so-balanco-rel` | Só balanço/relatórios anuais |

### Passo a passo na prática

1. Baixe os PDFs com o script de documentos
2. Confira se as pastas batem com `PASTA_RGF`, etc.
3. No portal CR2, abra cada módulo (RGF, RREO…) e copie a URL da barra de endereço
4. Preencha login e URLs no CONFIG
5. Rode com `--test` e acompanhe o navegador
6. Se OK, rode sem `--test` para publicar tudo

> O script pode criar `venv` e instalar Playwright sozinho na primeira execução, mas usar `instalar_dependencias.bat` antes evita surpresas.

---

## 9. Script 4 — Mapa do site WordPress

**Arquivo:** `mapa-site\script.py`

### O que faz

- Conecta no **WordPress** da entidade via REST API
- Cria páginas filhas com link para o portal CR2
- Atualiza a página **Mapa do Site** com a lista organizada por categoria

### O que configurar

| Variável | O que colocar |
|----------|---------------|
| `WP_URL` | Site WordPress (sem barra no final) | `https://camara...pa.gov.br` |
| `USER` | Usuário WordPress |
| `APP_PASSWORD` | **Senha de aplicativo** (não é a senha normal) |
| `SLUG_MAPA_DO_SITE` | Slug da página mapa | geralmente `mapa-do-site` |
| `PAGINAS` | Dicionário com categorias, títulos e URLs CR2 |

### Como gerar a senha de aplicativo

1. WordPress → **Usuários** → **Perfil**
2. Role até **Senhas de aplicativo**
3. Nome: `CR2-automacao` → **Adicionar**
4. Copie a senha gerada (com espaços) para `APP_PASSWORD`

### Exemplo de `PAGINAS`

```python
PAGINAS = {
    "Receitas e Despesas": [
        ("Receitas", "https://www.portalcr2.com.br/receitas/receitas-cm-exemplo"),
        ("Despesas", "https://www.portalcr2.com.br/despesas/despesas-cm-exemplo"),
    ],
}
```

Cada tupla é: `(Título da página no WordPress, URL do módulo no portal CR2)`.

### Como rodar

```powershell
.\venv\Scripts\python.exe "mapa-site\script.py"
```

No final, pressione **Enter** para fechar a janela.

### Passo a passo na prática

1. Monte a lista de links CR2 da entidade (copie do portal ou do material da CR2)
2. Organize em `PAGINAS` por seção
3. Crie senha de aplicativo no WordPress
4. Rode — o script testa conexão antes de criar páginas
5. Confira no site: `https://suaentidade.gov.br/mapa-do-site/`

---

## 10. Fluxo recomendado

Para uma entidade nova, siga esta ordem:

```
┌─────────────────────────────────────────────────────────────┐
│  1. instalar_dependencias.bat                               │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  2. download-documentos\script.py  →  baixar PDFs               │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  3. publicacao-cr2\script.py (--test)  →  testar 1 PDF   │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  4. publicacao-cr2\script.py  →  publicar tudo           │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  5. mapa-site\script.py  →  mapa do site no WordPress       │
└─────────────────────────────────────────────────────────────┘
```

**Download por categoria** entra quando os PDFs estão em posts WordPress (portarias, legislação etc.), em vez de páginas fixas de transparência.

---

## 11. Erros comuns e soluções

| Erro | Causa provável | O que fazer |
|------|----------------|-------------|
| `'python' não é reconhecido` | Python não está no PATH | Reinstale Python marcando **Add to PATH** |
| `ModuleNotFoundError: requests` | Biblioteca não instalada | Rode `instalar_dependencias.bat` |
| `ModuleNotFoundError: playwright` | Playwright não instalado | Rode o `.bat` ou `pip install playwright` + `playwright install chromium` |
| `401` / `rest_not_logged_in` (mapa) | Usuário ou senha de aplicativo errados | Gere nova senha de aplicativo no WordPress |
| `[PULADO] já existe` | PDF já foi baixado antes | Normal — apague o arquivo se quiser baixar de novo |
| `[ERRO] 404` | Link quebrado no site da entidade | Confira a URL no navegador |
| Publicador não acha PDF | Pasta ou nome diferente do esperado | Compare com a seção 8 (estrutura de pastas) |
| Navegador não abre | `HEADLESS = True` | Mude para `False` para ver o que acontece |
| Script trava no login | Credenciais ou captcha | Confira usuário/senha; faça login manual se necessário |

---

## 12. Checklist rápido por entidade

Use como lista ao configurar um cliente novo:

- [ ] Python instalado + `instalar_dependencias.bat` executado
- [ ] URLs das páginas de transparência coletadas
- [ ] `download-documentos\script.py` — `PASTA_BASE` e `URLS_PAGINAS` preenchidos
- [ ] PDFs baixados e pastas conferidas
- [ ] URLs admin do portal CR2 (RGF, RREO, balancete, balanço)
- [ ] `publicacao-cr2\script.py` — login + URLs + teste com `--test`
- [ ] Publicação completa
- [ ] WordPress — senha de aplicativo criada
- [ ] `mapa-site\script.py` — `PAGINAS` atualizado com links CR2 da entidade
- [ ] Mapa do site verificado no navegador

---

## Dúvidas frequentes

**Preciso rodar os 4 scripts sempre?**  
Não. Use só o que precisa: só download, só publicação, ou só mapa.

**Posso rodar de qualquer pasta?**  
Sim, desde que use o caminho completo do Python e do script, ou `cd` até `automacoes` antes.

**O script apaga arquivos?**  
Não apaga PDFs baixados. Em erro de download, remove apenas arquivo incompleto/corrompido.

**Posso passar a pasta automacoes por WhatsApp/e-mail?**  
Sim. Quem receber segue este guia desde o passo 2.

---

*Última atualização: scripts da pasta automacoes — RGF, RREO, Balancete, Balanço, downloads e mapa WordPress.*
