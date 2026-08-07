#!/bin/bash
# Cole INTEIRO no Terminal da Hostinger (VPS → Terminal no painel)
# Antes: envie o ZIP com scp OU faça git clone na pasta indicada abaixo.
set -euo pipefail

APP_USER=opto
APP_DIR=/opt/opto-automacoes
SRC="${1:-/root/Cr2-Automation}"

echo "=== Opto Automações — bootstrap VPS ==="

if [[ ! -f "$SRC/centro-automacoes/backend/main.py" ]]; then
  echo "ERRO: pasta do projeto não encontrada em: $SRC"
  echo "Opções:"
  echo "  1) git clone SEU_REPO /root/Cr2-Automation"
  echo "  2) scp do ZIP e unzip em /root/Cr2-Automation"
  echo "  3) bash bootstrap-hostinger.sh /caminho/correcto"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv tesseract-ocr tesseract-ocr-por poppler-utils \
  rsync nginx git curl unzip \
  libgl1 libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2

id "$APP_USER" &>/dev/null || useradd -m -s /bin/bash "$APP_USER"

mkdir -p "$APP_DIR"
rsync -a --delete \
  --exclude venv --exclude __pycache__ --exclude .git \
  --exclude centro-automacoes/venv \
  "$SRC/" "$APP_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

sudo -u "$APP_USER" bash <<'EOSU'
set -e
cd /opt/opto-automacoes/centro-automacoes
python3 -m venv venv
./venv/bin/pip install -U pip wheel -q
./venv/bin/pip install -r requirements.txt -q
./venv/bin/pip install -r ../automacoes/requirements.txt -q
./venv/bin/playwright install chromium
EOSU

/opt/opto-automacoes/centro-automacoes/venv/bin/playwright install-deps chromium 2>/dev/null || true

mkdir -p "$APP_DIR/centro-automacoes/data/users" "$APP_DIR/centro-automacoes/data/jobs"
ENV="$APP_DIR/centro-automacoes/deploy/opto.env"
if [[ ! -f "$ENV" ]]; then
  cp "$APP_DIR/centro-automacoes/deploy/opto.env.example" "$ENV"
  # Senha temporária — TROQUE depois
  sed -i 's/TROQUE_ESTA_SENHA/OptoTemp2026!/g' "$ENV"
  echo ">>> Senha admin TEMPORÁRIA: OptoTemp2026!  — troque em $ENV"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR/centro-automacoes/data"

cp "$APP_DIR/centro-automacoes/deploy/opto.service" /etc/systemd/system/opto.service
systemctl daemon-reload
systemctl enable opto
systemctl restart opto

IP=$(curl -4 -s ifconfig.me || hostname -I | awk '{print $1}')
cat > /etc/nginx/sites-available/opto <<NGX
server {
    listen 80;
    server_name _;
    client_max_body_size 160M;
    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 3600s;
        proxy_buffering off;
    }
}
NGX
ln -sf /etc/nginx/sites-available/opto /etc/nginx/sites-enabled/opto
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

sleep 2
if curl -sf http://127.0.0.1:8765/api/health | grep -q '"ok"'; then
  echo ""
  echo "============================================"
  echo "  OK! Painel: http://${IP}/"
  echo "  Login: http://${IP}/login.html"
  echo "  Usuário: admin  Senha: OptoTemp2026!"
  echo "  Troque a senha em: $ENV"
  echo "============================================"
else
  echo "Serviço não respondeu. Veja: journalctl -u opto -n 40 --no-pager"
  exit 1
fi
