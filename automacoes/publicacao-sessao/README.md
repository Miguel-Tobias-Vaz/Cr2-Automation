# Publicação de Sessão — portal CR2

Publica sessões a partir de **pastas locais** no portal administrativo CR2 (Bubble).

## Estrutura da pasta

```
sessoes_2021/
  33ª Ordinária - 14-10-2021/
    Pauta.pdf
    Ata.pdf
  Ordinária - 11-05-2021/
    Pauta.pdf
    Ata.pdf
  Solene - 19-01-2021/
    Pauta.pdf
```

O nome da pasta vira:

| Pasta | Tipo | Data | Número |
|-------|------|------|--------|
| `33ª Ordinária - 14-10-2021` | Ordinária | 14/10/2021 | 33ª Sessão Ordinária |
| `Ordinária - 11-05-2021` | Ordinária | 11/05/2021 | Sessão Ordinária |

Arquivos reconhecidos por nome: `Pauta`, `Ata`, `Presença`/`Lista`, `Votações`.

## Painel

http://127.0.0.1:8765/sessao.html

Campos: usuário, senha, URL admin Sessão, **pasta base**.

## CLI

```powershell
cd automacoes
.\venv\Scripts\python.exe publicacao-sessao\script.py --yes --test --pasta "C:\Users\tobia\Documents\mds\missao_baixar_sessao\sessoes_2021"
```

Edite no topo de `script.py`: `URL_PORTAL_SESSAO`, `PORTAL_USUARIO`, `PORTAL_SENHA`, `PASTA_SESSOES`.

## Checklist de teste

1. Confirme que a pasta tem subpastas com `Pauta.pdf` / `Ata.pdf`.
2. Cole a URL admin de Sessão.
3. Rode com modo teste (1 sessão) e `--yes`.
4. Confira no portal se Tipo/Data/Número e anexos bateram.
