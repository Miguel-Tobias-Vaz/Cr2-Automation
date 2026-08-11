# Arquitetura — Opto Automações

Documentação técnica do painel, fila de jobs e deploy na VPS.

## Visão geral

```
Navegador (HTML/JS modules)
        │  HTTPS
        ▼
     Nginx :443
        │
        ▼
  Uvicorn :8765  (FastAPI — centro-automacoes/backend/main.py)
        │
        ▼
  JobManager (singleton, memória + disco)
        │
        ├── Thread → runner Python (documentos, normas, …)
        └── Subprocess → job_worker + Playwright (publicacao, sessao, …)
        │
        ▼
  data/users/{email}/jobs/{id}/
```

## Ciclo de vida do job

| Status | Significado |
|--------|-------------|
| `pending` | Na fila, aguardando slot |
| `running` | Em execução |
| `completed` | Sucesso; ZIP opcional |
| `failed` | Erro |
| `cancelled` | Cancelado pelo usuário |

- Fila **FIFO**; até `OPTO_MAX_JOBS` rodando em paralelo.
- Persistência: `data/jobs/queue_state.json` (pending/running).
- Jobs **concluídos recentes**: `data/jobs/completed_recent.json` (TTL `OPTO_COMPLETED_TTL_S`, default 2 h).

## Pastas `data/`

```
centro-automacoes/data/
├── jobs/
│   ├── queue_state.json
│   └── completed_recent.json
├── users/{email}/
│   ├── uploads/          # ZIP/planilhas enviados
│   ├── output/{servico}/ # saída padrão por ferramenta
│   └── jobs/{job_id}/
│       ├── runtime.json    # credenciais (modo 600)
│       ├── config.json     # config sem senhas
│       ├── job.log
│       └── resultado.zip
├── auth/                 # users.json (login local)
└── audit/
    └── actions.jsonl     # log de ações admin
```

## API principal

| Método | Rota | Auth |
|--------|------|------|
| POST | `/api/jobs` | Sim |
| GET | `/api/jobs/{id}` | Sim + dono |
| GET | `/api/jobs/{id}/logs/stream` | Sim (+ `?access_token=` para SSE) |
| GET | `/api/jobs/{id}/download` | Sim + dono |
| GET | `/api/health` | Mínimo anônimo se auth ativa |
| GET | `/api/admin/health-detail` | Admin |
| POST | `/api/uploads` | Sim |

## Front-end

- ES modules em `front/modules/` (`auth.js`, `upload.js`, `nav.js`, `core.js`, `jobs.js`).
- Entry: `front/shared.js` (type=module).
- Páginas escutam evento `opto-ready` antes de chamar `CR2Centro.*`.

## Variáveis de ambiente (VPS)

Ver [`centro-automacoes/deploy/opto.env.example`](../centro-automacoes/deploy/opto.env.example).

| Variável | Descrição |
|----------|-----------|
| `OPTO_MAX_JOBS` | Jobs simultâneos |
| `OPTO_MAX_QUEUE` | Tamanho máximo da fila |
| `OPTO_JOB_TIMEOUT_S` | Timeout por job (0=off) |
| `OPTO_REQUIRE_AUTH` | Exige login na VPS |
| `OPTO_SUPABASE_*` | Login por e-mail |
| `OPTO_PRINCIPAL_ADMIN` | E-mail do painel Admin |
| `OPTO_CORS_ORIGINS` | Origens CORS permitidas |
| `OPTO_COMPLETED_TTL_S` | Retenção de jobs concluídos no disco |
| `OPTO_WORKER_HEARTBEAT_S` | Detecção de subprocess travado |

## Deploy na VPS

```bash
git pull
bash centro-automacoes/deploy/atualizar-vps.sh
```

- Código em `/opt/opto-automacoes`.
- `data/` e `opto.env` **nunca** sobrescritos pelo rsync.
- Serviço: `systemctl restart opto`.

### Backup

```bash
bash centro-automacoes/deploy/backup-data.sh
# Cron: 0 3 * * *
```

### Monitoramento

```bash
bash centro-automacoes/deploy/check-health.sh
# Cron: */5 * * * *
```

## Segurança

Ver [`centro-automacoes/deploy/SUPABASE_SEGURANCA.md`](../centro-automacoes/deploy/SUPABASE_SEGURANCA.md).

## Testes

```bash
cd centro-automacoes
python -m pytest tests/ -q
```

CI: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
