#!/bin/bash
# Backup diário de data/ — usuários, fila e audit.
# Cron exemplo: 0 3 * * * /opt/opto-automacoes/centro-automacoes/deploy/backup-data.sh
set -euo pipefail

APP_DIR="${OPTO_APP_DIR:-/opt/opto-automacoes}"
DATA="$APP_DIR/centro-automacoes/data"
DEST="${OPTO_BACKUP_DIR:-/var/backups/opto}"
RETAIN_DAYS="${OPTO_BACKUP_RETAIN_DAYS:-7}"
STAMP="$(date +%Y%m%d-%H%M)"
ARCHIVE="$DEST/opto-data-$STAMP.tar.gz"

mkdir -p "$DEST"

if [[ ! -d "$DATA" ]]; then
  echo "ERRO: pasta data não encontrada: $DATA"
  exit 1
fi

tar -czf "$ARCHIVE" \
  -C "$APP_DIR/centro-automacoes" \
  data/users \
  data/jobs/queue_state.json \
  data/jobs/completed_recent.json \
  data/audit \
  2>/dev/null || tar -czf "$ARCHIVE" -C "$APP_DIR/centro-automacoes" data/users data/jobs 2>/dev/null || true

if [[ ! -f "$ARCHIVE" ]]; then
  echo "ERRO: falha ao criar $ARCHIVE"
  exit 1
fi

find "$DEST" -name 'opto-data-*.tar.gz' -mtime +"$RETAIN_DAYS" -delete 2>/dev/null || true
echo "OK: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
