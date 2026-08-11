#!/bin/bash
# Verifica se o painel responde (cron / alerta).
# Cron: */5 * * * * /opt/opto-automacoes/centro-automacoes/deploy/check-health.sh
set -euo pipefail

URL="${OPTO_HEALTH_URL:-http://127.0.0.1:8765/api/health}"
LOG="${OPTO_HEALTH_LOG:-/var/log/opto-health.log}"

if curl -sf --max-time 15 "$URL" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

MSG="$(date -Iseconds) OFFLINE: $URL"
echo "$MSG" >> "$LOG"
# Opcional: webhook Telegram — defina OPTO_ALERT_WEBHOOK
if [[ -n "${OPTO_ALERT_WEBHOOK:-}" ]]; then
  curl -sf -X POST "$OPTO_ALERT_WEBHOOK" \
    -d "text=Opto Automações: $MSG" >/dev/null 2>&1 || true
fi
exit 1
