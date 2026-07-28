# Opto Automações

Painel web com automações CR2 (downloads, normas, licitações, publicação, mapa…).

## Para o time (Windows) — mais fácil

### 1. Receber o projeto
- ZIP gerado com `GERAR_PACOTE.bat`, **ou**
- clone do Git

### 2. Instalar (só na primeira vez)
1. Instale o [Python 3](https://www.python.org/downloads/) e marque **Add python.exe to PATH**
2. Clique duas vezes em **`INSTALAR.bat`**
3. Espere terminar (cria `venv` e instala pacotes)

### 3. Usar no dia a dia
1. Clique duas vezes em **`INICIAR.bat`**
2. Abra no navegador: **http://127.0.0.1:8765**
3. Para parar: feche a janela preta (ou Ctrl+C)

Não precisa abrir o Cursor/VS Code para usar o painel.

## Para quem vai distribuir

Na sua máquina, na pasta do projeto:

```text
GERAR_PACOTE.bat
```

Isso cria um ZIP (sem `venv`, `.git`, caches). Envie o ZIP.

Cada colega: extrair → `INSTALAR.bat` → `INICIAR.bat`.

## Estrutura

```
INSTALAR.bat                 Instalação única
INICIAR.bat                  Sobe o painel
GERAR_PACOTE.bat             Gera ZIP para enviar

automacoes/                  Scripts
centro-automacoes/           Painel FastAPI + front
```

## Páginas do painel

| Página | Automação |
|--------|-----------|
| `/documentos.html` | Download de documentos |
| `/categorias.html` | Download por categoria |
| `/normas.html` | Download de normas |
| `/licitacoes.html` | Licitações |
| `/publicacao.html` | Publicação CR2 |
| `/dic-est-ter.html` | Dic/Est/Ter |
| `/mapa.html` | Mapa WordPress |

## Requisitos extras (só se for usar)

- **Publicação CR2 / Dic-Est-Ter:** Chromium (já instalado pelo `INSTALAR.bat` via Playwright)
- **OCR em licitações escaneadas:** [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) (opcional)
- Pasta de downloads com permissão de escrita (ex.: `C:\Downloads`)

## Problemas comuns

| Problema | Solução |
|----------|---------|
| Janela do `INSTALAR` abre e fecha | Atualize o ZIP (versão nova mantém a janela aberta). Instale Python do [python.org](https://www.python.org/downloads/) com **Add to PATH**. Evite só o atalho da Microsoft Store. |
| `Python não encontrado` | Reinstalar Python com PATH marcado; feche e abra o `INSTALAR.bat` de novo |
| Erro na instalação | Envie o arquivo `instalacao-log.txt` (criado ao lado do `INSTALAR.bat`) |
| Porta 8765 ocupada | Fechar a janela antiga do painel e rodar `INICIAR.bat` de novo |
| Página em branco / antiga | Ctrl+F5 no navegador |
| Erro de SSL em sites | Marcar “Ignorar erros de SSL” na automação |

**Importante:** no GitHub use **Code → Download ZIP**, **extraia** a pasta, e só então rode `INSTALAR.bat` (não execute de dentro do visualizador de ZIP).
