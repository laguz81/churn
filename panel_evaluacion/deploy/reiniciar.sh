#!/bin/bash
# reiniciar.sh — reinicia el contenedor SIN reconstruir la imagen.
#
# Para cuando algo se ve raro y quieres un reinicio limpio rapido, sin
# esperar un build de Docker. Si cambiaste codigo, usa publicar.sh en vez
# de esto (reiniciar.sh no copia nada nuevo al servidor).
#
# La base de datos (data/respuestas.db) es un volumen bind fuera del
# contenedor -- un reinicio (o incluso recrear el contenedor) no la toca.
#
# Uso:
#   ./deploy/reiniciar.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

echo "=== Reiniciando $CONTAINER_NAME en $SSH_HOST ==="
ssh "$SSH_HOST" "cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE restart"

echo
echo "=== Verificando salud tras el reinicio... ==="
"$SCRIPT_DIR/health.sh"
