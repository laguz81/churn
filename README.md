# Churn — Sistema agéntico y estudio ciego IA vs. expertos

> Proyecto de titulación MIAA/UISRAEL — Grupo 9 — comercializadora de licores.
> Repositorio privado.

---

Segunda mitad del proyecto de titulación (BT 18 — RAG multimodal y
orquestación agéntica): un sistema de 4 agentes que genera recomendaciones
de retención de clientes, y una aplicación web de evaluación ciega A/B
para compararlas contra las de un experto humano. La parte de detección de
churn / segmentación RFM (K-means, calibración de ventanas) vive en un
repositorio y directorio separados
(`titulacion/scripts/` en Google Drive) y no forma parte de este repo.

---

## Componentes

| Carpeta | Qué es | README |
|---|---|---|
| `camino_b/` | Pipeline de 4 agentes (blackboard, adaptado de ARAG) que genera las 15 recomendaciones del sistema | [`camino_b/README.md`](camino_b/README.md) |
| `panel_evaluacion/` | App Flask de evaluación ciega A/B (sistema vs. experto humano EH2), desplegada en `dev.ecticsoft` | [`panel_evaluacion/README.md`](panel_evaluacion/README.md) |

`panel_evaluacion/` es un proyecto independiente (carpeta hermana, no
depende de `camino_b/` en tiempo de ejecución) que consume el CSV
congelado que produce `camino_b/` como uno de sus dos insumos de
contenido.

## Estructura del repositorio

```
churn/
├── camino_b/                 # Pipeline de 4 agentes (perfilador, verificador, sintetizador, generador)
│   ├── agentes.py             #   Logica de los 4 agentes + redes de seguridad
│   ├── pipeline.py            #   Orquestador end-to-end sobre los 15 casos
│   ├── validador.py           #   Validacion programatica de forma/estilo del Agente 4
│   ├── indexador.py           #   Construye los indices FAISS (o fallback numpy) del corpus
│   ├── prompts/                #   Prompts versionados de cada agente (nunca inline en Python)
│   ├── tests/                  #   Smoke tests (no requieren OPENAI_API_KEY salvo pipeline.py)
│   └── resultados/             #   Salidas de cada corrida (gitignored)
└── panel_evaluacion/          # App Flask de evaluacion ciega A/B
    ├── app.py                  #   Rutas, logica de bloqueo de recalificacion, no-leak
    ├── db.py                   #   SQLite (stdlib), una fila por evento de envio
    ├── preparar_evaluacion.py  #   Genera tokens, asignacion A/B, contenido
    ├── exportar_resultados.py  #   calificaciones.csv / comentarios.csv
    ├── templates/               #   Jinja2 (server-rendered, sin JS de terceros)
    ├── deploy/                  #   publicar.sh / reiniciar.sh / health.sh
    └── DESPLIEGUE.md            #   Como se armo el despliegue en dev.ecticsoft, paso a paso
```

## Despliegue

`panel_evaluacion` está desplegado en `dev.ecticsoft` (`/opt/panel-evaluacion/`),
público en `https://churn-test.ecticsoft.com`. Ver
[`panel_evaluacion/DESPLIEGUE.md`](panel_evaluacion/DESPLIEGUE.md) para
el detalle de cómo se armó, y [`panel_evaluacion/deploy/README.md`](panel_evaluacion/deploy/README.md)
para el uso día a día:

```bash
cd panel_evaluacion
./deploy/publicar.sh     # publicar cambios de codigo
./deploy/reiniciar.sh    # reinicio rapido sin rebuild
./deploy/health.sh       # verificar salud sin cambiar nada
```

`camino_b` no está desplegado — se corre localmente/manualmente para
generar el CSV congelado que consume `panel_evaluacion`.

## Convenciones

- **Ramas:** `main` (estable) y `dev` (integración — publicamos siempre
  desde acá). Todo cambio entra por una rama `feature/<nombre-corto>`
  con PR hacia `dev` (`--base dev`), nunca commit directo a `dev` o `main`.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, etc.), sin atribución de IA en el mensaje.
- **Secretos:** `camino_b/.env` (API key de OpenAI) y
  `panel_evaluacion/secreto/` (desciframiento etiqueta→fuente) nunca se
  commitean ni se copian a una imagen Docker — ver `.gitignore` de cada
  subcarpeta y `panel_evaluacion/DESPLIEGUE.md`.
- **Reproducibilidad:** `temperature=0`, semilla fija (42) en todas las
  corridas de `camino_b`; prompts versionados como archivos `.md`
  independientes del código.

## Licencia

Repositorio privado, uso interno del equipo de titulación (Grupo 9,
MIAA/UISRAEL). Sin licencia de distribución pública.
