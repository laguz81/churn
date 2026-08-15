#!/bin/bash
# config.sh — variables compartidas por publicar.sh / reiniciar.sh / health.sh
#
# No se ejecuta directo: los otros scripts hacen `source "$(dirname "$0")/config.sh"`.
# Un solo lugar para el host, la ruta remota y el dominio publico, en vez de
# repetirlos en cada script (y arriesgar que uno quede desactualizado).

SSH_HOST="dev.ecticsoft"
REMOTE_DIR="/opt/panel-evaluacion"
COMPOSE_FILE="docker-compose.prod.yml"
CONTAINER_NAME="panel_evaluacion"
SERVER_PORT="8090"          # puerto interno en el servidor (127.0.0.1:8090)
PUBLIC_URL="https://churn-test.ecticsoft.com"

# Carpeta local del proyecto (panel_evaluacion/), independiente de desde
# donde se invoque el script.
LOCAL_APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# curl.exe en Windows usa el backend TLS "schannel", que a veces falla
# con CRYPT_E_NO_REVOCATION_CHECK contra certificados recien emitidos
# (revocation-check estricto de Windows, no un problema real del sitio --
# confirmado 2026-08-14 comparando contra curl del servidor y Chrome real,
# ambos funcionando). --ssl-no-revoke es una flag propia de schannel; en
# curl con backend OpenSSL (Linux/Mac) esa flag no existe y el comando
# fallaria, asi que solo se agrega si el backend detectado es schannel.
CURL_PUBLICO=(curl -s --max-time 10)
if curl -V 2>/dev/null | grep -qi schannel; then
    CURL_PUBLICO+=(--ssl-no-revoke)
fi
