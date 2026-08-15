# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Sin versionado semántico todavía (proyecto de titulación, no un paquete
distribuido) — las entradas se agrupan por fecha.

## [Sin publicar] — 2026-08-14

### Camino B — pipeline de 4 agentes

#### Added
- Mudanza del pipeline de 4 agentes desde `titulacion/scripts/camino_b`
  (Google Drive, lento) a `camino_b/` en este repositorio.
- Acción 4 ("Seguimiento ligero") agregada al catálogo de acciones, para
  clientes bajo el umbral de $500 de compra anual — cierra un vacío entre
  la política formal documentada y la práctica real de los expertos.
- Flag `--casos` en `pipeline.py` para correr un subconjunto acotado de
  casos (validación de formato antes de una corrida completa).
- Red de seguridad en código: detecta cuando el Agente 2 (verificador)
  aprueba a la vez dos acciones cuyas condiciones de uso se excluyen
  mutuamente sobre el mismo umbral, y fuerza `revision_manual=True` en
  vez de resolver el empate en silencio.
- Segunda red de seguridad: compara el veredicto del Agente 2 contra el
  monto real del caso (dato conocido, no inferido por el LLM) — atrapa
  casos donde el modelo se equivoca de forma consistente, sin empate ni
  contradicción textual.
- Botón/paso de generación libre de citar cifras del perfil del cliente
  (días sin comprar, número de compras anteriores) cuando resulta natural,
  igualando el registro observado en el experto humano de referencia.

#### Fixed
- El prompt del verificador se autocontradecía sobre el umbral de $500 en
  casos límite; reforzado para fijar una sola determinación consistente
  por respuesta.
- Repetición de plantilla: 9/15 recomendaciones salían idénticas palabra
  por palabra, rompiendo el cegado del panel. Nueva validación a nivel de
  corrida completa (no por caso) que marca la corrida inválida si algún
  campo se repite más de lo esperable.
- Registro de vendedor demasiado formal ("Es crucial contactar...");
  ampliada la lista de palabras prohibidas y forzado un plazo concreto
  (número + unidad) en vez de expresiones vagas.
- Punto final al final de cada campo: el LLM no lo evitaba de forma
  confiable vía instrucción sola (agotaba reintentos); se recorta ahora de
  forma determinística en código antes de validar.
- Campo `accion` 100% separable por longitud del experto humano (7-9
  palabras vs. 1-3): redefinido como canal/gesto corto (máx. 4 palabras),
  no una descripción completa.
- Primer intento de permitir citar cifras del perfil sobrecorrigió a
  100% de los casos (el experto humano lo hace en 40%); reformulado como
  excepción, no como comportamiento por defecto. `justificacion` también
  tenía una densidad visual consistentemente mayor que la del experto;
  acotada a un rango de 8–16 palabras.
- Tipo ortográfico en fixtures de test sintéticos (sin impacto en datos
  reales ni en la interfaz).

### Panel de evaluación ciega A/B

#### Added
- Aplicación Flask de un solo propósito: 15 casos, opciones etiquetadas
  solo "A"/"B", acceso por token en la URL (sin login), un caso a la vez,
  sin poder retroceder ni recalificar.
- Escala Likert 1-5 en dos dimensiones (relevancia, viabilidad), anclas
  completas visibles en pantalla, más comentario libre opcional (control
  de fuga del cegado).
- Asignación A/B balanceada (7/8) e independiente por evaluador, con
  semilla propia registrada — reemplaza una clave anterior sesgada
  (sistema=A en 13/15 casos).
- Botón "Reiniciar simulación", restringido en dos capas (plantilla +
  ruta con 403) a tokens marcados como prueba — nunca disponible para un
  evaluador real.

#### Fixed
- Normalización de forma en la capa de presentación (nunca en los CSV
  fuente): punto final, mayúscula inicial, comillas/viñetas residuales,
  espacios, y formato de `plazo` unificados entre ambas fuentes — el
  punto final era, por sí solo, 100% distintivo entre sistema y experto.

### Despliegue

#### Added
- Despliegue en `dev.ecticsoft` (`/opt/panel-evaluacion/`), puerto interno
  8090 en loopback (8000 ya ocupado por otro servicio del servidor).
- DNS + certificado HTTPS para `churn-test.ecticsoft.com` vía la API de
  Cloudflare y `certbot --nginx`, reutilizando credenciales ya
  provisionadas en el servidor.
- `panel_evaluacion/deploy/`: `publicar.sh`, `reiniciar.sh`, `health.sh`
  (7 chequeos: contenedor, puerto interno, URL pública, `secreto/`
  inaccesible por HTTP, base de datos escribible, vigencia del
  certificado TLS).
- `DESPLIEGUE.md` documentando el proceso completo, reproducible desde
  cero.

#### Fixed
- Override parcial de `docker-compose` concatenaba mappings de puerto en
  vez de reemplazarlos (Compose no reemplaza listas entre `-f`); resuelto
  con un `docker-compose.prod.yml` autocontenido.
