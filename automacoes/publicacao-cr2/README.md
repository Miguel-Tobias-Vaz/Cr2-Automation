# Publicação CR2

Publica PDFs de RGF, RREO, Balanço e Balancete no **portal administrativo CR2** (Bubble) via Playwright.

## Executar

```powershell
cd automacoes
.\venv\Scripts\python.exe publicacao-cr2\script.py --test --yes
```

Edite credenciais, URLs do portal e pastas locais no início de `script.py`.

Opções úteis: `--test`, `--yes`, `--so-rgf`, `--ano 2024`. Use `--help` para a lista completa.
