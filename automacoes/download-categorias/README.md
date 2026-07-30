# Download por categorias

Baixa PDFs listados em uma **categoria WordPress**.

A coleta de posts é a mesma lógica do `download-normas` (modo categoria):

1. **Carregar Mais / infinite scroll** (tema Bunyad) → AJAX `bunyad_block`
2. Caso contrário → paginação clássica `/page/2/`, `/page/3/`…

## Executar

```powershell
cd automacoes
.\venv\Scripts\python.exe download-categorias\script.py
```

Edite `PASTA_BASE`, `URL_CATEGORIA` e `SITE` no início de `script.py`.
`ANOS_FILTRO` e `LIMITE_POSTS` são opcionais.
