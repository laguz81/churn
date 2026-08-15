# deploy/

Scripts para publicar, reiniciar y comprobar la salud del panel en
`dev.ecticsoft` (`/opt/panel-evaluacion`). Se ejecutan desde esta carpeta
en la máquina local (necesitan el alias SSH `dev.ecticsoft` ya
configurado en `~/.ssh/config`, igual que el resto del despliegue — ver
`../DESPLIEGUE.md`).

```
deploy/
  config.sh      # variables compartidas (host, ruta remota, dominio). No se ejecuta directo.
  publicar.sh    # copia el codigo al servidor + docker compose up -d --build + health.sh
  reiniciar.sh   # docker compose restart (sin rebuild) + health.sh
  health.sh      # 7 chequeos, exit 0 si todos pasan, exit 1 si alguno falla
```

## Uso

```bash
./deploy/publicar.sh     # despues de cambiar app.py, db.py, templates/, etc.
./deploy/reiniciar.sh    # reinicio rapido sin rebuild, si algo se ve raro
./deploy/health.sh       # solo verificar, no cambia nada
```

## Qué NO hace `publicar.sh`

Nunca copia `datos/`, `secreto/` ni `data/`. Esos no son código:

- `datos/` y `secreto/` los genera `preparar_evaluacion.py` (asignación
  A/B y desciframiento etiqueta→fuente de la corrida vigente en el
  servidor). Sobrescribirlos por accidente invalidaría un estudio en
  curso.
- `data/` es la base SQLite con las calificaciones ya recibidas.

Si hace falta regenerar tokens/asignación, correr `preparar_evaluacion.py`
explícitamente y copiar el resultado a mano (ver `DESPLIEGUE.md`), nunca
vía estos scripts.

## Qué revisa `health.sh`

1. El contenedor está corriendo (`docker inspect`).
2. El puerto interno (`127.0.0.1:8090` en el servidor) responde con la
   página propia de la app, no un puerto muerto.
3. La URL pública (`https://churn-test.ecticsoft.com`) responde con la
   página propia — confirma DNS + Cloudflare + nginx + certificado, todo
   junto, no solo el contenedor.
4-5. `secreto/decode.json` da 404 tanto interno como público — regresión
   del chequeo de seguridad que se hizo a mano durante el despliegue.
6. `data/respuestas.db` existe y el directorio es escribible.
7. El certificado TLS tiene más de 14 días antes de vencer (aviso
   temprano; certbot ya tiene renovación automática, esto es una
   segunda verificación).

Cada chequeo se corre aunque otro haya fallado (no se corta a la
primera), para tener el panorama completo de una sola pasada.

## Nota sobre Windows / curl

`curl.exe` en Windows usa el backend TLS `schannel`, que a veces falla
contra un certificado recién emitido con
`CRYPT_E_NO_REVOCATION_CHECK` (verificación de revocación estricta —
confirmado que no es un problema real del sitio, comparado contra curl
del servidor y Chrome real). `config.sh` detecta el backend de `curl -V`
y agrega `--ssl-no-revoke` solo si hace falta (esa flag no existe en curl
con backend OpenSSL, así que no se agrega en Linux/Mac).
