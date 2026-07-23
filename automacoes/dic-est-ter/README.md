# Publicação Dic/Est/Ter

Dívida ativa, estagiários e terceirizados — planilhas Google Drive → portal CR2 (Playwright).

## Estrutura (sem front duplicado)

```
dic-est-ter/
  publicar_estagiario_terceirizado_divida.py  ← script principal
  servidor_front.py                           ← worker da API (usado pelo Opto)
  job_runtime.py                              ← cache, logs, checkpoint
  data/                                       ← planilhas e cache CSV
  refs/                                       ← referências
  runtime/                                    ← logs de execução
```

O **front** fica apenas em `centro-automacoes/front/dic-est-ter.html`.

## Terminal

```powershell
cd automacoes
.\venv\Scripts\python.exe dic-est-ter\publicar_estagiario_terceirizado_divida.py --test --yes
```

## Painel

**http://127.0.0.1:8765/dic-est-ter.html**
