#!/bin/bash
# Instala en el host (VPS) el cron del reporte diario de gasto por Telegram.
# Corre a las 00:00 UTC, que son las 21:00 en Argentina.
#
# Uso: bash scripts/instalar-cron-reporte.sh
# Se corre en el VPS, parado en la carpeta del repo (~/olivia).
set -euo pipefail

LINEA="0 0 * * * cd $(pwd) && docker compose exec -T brain python -m brain.reporte_diario >> /var/log/olivia-reporte.log 2>&1"

# Idempotente: si ya está la línea, no la duplica.
if crontab -l 2>/dev/null | grep -qF "brain.reporte_diario"; then
  echo "Ya estaba instalado el cron del reporte diario."
else
  (crontab -l 2>/dev/null; echo "$LINEA") | crontab -
  echo "Cron instalado: reporte diario a las 21hs Argentina (00:00 UTC)."
fi

crontab -l | grep reporte_diario
