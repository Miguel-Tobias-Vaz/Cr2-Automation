# Opto Automações

Projeto organizado — scripts em `automacoes/`, painel único em `centro-automacoes/`.

## Estrutura

```
automacoes/                    Uma pasta por automação (scripts + dados)
  download-documentos/
  download-categorias/
  publicacao-cr2/
  dic-est-ter/                   Dic/Est/Ter (sem front duplicado)
  mapa-site/

centro-automacoes/               Painel web Opto (único front)
  front/                         HTML + JS + CSS
  backend/                       API FastAPI
```

## Início rápido

```powershell
cd centro-automacoes
.\run.bat
```

**http://127.0.0.1:8765**

| Página | Automação |
|--------|-----------|
| `/dic-est-ter.html` | Publicação Dic/Est/Ter |
| `/publicacao.html` | RGF, RREO, Balanço, Balancete |
| `/documentos.html` | Download de documentos |
| `/categorias.html` | Download por categoria |
| `/mapa.html` | Mapa WordPress |
