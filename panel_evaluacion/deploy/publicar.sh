#!/bin/bash
# publicar.sh — copia el codigo al servidor y reconstruye el contenedor.
#
# NUNCA copia datos/, secreto/ ni data/ — esos no son codigo: datos/ y
# secreto/ los genera preparar_evaluacion.py (contienen la asignacion A/B
# y el desciframiento etiqueta->fuente de la corrida vigente) y data/ es
# la base de calificaciones ya recibidas. Sobrescribirlos por accidente
# invalidaria un estudio en curso. Si hace falta regenerar la asignacion,
# usa preparar_evaluacion.py explicitamente, no este script.
#
# Uso:
#   ./deploy/publicar.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

echo "=== Copiando codigo a $SSH_HOST:$REMOTE_DIR ==="
cd "$LOCAL_APP_DIR"

scp app.py db.py preparar_evaluacion.py exportar_resultados.py \
    requirements.txt Dockerfile .dockerignore \
    docker-compose.yml docker-compose.prod.yml README.md DESPLIEGUE.md \
    "$SSH_HOST:$REMOTE_DIR/"

scp -r templates static "$SSH_HOST:$REMOTE_DIR/"

echo
echo "=== Reconstruyendo y reiniciando el contenedor ==="
ssh "$SSH_HOST" "cd $REMOTE_DIR && docker compose -f $COMPOSE_FILE up -d --build"

echo
echo "=== Publicado. Verificando salud... ==="
"$SCRIPT_DIR/health.sh"
