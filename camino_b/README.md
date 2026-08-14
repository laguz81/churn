# Camino B — Sistema de 4 agentes (blackboard) para recomendaciones de retencion

Implementacion adaptada de ARAG (Maragheh et al. 2025, ACM SIGIR,
arXiv:2506.21931): 4 agentes especializados que comparten un blackboard
(estado compartido, serializado a `trazas_agentes.json`) en vez de un
pipeline RAG plano de un solo paso.

## Arquitectura

```
casos_15_perfil.csv
        |
        v
+-------------------+      (no toca el corpus)
| Agente 1          |
| PERFILADOR        |  -> resumen_perfil (lenguaje natural)
+-------------------+
        |
        v
+-------------------+      FAISS: acciones.index (3 acciones)
| Agente 2          |      -> si gana Accion 3: FAISS promociones.index (10)
| VERIFICADOR       |  -> scores 0-1 por opcion + descarte por theta (0.6)
+-------------------+
        |
        v
+-------------------+
| Agente 3          |  -> contexto_condensado (solo lo que paso theta)
| SINTETIZADOR      |
+-------------------+
        |
        v
+-------------------+
| Agente 4          |  -> recomendacion / accion / plazo / justificacion
| ORDENADOR/GENERADOR| -> valida formato, reintenta hasta 3 veces
+-------------------+
```

Cada caso produce una fila en `resultados/recomendaciones_ia.csv`, una
entrada completa en `resultados/trazas_agentes.json` (blackboard integro:
que vio y que devolvio cada agente, incluyendo scores y descartes) y una
linea en `resultados/run_log.jsonl` (modelo, temperatura, seed,
timestamp, acciones/promociones descartadas por umbral).

## Por que MiniLM multilingue y no `all-MiniLM-L6-v2`

El usuario referencio "MiniLM-L6-v2 o similar multilingue" como punto de
partida, pero `all-MiniLM-L6-v2` esta entrenado casi exclusivamente con
texto en ingles. El corpus (`acciones_retencion_1.md`,
`politica_descuentos_1.md`, `promociones_vigentes_1.md`) y las consultas
(resumen de perfil generado por el Agente 1) estan en espanol, por lo que
se uso `paraphrase-multilingual-MiniLM-L12-v2`: misma familia
arquitectonica MiniLM (rapido, correlativo en tamano/latencia con
L6-v2), pero entrenado en 50+ idiomas incluido espanol, lo que evita la
degradacion de calidad de embeddings que produciria usar la variante
solo-ingles sobre texto castellano.

## Chunking

Cada documento markdown se divide por encabezados `## ` de nivel 2:

- `acciones_retencion_1.md` -> 3 chunks (`accion_1`, `accion_2`,
  `accion_3`), uno por cada `## Accion N: ...`. Se descartan las
  secciones de procedencia y la lista de "acciones que nunca deben
  recomendarse" (son restricciones globales, no candidatas de
  recuperacion).
- `promociones_vigentes_1.md` -> 10 chunks (`promocion_1` .. `promocion_10`),
  uno por cada `## Promocion N: ...`. Se descartan procedencia, nota
  metodologica y notas adicionales.
- `politica_descuentos_1.md` -> se chunkea por seccion tematica
  (descuentos autorizados, limite maximo, condiciones de credito, etc.)
  y se indexa por completitud/trazabilidad del corpus, pero ningun
  agente lo consulta por similitud en la version actual del pipeline
  (las restricciones de politica no son "opciones a recuperar", son
  reglas fijas). Queda disponible para extender el sistema si se decide
  usarlo como contexto de validacion en el futuro.

Se eligio granularidad "por seccion completa" (no por parrafo ni por
frase) a proposito: el Agente 2 necesita el bloque completo de
canal/plazo/condicion de uso/cuando-NO-usar para poder puntuar relevancia
de forma responsable; fragmentar mas fino perderia ese contexto
estructural.

## Reindexar

El corpus va a cambiar pronto (posible Accion 4 pendiente de una
decision de politica de negocio). Reindexar es una sola linea:

```
python indexador.py
```

Esto reconstruye `indice/acciones.index`, `indice/promociones.index` e
`indice/politica.index` (o su equivalente `.npy` si se esta usando el
fallback numpy) desde cero, leyendo unicamente los 3 archivos de la
whitelist en `config.CORPUS_WHITELIST`.

## Umbral de relevancia (theta) y regla de jerarquia del Agente 2

Ver el docstring de `agentes.py` para el detalle completo. Resumen: se
puntuan las 3 acciones, se descartan las que no llegan a `theta` (0.6
por default, `config.THETA_RELEVANCIA`), la accion ganadora es la de
mayor score entre las que si superan `theta`. Solo si la accion ganadora
es `accion_3` se recuperan y puntuan las 10 promociones con la misma
regla de umbral.

## Backend de similitud: FAISS con fallback numpy

`vectorstore.py` intenta usar `faiss-cpu` (`IndexFlatIP` sobre vectores
normalizados = similitud coseno exacta). Si faiss no esta disponible en
el interprete, cae automaticamente a busqueda por fuerza bruta con numpy
(mismo resultado exacto, sin perdida de calidad; con ~15 chunks totales
en el corpus la diferencia de rendimiento es irrelevante). En este
entorno (Windows, Python 3.13.5) **faiss-cpu 1.15.0 instalo y funciono
sin problemas**, asi que el backend activo es FAISS — ver la seccion de
smoke tests para la confirmacion empirica.

## Prompts versionados

Cada agente lee su prompt desde un archivo propio bajo `prompts/`:

- `prompts/perfilador.md`
- `prompts/verificador.md` (reutilizado tanto para puntuar acciones como
  promociones, ya que la tarea de scoring es identica en ambos casos)
- `prompts/sintetizador.md`
- `prompts/generador.md`

Ningun prompt esta inline como string literal en Python: cualquier
cambio de prompt es visible en el diff del `.md` correspondiente,
independiente de cambios de codigo.

## Configuracion (`config.py`)

Todo lo variable entre corridas vive en un solo modulo: `THETA_RELEVANCIA`,
`OPENAI_MODEL` (via env var, default pinneado a un snapshot con fecha),
`LLM_SEED` (default 42), limites de palabras por campo, lista de
palabras prohibidas, y todas las rutas de entrada/salida. Ver
`dotenv_ejemplo.txt` para las variables de entorno soportadas.

**IMPORTANTE sobre el modelo:** `config.DEFAULT_OPENAI_MODEL` esta
fijado a un snapshot con fecha (`gpt-4o-2024-08-06`) en vez de un alias
flotante como `"gpt-4o"`, para evitar que el comportamiento del pipeline
cambie silenciosamente si OpenAI actualiza el modelo detras del alias.
**Confirmar que ese snapshot siga vigente en la cuenta de OpenAI antes de
correr el pipeline en produccion**; si fue deprecado, fijar
`OPENAI_MODEL` a un snapshot vigente via variable de entorno.

## Que NO hace este pipeline (a proposito)

- `indexador.py`, `corpus.py` y todo el codigo de agentes/pipeline nunca
  leen `casos_15_expertos.csv` ni `PRIVADO_mapa_id.csv`. Esos dos nombres
  de archivo no aparecen en ninguna ruta de codigo ejecutable del
  proyecto (solo en comentarios/documentacion, como recordatorio).
- `corpus.py` nunca hace `os.listdir`/glob sobre `corpus_1/`: toda
  lectura pasa por la whitelist explicita `config.CORPUS_WHITELIST`.
- **No se ejecuto el pipeline end-to-end sobre los 15 casos reales.**
  `pipeline.py` esta completo y listo para correr, pero la generacion
  real esta pausada hasta que se resuelva una pregunta de politica de
  negocio pendiente (indicacion explicita del usuario). Los unicos
  smoke tests que se corrieron son los del indexador (con el corpus
  real, sin LLM) y los del validador (con ejemplos sinteticos
  inventados, no derivados de `casos_15_expertos.csv`).

## Instalacion y smoke tests

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

.venv\Scripts\python indexador.py
.venv\Scripts\python -m tests.test_indexador
.venv\Scripts\python -m tests.test_validador
```

Ver el resultado real de esta corrida (Python 3.13.5, Windows) al final
de este README.
