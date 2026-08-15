#!/bin/bash
# health.sh — comprobacion de salud del panel desplegado.
#
# Corre 6 chequeos independientes, imprime PASS/FAIL en cada uno, y sale
# con status 0 solo si TODOS pasan (status 1 si alguno falla) -- pensado
# para poder engancharse a un cron/monitor mas adelante, no solo para
# lectura humana.
#
# Uso:
#   ./deploy/health.sh
set -uo pipefail   # sin -e: queremos que TODOS los chequeos corran aunque uno falle

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

FALLOS=0
# Firma de templates/no_encontrado.html usada en los chequeos 2 y 3, para
# confirmar que responde nuestra app y no un 404 generico de nginx/Cloudflare.

check() {
    local nombre="$1" condicion="$2" detalle="${3:-}"
    if [ "$condicion" = "0" ]; then
        echo "[OK  ] $nombre"
    else
        echo "[FAIL] $nombre${detalle:+ -- $detalle}"
        FALLOS=$((FALLOS + 1))
    fi
}

echo "=== Salud de $CONTAINER_NAME ($SSH_HOST -> $PUBLIC_URL) ==="
echo

# 1. Contenedor corriendo
estado_container=$(ssh "$SSH_HOST" "docker inspect -f '{{.State.Status}}' $CONTAINER_NAME 2>&1" || echo "error")
if [ "$estado_container" = "running" ]; then
    check "contenedor '$CONTAINER_NAME' esta corriendo" 0
else
    check "contenedor '$CONTAINER_NAME' esta corriendo" 1 "estado=$estado_container"
fi

# 2. Puerto interno responde con la firma de la app (no un puerto muerto)
resp_interno=$(ssh "$SSH_HOST" "curl -s http://127.0.0.1:$SERVER_PORT/ruta-inexistente-para-probar" 2>&1 || echo "")
if echo "$resp_interno" | grep -qi "no encontrada"; then
    check "puerto interno 127.0.0.1:$SERVER_PORT responde (app propia, no generico)" 0
else
    check "puerto interno 127.0.0.1:$SERVER_PORT responde (app propia, no generico)" 1 "respuesta inesperada"
fi

# 3. URL publica responde con la firma de la app (nginx + Cloudflare + cert ok)
resp_publico=$("${CURL_PUBLICO[@]}" "$PUBLIC_URL/ruta-inexistente-para-probar" 2>&1 || echo "")
if echo "$resp_publico" | grep -qi "no encontrada"; then
    check "URL publica $PUBLIC_URL responde (app propia, no generico)" 0
else
    check "URL publica $PUBLIC_URL responde (app propia, no generico)" 1 "respuesta inesperada o sin conexion"
fi

# 4. secreto/decode.json NO debe ser accesible por HTTP (interno)
code_secreto_interno=$(ssh "$SSH_HOST" "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$SERVER_PORT/secreto/decode.json" 2>/dev/null)
code_secreto_interno="${code_secreto_interno:-000}"
if [ "$code_secreto_interno" = "404" ]; then
    check "secreto/decode.json no accesible (interno)" 0
else
    check "secreto/decode.json no accesible (interno)" 1 "status=$code_secreto_interno (deberia ser 404)"
fi

# 5. secreto/decode.json NO debe ser accesible por HTTP (publico)
code_secreto_publico=$("${CURL_PUBLICO[@]}" -o /dev/null -w '%{http_code}' "$PUBLIC_URL/secreto/decode.json" 2>/dev/null)
code_secreto_publico="${code_secreto_publico:-000}"
if [ "$code_secreto_publico" = "404" ]; then
    check "secreto/decode.json no accesible (publico)" 0
else
    check "secreto/decode.json no accesible (publico)" 1 "status=$code_secreto_publico (deberia ser 404)"
fi

# 6. Base de datos existe y el directorio es escribible por el contenedor
db_check=$(ssh "$SSH_HOST" "test -f $REMOTE_DIR/data/respuestas.db && test -w $REMOTE_DIR/data && echo ok || echo falla" 2>&1)
if [ "$db_check" = "ok" ]; then
    check "data/respuestas.db existe y es escribible" 0
else
    check "data/respuestas.db existe y es escribible" 1 "$db_check"
fi

# 7. Certificado TLS: dias hasta expirar
dias_cert=$(ssh "$SSH_HOST" "
    fecha_fin=\$(openssl x509 -enddate -noout -in /etc/letsencrypt/live/churn-test.ecticsoft.com/fullchain.pem 2>/dev/null | cut -d= -f2)
    if [ -z \"\$fecha_fin\" ]; then echo 'error'; exit; fi
    epoch_fin=\$(date -d \"\$fecha_fin\" +%s)
    epoch_hoy=\$(date +%s)
    echo \$(( (epoch_fin - epoch_hoy) / 86400 ))
" 2>&1)
if [[ "$dias_cert" =~ ^[0-9]+$ ]] && [ "$dias_cert" -gt 14 ]; then
    check "certificado TLS valido por mas de 14 dias ($dias_cert dias restantes)" 0
else
    check "certificado TLS valido por mas de 14 dias" 1 "dias_restantes=$dias_cert"
fi

echo
if [ "$FALLOS" -eq 0 ]; then
    echo "=== TODO OK (7/7) ==="
    exit 0
else
    echo "=== $FALLOS chequeo(s) fallaron ==="
    exit 1
fi
