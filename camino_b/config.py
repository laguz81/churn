"""
Configuracion centralizada del pipeline de 4 agentes (Camino B).

Todo lo que un experimento podria necesitar variar (theta, modelo, seed,
rutas, limites de palabras, palabras prohibidas) vive aqui, no disperso
en el codigo de los agentes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Carga camino_b/.env si existe (no versionado). No sobreescribe
    # variables de entorno ya definidas en el sistema.
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover - python-dotenv es una dependencia
    # declarada en requirements.txt; si por algun motivo no esta instalada,
    # el pipeline sigue funcionando con variables de entorno del sistema.
    pass

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------

CAMINO_B_DIR = Path(__file__).resolve().parent

# El codigo de camino_b vive en C:\ecticsoft\churn\camino_b, pero el corpus
# y el resto del proyecto de titulacion se quedaron en Google Drive (G:).
# No se puede derivar CORPUS_DIR subiendo niveles desde CAMINO_B_DIR porque
# ya no comparten arbol de directorios. Ruta explicita, overrideable por
# env var para no romper si alguien mas clona esto en otra maquina.
TITULACION_DIR = Path(
    os.environ.get(
        "TITULACION_DIR",
        r"G:\Mi unidad\maestria\articulo_proyecto\plan-defensa\titulacion",
    )
)
CORPUS_DIR = Path(os.environ.get("CORPUS_DIR", str(TITULACION_DIR / "corpus_1")))

INDICE_DIR = CAMINO_B_DIR / "indice"
RESULTADOS_DIR = CAMINO_B_DIR / "resultados"
PROMPTS_DIR = CAMINO_B_DIR / "prompts"

# ---------------------------------------------------------------------------
# Whitelist explicita de archivos del corpus que el indexador puede leer.
#
# IMPORTANTE: nunca reemplazar esto por un glob/listdir sobre CORPUS_DIR.
# casos_15_expertos.csv y PRIVADO_mapa_id.csv NO deben aparecer aqui jamas.
# ---------------------------------------------------------------------------

CORPUS_WHITELIST = {
    "acciones": CORPUS_DIR / "acciones_retencion_1.md",
    "acciones_2": CORPUS_DIR / "acciones_retencion_2.md",
    "politica": CORPUS_DIR / "politica_descuentos_1.md",
    "promociones": CORPUS_DIR / "promociones_vigentes_1.md",
}

# Claves de CORPUS_WHITELIST cuyas secciones "## Accion N: ..." se combinan
# en un unico indice de acciones de primer nivel. acciones_retencion_2.md
# se agrego 2026-08-14 (Accion 4: Seguimiento ligero, para clientes bajo el
# umbral de compra anual que documenta acciones_retencion_1.md) tras
# detectar que la practica de los expertos por debajo del umbral no estaba
# en el corpus original. Si se agrega una Accion 5 en un archivo nuevo,
# basta con sumar su clave aqui.
CLAVES_ACCIONES = ("acciones", "acciones_2")

# Archivo de entrada seguro para el generador (perfiles RFM, sin datos
# identificables). Este es el UNICO csv de casos que el pipeline puede leer.
CASOS_PERFIL_CSV = CORPUS_DIR / "casos_15_perfil.csv"

# Archivos que el pipeline tiene EXPRESAMENTE PROHIBIDO leer o referenciar
# en cualquier ruta de codigo en tiempo de ejecucion. Se listan aqui solo
# como documentacion / recordatorio, nunca se usan para abrir un archivo.
ARCHIVOS_PROHIBIDOS = (
    "casos_15_expertos.csv",
    "PRIVADO_mapa_id.csv",
)

# ---------------------------------------------------------------------------
# Rutas de salida del indice FAISS (o del fallback numpy)
# ---------------------------------------------------------------------------

INDICE_ACCIONES_PATH = INDICE_DIR / "acciones.index"
INDICE_ACCIONES_META_PATH = INDICE_DIR / "acciones_meta.json"

INDICE_PROMOCIONES_PATH = INDICE_DIR / "promociones.index"
INDICE_PROMOCIONES_META_PATH = INDICE_DIR / "promociones_meta.json"

INDICE_POLITICA_PATH = INDICE_DIR / "politica.index"
INDICE_POLITICA_META_PATH = INDICE_DIR / "politica_meta.json"

# ---------------------------------------------------------------------------
# Modelo de embeddings
# ---------------------------------------------------------------------------

# Se eligio la variante MULTILINGUE en vez de la version en ingles
# (all-MiniLM-L6-v2) porque el corpus y las consultas estan en espanol.
# all-MiniLM-L6-v2 se entrena solo con texto en ingles y su desempeno en
# espanol degrada notablemente frente a la familia multilingue. Ver
# camino_b/README.md para el detalle de esta decision.
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# ---------------------------------------------------------------------------
# LLM (OpenAI)
# ---------------------------------------------------------------------------

# Modelo fijado a un snapshot con fecha (no un alias flotante como "gpt-4o")
# para evitar drift silencioso de comportamiento entre corridas a lo largo
# del ano. CONFIRMAR antes de correr el pipeline en produccion que este
# snapshot sigue vigente en la cuenta de OpenAI utilizada; si fue
# deprecado, actualizar la variable de entorno OPENAI_MODEL o este default.
DEFAULT_OPENAI_MODEL = "gpt-4o-2024-08-06"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

OPENAI_API_KEY_ENV_VAR = "OPENAI_API_KEY"

LLM_TEMPERATURE = 0
LLM_SEED = int(os.environ.get("LLM_SEED", "42"))
LLM_MAX_RETRIES_AGENTE4 = 3

# ---------------------------------------------------------------------------
# Umbral de relevancia (Agente 2 - VERIFICADOR)
# ---------------------------------------------------------------------------

THETA_RELEVANCIA = float(os.environ.get("THETA_RELEVANCIA", "0.6"))

# Umbral de compra anual que Accion 1 y Accion 4 usan como condicion de uso
# ("supera aproximadamente $500 anuales" / "no supera el umbral") en
# acciones_retencion_1.md y acciones_retencion_2.md. Es un HECHO conocido
# del caso de entrada (monetary_usd), no algo que el LLM deba inferir: se
# usa para verificar en codigo que el veredicto del Agente 2 sobre
# accion_1/accion_4 sea consistente con el dato real, sin depender de que
# el LLM haga bien esa comparacion numerica (ver agentes.py,
# _detectar_contradiccion_umbral_objetivo).
UMBRAL_COMPRA_ANUAL = float(os.environ.get("UMBRAL_COMPRA_ANUAL", "500"))

# Cuantas acciones/promociones candidatas trae la busqueda por similitud
# antes de que el Agente 2 las puntue. Con 4 acciones y 10 promociones en
# total, top_k cubre el corpus completo de cada indice.
TOP_K_ACCIONES = 4
TOP_K_PROMOCIONES = 10

# ---------------------------------------------------------------------------
# Validacion del formato de salida (Agente 4)
# ---------------------------------------------------------------------------

LIMITE_PALABRAS_RECOMENDACION = 25
LIMITE_PALABRAS_ACCION = 12
LIMITE_PALABRAS_JUSTIFICACION = 30

# Palabras/frases prohibidas (tono "consultor" / "IA"), coincidencia
# exacta de palabra o frase completa, sin distinguir mayusculas/minusculas.
# Segunda tanda (2026-08-14): el caso 14 de una corrida real decia "Es
# crucial contactar al cliente..." -- registro de informe, no de vendedor
# apurado tomando nota (comparar con el registro llano de los expertos:
# "Hacer un acercamiento via telefonica para verificar estado del
# cliente", "Recuperar cliente, facturacion importante").
PALABRAS_PROHIBIDAS = (
    "optimizar",
    "estrategico",
    "estratégico",
    "sinergia",
    "proactivo",
    "holistico",
    "holístico",
    "clave",
    "robusto",
    "integral",
    "crucial",
    "fundamental",
    "esencial",
    "optimo",
    "óptimo",
    "relevante",
    "significativo",
    "indica que",
    "resulta importante",
    "se recomienda",
    "adecuado",
    "personalizado",
    "experiencia del cliente",
)

# Campos que deben respetar limite de palabras (justificacion y accion no
# llevan numeros de plazo, por eso "plazo" queda fuera de este control).
CAMPOS_SALIDA = ("recomendacion", "accion", "plazo", "justificacion")

# ---------------------------------------------------------------------------
# El campo 'plazo' debe ser una cifra concreta (numero + unidad temporal),
# no una expresion vaga ("en las proximas semanas", "lo antes posible").
# Los expertos humanos usaron valores como "8 dias", "15 dias", "1 mes".
# Rango esperable: 3 dias a 1 mes (30 dias). Fuera de rango o sin numero
# -> falla la validacion, Agente 4 reintenta.
# ---------------------------------------------------------------------------

PLAZO_MIN_DIAS = 3
PLAZO_MAX_DIAS = 30

# ---------------------------------------------------------------------------
# Validacion anti-plantilla (a nivel de CORRIDA completa, no por caso)
# ---------------------------------------------------------------------------

# Si un mismo valor literal de un campo se repite mas de N veces dentro de
# una corrida, el sistema no esta individualizando por cliente -- esta
# aplicando una regla fija con una plantilla de texto alrededor. Encontrado
# empiricamente 2026-08-14: 9/15 'recomendacion' identicas palabra por
# palabra, 11/15 'plazo' identicos. Rompe el cegado del panel (un
# evaluador humano detecta el patron).
#
# Umbral en CONTEO ABSOLUTO (no porcentaje), calibrado para N=15: maximo 3
# repeticiones por campo, excepto 'plazo' que tolera hasta 5 (el
# vocabulario razonable de plazos es chico -- "15 dias" es legitimo en
# varios casos sin que sea plantilla).
#
# Esta verificacion SOLO tiene sentido en la corrida completa de 15 casos:
# con N chico (p.ej. un piloto de --casos 1,2) cualquier reparto 50/50
# dispara el umbral por definicion y el resultado no es interpretable.
# pipeline.py la omite cuando se usa --casos.
MAX_REPETICION_ABSOLUTA = int(os.environ.get("MAX_REPETICION_ABSOLUTA", "3"))
MAX_REPETICION_ABSOLUTA_PLAZO = int(os.environ.get("MAX_REPETICION_ABSOLUTA_PLAZO", "5"))

# ---------------------------------------------------------------------------
# Salidas del pipeline
# ---------------------------------------------------------------------------

RECOMENDACIONES_CSV = RESULTADOS_DIR / "recomendaciones_ia.csv"
TRAZAS_JSON = RESULTADOS_DIR / "trazas_agentes.json"
RUN_LOG_JSONL = RESULTADOS_DIR / "run_log.jsonl"


@dataclass(frozen=True)
class RutasPrompts:
    perfilador: Path = PROMPTS_DIR / "perfilador.md"
    verificador: Path = PROMPTS_DIR / "verificador.md"
    sintetizador: Path = PROMPTS_DIR / "sintetizador.md"
    generador: Path = PROMPTS_DIR / "generador.md"


PROMPTS = RutasPrompts()


def get_openai_api_key() -> str:
    """Devuelve la API key de OpenAI o falla rapido con un mensaje claro.

    No se debe dejar que el cliente de openai reviente con una excepcion
    generica varias capas mas abajo: el fallo debe ser explicito aqui,
    en el punto de entrada del pipeline.
    """
    api_key = os.environ.get(OPENAI_API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"{OPENAI_API_KEY_ENV_VAR} no esta configurada. "
            "Define la variable de entorno antes de correr el pipeline."
        )
    return api_key


def ensure_dirs() -> None:
    INDICE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
