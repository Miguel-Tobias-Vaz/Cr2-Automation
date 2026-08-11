#!/bin/bash
# Atualiza código na VPS após git pull (NÃO apaga venv nem data/)
set -euo pipefail

SRC="${1:-/root/Cr2-Automation}"
APP_DIR=/opt/opto-automacoes
APP_USER=opto

echo "==> git pull"
cd "$SRC"
git pull

echo "==> rsync (preserva venv e data)"
rsync -a --delete \
  --exclude venv \
  --exclude centro-automacoes/venv \
  --exclude centro-automacoes/deploy/opto.env \
  --exclude __pycache__ \
  --exclude .git \
  --exclude centro-automacoes/data \
  --exclude '*.pyc' \
  "$SRC/" "$APP_DIR/"

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
