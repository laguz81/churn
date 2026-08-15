# Despliegue — Panel de evaluación ciega

Servidor: `dev.ecticsoft` (72.62.101.24), acceso root vía SSH (config en
`~/.ssh/config` del usuario).

Directorio en el servidor: `/opt/panel-evaluacion/` — sigue la misma
convención que el resto de servicios del servidor (`/opt/<app>/docker-compose.yml`,
ver `/opt/engram`, `/opt/n8n`, `/opt/platform-ia`).

**Para publicar cambios, reiniciar o verificar salud, usar los scripts de
`deploy/`** (`./deploy/publicar.sh`, `./deploy/reiniciar.sh`,
`./deploy/health.sh` — ver `deploy/README.md`). El resto de este documento
describe CÓMO se armó el despliegue la primera vez (para poder
reproducirlo desde cero si hace falta); para el uso día a día no hace
falta repetir estos pasos a mano.

## Estado del entorno del servidor (verificado antes de instalar nada)

- Docker 29.5.3 / Compose v5.1.3 ya instalados.
- nginx ya corre como reverse proxy para varios subdominios de `ecticsoft.com`
  (`sites-enabled/`), con certificados Let's Encrypt individuales por
  subdominio en `/etc/letsencrypt/live/<dominio>/`.
- **Puerto 8000 (host) ya ocupado** por el contenedor `platform-ai`
  (`127.0.0.1:8000`). Por eso `panel_evaluacion` usa el puerto **8090** en
  este servidor, no 8000.
- Todos los backends existentes están en `127.0.0.1` (loopback), nunca en
  `0.0.0.0` — nginx es el único proceso que escucha en `0.0.0.0:80/443`. Se
  siguió la misma convención.

## Archivos: dos docker-compose distintos, a propósito

- `docker-compose.yml` — para desarrollo local (puerto 8000, sin
  restricción de host_ip). No se usa en el servidor.
- `docker-compose.prod.yml` — **archivo completo independiente**, NO un
  override parcial. Puerto `127.0.0.1:8090:8000`.

**Por qué no es un override**: Docker Compose concatena listas (`ports`,
`volumes`, etc.) entre archivos con `-f a.yml -f b.yml`, no las reemplaza.
Un primer intento con `docker-compose.prod.yml` conteniendo solo la clave
`ports` sobrescrita produjo AMBOS mappings a la vez (`8000:8000` Y
`127.0.0.1:8090:8000`), y el intento de bind en el puerto 8000 (ya
ocupado) hizo fallar el `docker compose up` completo. Solución: el archivo
de producción repite toda la configuración del servicio y se usa solo con
`-f docker-compose.prod.yml` (sin el archivo base).

## Qué se copió y cómo (nunca vía `git clone` en el servidor — copia directa)

```
scp app.py db.py preparar_evaluacion.py exportar_resultados.py \
    requirements.txt Dockerfile .dockerignore \
    docker-compose.yml docker-compose.prod.yml README.md \
    dev.ecticsoft:/opt/panel-evaluacion/
scp -r templates static dev.ecticsoft:/opt/panel-evaluacion/
scp -r datos dev.ecticsoft:/opt/panel-evaluacion/
scp secreto/decode.json dev.ecticsoft:/opt/panel-evaluacion/secreto/
```

`datos/` (evaluadores.json + casos.json, generados por
`preparar_evaluacion.py`) y `secreto/decode.json` se copiaron por
separado del código — nunca están en el repo, nunca se copian dentro de
la imagen Docker (el `Dockerfile` solo hace `COPY app.py db.py
templates static`).

**Permisos aplicados en el servidor** (todo bajo `root`, servidor de un
solo administrador):

```
chmod 700 /opt/panel-evaluacion/secreto
chmod 600 /opt/panel-evaluacion/secreto/decode.json
chmod 700 /opt/panel-evaluacion/data      # volumen de la base SQLite
```

`secreto/` se monta `:ro` (solo lectura) en el contenedor — ver
`docker-compose.prod.yml`. Nunca se referencia en el `Dockerfile`.

## Levantar / actualizar el contenedor

```bash
ssh dev.ecticsoft
cd /opt/panel-evaluacion
docker compose -f docker-compose.prod.yml up -d --build
```

Para actualizar código: repetir los `scp` de arriba (solo los archivos
que cambiaron) y volver a correr `up -d --build`. La base de datos
(`data/respuestas.db`) y los datos del panel (`datos/`, `secreto/`) no se
tocan al reconstruir la imagen — persisten porque son volúmenes bind, no
parte de la imagen.

## Reverse proxy + HTTPS para `churn-test.ecticsoft.com`

**COMPLETADO 2026-08-14.**

DNS: el servidor ya tenía un token de Cloudflare provisionado en
`/etc/letsencrypt/cloudflare.ini` (para el plugin `certbot-dns-cloudflare`,
instalado pero no usado aquí). Se verificó válido vía
`GET /client/v4/user/tokens/verify` y se usó para crear el registro A
directamente por API (`POST /zones/{zone_id}/dns_records`), sin necesidad
de instalar un CLI dedicado:

```bash
ZONE=a01492ac1f7eb3d5fd6e49655262ebf4   # ecticsoft.com
TOKEN=$(grep dns_cloudflare_api_token /etc/letsencrypt/cloudflare.ini | cut -d"=" -f2 | tr -d " ")
curl -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE/dns_records" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  --data '{"type":"A","name":"churn-test.ecticsoft.com","content":"72.62.101.24","ttl":1,"proxied":true}'
```

`proxied: true` para igualar la convención de todos los demás subdominios
del servidor (todos detrás del proxy de Cloudflare).

Certificado: `certbot certonly --nginx -d churn-test.ecticsoft.com
--non-interactive --agree-tos --cert-name churn-test.ecticsoft.com`,
reutilizando la cuenta ACME ya registrada en el servidor. Funcionó pese
al proxy de Cloudflare (mismo método `authenticator=nginx` que usan los
certificados hermanos) — no hizo falta DNS-01 pese a tener el plugin
disponible.

Config de nginx en `/etc/nginx/sites-available/churn-test` (mismo patrón
que los demás sitios del servidor):

```nginx
server {
    listen 80;
    server_name churn-test.ecticsoft.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name churn-test.ecticsoft.com;

    ssl_certificate /etc/letsencrypt/live/churn-test.ecticsoft.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/churn-test.ecticsoft.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30;
    }
}
```

Nota de proceso: el primer intento de `certbot --nginx` se hizo con un
bloque `server` que YA incluía `ssl_certificate` apuntando a un
certificado que todavía no existía — nginx no habría podido levantar esa
config. Se resolvió en dos pasos: (1) desplegar primero un bloque HTTP-only
en el puerto 80 (sin sección `ssl`, solo el `proxy_pass`), recargar nginx,
y RECIÉN ahí (2) correr `certbot certonly --nginx` (que usa ese bloque
para el challenge) y desplegar la config HTTPS completa de arriba.

`app.py` ya usa `ProxyFix`, así que respeta `X-Forwarded-Proto`/
`X-Forwarded-Host` sin configuración adicional — confirmado: los
redirects de la app salen como `https://churn-test.ecticsoft.com/...`
correctamente detrás del proxy.

Verificado end-to-end tras el despliegue de HTTPS: `curl` desde el
servidor (OpenSSL, HTTP/2 vía Cloudflare) y navegación real en Chrome,
ambos contra `https://churn-test.ecticsoft.com/e/<token>/`. Un error
`schannel: CRYPT_E_NO_REVOCATION_CHECK` apareció solo en curl.exe de
Windows (verificación de revocación de un certificado recién emitido) —
no es un problema del servidor, descartado comparando contra curl del
servidor y Chrome real, ambos exitosos.

## Verificación end-to-end realizada (2026-08-14, contra 127.0.0.1:8090 en el servidor, con el token de prueba)

- Recorrido completo de los 15 casos vía POST real (confirmado en los
  logs de gunicorn del contenedor: 15/15 con status 302, ninguno con
  error 500).
- Confirmado en SQLite directamente: 15 filas para el token de prueba,
  todas con `es_prueba=1`.
- `gracias` aparece correctamente tras el caso 15; un intento posterior
  de volver a `/caso/1` redirige a `gracias` (no se puede recalificar).
- Reinicio del contenedor (`docker compose restart`): las 15 filas
  siguen presentes después — persistencia confirmada.
- `secreto/decode.json` no accesible por ninguna ruta HTTP probada
  (`/secreto/decode.json`, `/app/secreto/decode.json`, intento de path
  traversal) — 404 en todos los casos, página genérica de "no encontrado"
  (nunca el listado ni el contenido del archivo).
- `/static/` y `/templates/` no listan directorio (404, página genérica).
- `exportar_resultados.py` excluye las filas de prueba por diseño
  (`WHERE es_prueba = 0`); no fue necesario borrar nada de la base para
  aislarlas, la exclusión ya es estructural.

## Estado

Despliegue completo. `https://churn-test.ecticsoft.com/e/<token>/` sirve
el panel real para los 3 evaluadores + 1 token de prueba (generados el
2026-08-14 con `--evaluadores 3`, semillas frescas — ver el log de esa
corrida para los tokens exactos, no se repiten aquí).

Si se vuelve a desplegar desde cero: los tokens/`datos/`/`secreto/` no
están en git (por diseño, ver `.gitignore`); hay que regenerarlos con
`preparar_evaluacion.py` y copiarlos al servidor de nuevo tal como se
describe arriba.
