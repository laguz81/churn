# Panel de evaluacion ciega A/B

Aplicacion web de un solo proposito para el estudio de evaluacion ciega
de la tesis (MIAA/UISRAEL): compara 15 recomendaciones generadas por el
pipeline "Camino B" contra 15 recomendaciones del experto humano EH2,
mostradas sin marcar (solo "A"/"B") a evaluadores humanos.

Proyecto independiente de `camino_b/` (vive como carpeta hermana en el
mismo repositorio, sin tocar su historial de git).

## 1. Preparar la evaluacion (genera tokens, asignacion A/B y contenido)

```bash
cd panel_evaluacion
python preparar_evaluacion.py --evaluadores 3
```

- `--evaluadores N` (por defecto 3, o variable de entorno `NUM_EVALUADORES`):
  numero de evaluadores reales. Siempre se genera ademas UN token adicional
  de PRUEBA (`es_prueba: true`).
- Rutas de los CSV de origen y de las carpetas de salida son parametrizables
  por CLI (`--perfil-csv`, `--sistema-csv`, `--expertos-csv`, `--datos-dir`,
  `--secreto-dir`, `--eh1-referencia`, `--base-url`) o por variable de
  entorno equivalente. Los valores por defecto apuntan a las rutas reales
  del proyecto de tesis.
- Genera:
  - `datos/evaluadores.json` (NO secreto): que casos ve cada token, id de
    evaluador, si es de prueba. **No** contiene a que fuente corresponde
    cada etiqueta A/B.
  - `datos/casos.json` (NO secreto): contenido textual completo de los 15
    casos (perfil + version del sistema + version de EH2).
  - `secreto/decode.json` (**SECRETO**): para cada token y cada caso, que
    etiqueta (A/B) corresponde a que fuente (`sistema`/`eh2`). Es el unico
    archivo donde vive ese mapeo.
  - `eh1_referencia.csv`: copia de las filas EH1 del corpus, preservada para
    un analisis futuro de variabilidad entre expertos que **no** es parte
    de esta app.
- Imprime al final un resumen en texto plano con la URL de cada evaluador
  (marcando claramente cual es la de PRUEBA).

Cada token tiene su propia semilla aleatoria (impresa en el resumen) que
determina una asignacion A/B balanceada (7 u 8 de los 15 casos con el
sistema como "A") e independiente de la de los demas tokens.

## 2. Levantar la app

### Local (desarrollo rapido, sin Docker)

```bash
pip install -r requirements.txt
python app.py
```

Sirve en `http://127.0.0.1:5000`. Las URLs de evaluador son
`http://127.0.0.1:5000/e/<token>`.

### Docker (despliegue)

```bash
docker compose build
docker compose up -d
```

- Expone el puerto interno `8000` en el host (ver `docker-compose.yml`).
- Monta `./datos` (contenido no secreto), `./secreto` (solo lectura) y
  `./data` (base SQLite persistente) como volumenes; ninguno de los tres
  se copia dentro de la imagen.
- Detras de un reverse proxy que termine TLS (`churn-test.ecticsoft.com`),
  la app respeta `X-Forwarded-Proto`/`X-Forwarded-Host` via
  `werkzeug.middleware.proxy_fix.ProxyFix`.
- Para bajarlo: `docker compose down`.

**IMPORTANTE**: `secreto/decode.json` nunca debe commitearse a git ni
copiarse dentro de la imagen Docker. El `Dockerfile` nunca lo referencia
con `COPY`; solo llega al contenedor por el volumen `:ro` de
`docker-compose.yml`. `.gitignore` ya excluye `panel_evaluacion/secreto/`.

## 3. Exportar resultados para el analisis

```bash
python exportar_resultados.py --db data/respuestas.db --salida .
```

Genera:
- `calificaciones.csv` (formato largo): `evaluador, id_caso, etiqueta, criterio, puntaje`.
  Cada envio de caso se expande a 4 filas (`{A,B} x {relevancia,viabilidad}`).
- `comentarios.csv`: `evaluador, id_caso, comentario, timestamp` (solo filas
  con comentario real).

Las respuestas del token de PRUEBA (`es_prueba=1`) quedan **siempre**
excluidas de ambos archivos.

Para decodificar que etiqueta (A/B) corresponde a que fuente por caso y
por evaluador, usa directamente `secreto/decode.json` -- es el unico
archivo de desciframiento, no se duplica en ningun otro lado.

## Estructura

```
panel_evaluacion/
  app.py                   # aplicacion Flask (rutas de evaluacion)
  db.py                    # acceso SQLite compartido
  preparar_evaluacion.py   # genera tokens + asignacion A/B + contenido
  exportar_resultados.py   # exporta calificaciones.csv / comentarios.csv
  templates/                # HTML Jinja2 server-side, sin JS de terceros
  requirements.txt
  Dockerfile
  docker-compose.yml
  eh1_referencia.csv        # generado por preparar_evaluacion.py
  datos/                    # generado, NO secreto (gitignored por limpieza)
  secreto/                  # generado, SECRETO (gitignored, nunca en git/imagen)
  data/                     # generado, base SQLite (gitignored)
```

## Que NO hace esta app

- Sin login, sin registro, sin Keycloak, sin roles.
- Sin edicion de las recomendaciones mostradas (solo lectura).
- Sin una tercera dimension Likert (solo relevancia y viabilidad).
- Nunca lee, copia ni referencia `PRIVADO_mapa_id.csv`.
- Nunca expone en las respuestas HTTP de cara al evaluador las palabras
  "sistema", "IA", "EH1", "EH2", "experto" ni similares; solo "A"/"B".
