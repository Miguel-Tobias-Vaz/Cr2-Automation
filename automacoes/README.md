# Automações CR2

Scripts Python organizados — **uma pasta por automação**. O painel web fica só em `centro-automacoes/`.

## Pastas

| Pasta | Função |
|-------|--------|
| `download-documentos/` | Download de PDFs por página |
| `download-categorias/` | Download por categoria WordPress |
| `publicacao-cr2/` | RGF, RREO, Balanço e Balancete (portal Bubble) |
| `dic-est-ter/` | **Publicação Dic/Est/Ter** (dívida, estagiários, terceirizados) |
| `mapa-site/` | Mapa do site WordPress |

Cada automação tem `script.py` (ou script dedicado em `dic-est-ter/`) — edite as variáveis no topo antes de rodar.

## Painel Opto Automações

```powershell
cd centro-automacoes
.\run.bat
```

→ **http://127.0.0.1:8765** (todas as automações, inclusive Dic/Est/Ter em `/dic-est-ter.html`)

## Instalação

```powershell
cd automacoes
.\instalar_dependencias.bat
```

Leia **[GUIA_WINDOWS.md](GUIA_WINDOWS.md)** para detalhes.
