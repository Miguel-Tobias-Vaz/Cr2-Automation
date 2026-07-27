# Download de Normas Municipais

Baixa Leis, Decretos, Portarias e demais publicações oficiais de portais WordPress (ex.: Inhangapi/PA).

## O que faz

1. Percorre as fontes configuradas (categoria, hub de anos ou página direta)
2. Abre cada post / página anual e localiza os PDFs no corpo
3. **Lê o texto do PDF** (pypdf) quando o link é genérico (“Clique aqui”)
4. Salva com nome padronizado:
   - `Portaria Nº010-2025.pdf` ← lógico: Portaria Nº010/2025
   - `Lei Nº738-2023.pdf`
   - `LDO Nº726-2023.pdf`
   - `LOA Nº733-2023.pdf`
   - `Decreto Nº020-2023.pdf`

> No Windows a barra `/` vira `-` no nome do arquivo.

## Pastas

```
C:\Downloads\Inhangapi\
  Leis\2023\Lei Nº738-2023.pdf
  Decretos\2023\Decreto Nº020-2023.pdf
  Portarias\2023\Portaria Nº114-2023.pdf
  Demais\2023\...
```

## Configuração

No topo de `script.py`:

- `PASTA_BASE` — destino
- `SITE` — domínio
- `FONTES` — lista de URLs com `modo` (`categoria` | `hub_anos` | `pagina`) e `pasta`
- `LER_PDF` — `True` para leitura do PDF
- `LIMITE_POSTS` — use `> 0` só para teste

## Executar

```powershell
cd automacoes
.\venv\Scripts\python.exe download-normas\script.py
```

Ou pelo painel: **http://127.0.0.1:8765/normas.html**

## Dependência extra

```powershell
pip install pypdf
```
