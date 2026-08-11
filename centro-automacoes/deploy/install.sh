#!/bin/bash
# Opto Automações — instalação em Ubuntu 22.04/24.04 (VPS)
# Uso: bash deploy/install.sh
set -euo pipefail

APP_USER="${APP_USER:-opto}"
APP_DIR="${APP_DIR:-/opt/opto-automacoes}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Pacotes do sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-pip \
  tesseract-ocr tesseract-ocr-por \
  poppler-utils \
  git curl nginx \
  libgl1 libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2

if ! id "$APP_USER" &>/dev/null; then
  echo "==> Usuário $APP_USER"
  useradd -m -s /bin/bash "$APP_USER"
fi

echo "==> Copiando projeto para $APP_DIR (sem data/, venv, opto.env, caches, logs)"
mkdir -p "$APP_DIR"
EXCLUDE_FILE="$REPO_DIR/deploy/rsync-exclude.txt"
if [[ -f "$EXCLUDE_FILE" ]]; then
  # REPO_DIR é centro-automacoes; sobe um nível para a raiz do monorepo
  ROOT_DIR="$(cd "$REPO_DIR/.." && pwd)"
  rsync -a --delete --exclude-from="$EXCLUDE_FILE" "$ROOT_DIR/" "$APP_DIR/"
else
  rsync -a --delete \
    --exclude 'venv/' \
    --exclude '**/venv/' \
    --exclude '__pycache__/' \
    --exclude '.git/' \
    --exclude 'centro-automacoes/data/' \
    --exclude 'centro-automacoes/venv/' \
    --exclude 'centro-automacoes/deploy/opto.env' \
    --exclude '*.pyc' \
    --exclude '*.log' \
    "$REPO_DIR/../" "$APP_DIR/"
fi

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Python venv + dependências"
sudo -u "$APP_USER" bash <<EOSU
set -e
cd "$APP_DIR/centro-automacoes"
python3 -m venv venv
./venv/bin/pip install -U pip wheel
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install -r ../automacoes/requirements.txt
./venv/bin/playwright install chromium
EOSU

# Playwright deps de sistema (root)
"$APP_DIR/centro-automacoes/venv/bin/playwright" install-deps chromium || true

mkdir -p "$APP_DIR/centro-automacoes/data/users"
mkdir -p "$APP_DIR/centro-automacoes/data/jobs"
mkdir -p "$APP_DIR/centro-automacoes/data/auth"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/centro-automacoes/data"

ENV_FILE="$APP_DIR/centro-automacoes/deploy/opto.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$APP_DIR/centro-automacoes/deploy/opto.env.example" "$ENV_FILE"
  echo ""
  echo ">>> Edite $ENV_FILE (senha admin, etc.) antes de iniciar o serviço."
fi

echo "==> systemd"
cp "$APP_DIR/centro-automacoes/deploy/opto.service" /etc/systemd/system/opto.service
systemctl daemon-reload
systemctl enable opto.service

echo ""
echo "Pronto. Próximos passos:"
echo "  1. nano $ENV_FILE"
echo "  2. systemctl start opto"
echo "  3. systemctl status opto"
echo "  4. Configure Nginx: deploy/nginx-opto.conf + certbot"
