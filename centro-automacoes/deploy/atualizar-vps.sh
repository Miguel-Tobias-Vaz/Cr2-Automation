#!/bin/bash
# Atualiza código na VPS após git pull.
# REGRA INEGOCIÁVEL: nunca copia data/, venv, opto.env, caches nem logs.
set -euo pipefail

SRC="${1:-/root/Cr2-Automation}"
APP_DIR=/opt/opto-automacoes
APP_USER=opto

if [[ ! -f "$SRC/centro-automacoes/backend/main.py" ]]; then
  echo "ERRO: fonte não encontrada em $SRC"
  exit 1
fi

echo "==> git pull"
cd "$SRC"
git pull --ff-only

echo "==> rsync (NÃO toca data/, venv, opto.env, caches, logs)"
rsync -a --delete \
  --exclude '.git/' \
  --exclude 'venv/' \
  --exclude '**/venv/' \
  --exclude 'centro-automacoes/venv/' \
  --exclude 'centro-automacoes/data/' \
  --exclude 'centro-automacoes/deploy/opto.env' \
  --exclude 'opto.env' \
  --exclude '.env' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache/' \
  --exclude '**/cache_ia/' \
  --exclude '**/cache/' \
  --exclude '**/.cache/' \
  --exclude '*.log' \
  --exclude 'instalacao-log.txt' \
  --exclude 'iniciar-log.txt' \
  --exclude 'diagnostico-log.txt' \
  --exclude 'runtime.json' \
  --exclude '**/runtime.json' \
  "$SRC/" "$APP_DIR/"

ENV_FILE="$APP_DIR/centro-automacoes/deploy/opto.env"
  if [[ -f "$ENV_FILE" ]]; then
  echo "==> validando opto.env"
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  if [[ -n "${OPTO_SUPABASE_URL:-}" && -n "${OPTO_SUPABASE_ANON_KEY:-}" ]]; then
    echo "==> gerando front/supabase-config.js a partir de opto.env"
    SUPABASE_JS="$APP_DIR/centro-automacoes/front/supabase-config.js"
    cat > "$SUPABASE_JS" <<EOF
// Gerado automaticamente pelo deploy — não commitar.
window.SUPABASE_URL = "${OPTO_SUPABASE_URL}";
window.SUPABASE_ANON_KEY = "${OPTO_SUPABASE_ANON_KEY}";
EOF
    chown "$APP_USER:$APP_USER" "$SUPABASE_JS"
    chmod 640 "$SUPABASE_JS"
  fi
else
  echo "AVISO: $ENV_FILE não encontrado — copie de opto.env.example"
fi

# Garante pastas de dados (cria se faltarem; nunca apaga conteúdo)
mkdir -p \
  "$APP_DIR/centro-automacoes/data/users" \
  "$APP_DIR/centro-automacoes/data/jobs" \
  "$APP_DIR/centro-automacoes/data/auth" \
  "$APP_DIR/centro-automacoes/data/audit"

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

DATA_DIR="$APP_DIR/centro-automacoes/data"
if [[ -d "$DATA_DIR" ]]; then
  chmod 750 "$DATA_DIR" 2>/dev/null || true
  chmod -R u+rwX,go-rwx "$DATA_DIR/users" 2>/dev/null || true
  chmod -R u+rwX,go-rwx "$DATA_DIR/auth" 2>/dev/null || true
fi

VPY="$APP_DIR/centro-automacoes/venv/bin/python"
if [[ ! -x "$VPY" ]]; then
  echo "==> venv ausente — recriando..."
  sudo -u "$APP_USER" bash <<'EOSU'
set -e
cd /opt/opto-automacoes/centro-automacoes
python3 -m venv venv
./venv/bin/pip install -U pip wheel -q
./venv/bin/pip install -r requirements.txt -q
./venv/bin/pip install -r ../automacoes/requirements.txt -q
./venv/bin/python -m playwright install chromium
EOSU
  "$APP_DIR/centro-automacoes/venv/bin/playwright" install-deps chromium 2>/dev/null || true
else
  echo "==> dependências Python"
  sudo -u "$APP_USER" "$APP_DIR/centro-automacoes/venv/bin/pip" install -r "$APP_DIR/centro-automacoes/requirements.txt" -q
  sudo -u "$APP_USER" "$APP_DIR/centro-automacoes/venv/bin/pip" install -r "$APP_DIR/automacoes/requirements.txt" -q
fi

systemctl reset-failed opto 2>/dev/null || true
systemctl restart opto
sleep 2
systemctl status opto --no-pager || true
curl -sf http://127.0.0.1:8765/api/health && echo "" || journalctl -u opto -n 25 --no-pager

echo ""
echo "OK. data/ em produção NÃO foi alterada."
