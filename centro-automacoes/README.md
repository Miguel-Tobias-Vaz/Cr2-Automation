# Opto Automações

Painel web único para todas as automações em `../automacoes/`.

## Como abrir

```powershell
cd centro-automacoes
.\run.bat
```

**http://127.0.0.1:8765**

## Onde fica cada coisa

| O quê | Onde |
|-------|------|
| Front (HTML/JS/CSS) | `centro-automacoes/front/` |
| Scripts Python | `automacoes/*/script.py` ou `automacoes/dic-est-ter/` |
| API Dic/Est/Ter | integrada neste backend (`milagre_routes.py`) |
| Dados Dic/Est/Ter | `automacoes/dic-est-ter/data/` e `runtime/` |

Não existe mais front duplicado dentro de `automacoes/`.
