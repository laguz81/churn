#!/usr/bin/env python3
"""
preparar_evaluacion.py

Prepara los materiales de la evaluacion ciega A/B para el panel de
evaluadores humanos:

  - Lee los 3 CSV de origen (perfil de los 15 casos, recomendaciones del
    sistema/IA congeladas de run1_definitiva, y recomendaciones de los
    expertos humanos filtradas a la fuente EH2).
  - Genera un token no adivinable y una semilla aleatoria propia para cada
    evaluador real (evaluador_1..N) mas UN token/semilla adicional de
    PRUEBA (es_prueba=True).
  - Para cada token, calcula una asignacion A/B balanceada e independiente
    (7 u 8 casos con el sistema en "A", el resto en "B"), usando la
    semilla propia de ese token.
  - Escribe dos salidas separadas:
      * datos/evaluadores.json   -> NO secreto (que casos ve cada token,
        id de evaluador, si es de prueba). No contiene la fuente.
      * datos/casos.json         -> NO secreto: contenido textual completo
        de las 15 fichas (perfil + version "sistema" + version "eh2").
        Esto por si solo no revela que vio cada evaluador como A o B,
        eso solo lo sabe secreto/decode.json.
      * secreto/decode.json      -> SECRETO: para cada token y cada caso,
        que etiqueta (A/B) corresponde a que fuente (sistema/eh2). Este
        archivo NUNCA debe copiarse a la imagen Docker ni a git; se monta
        por volumen en tiempo de ejecucion.
  - Exporta ademas eh1_referencia.csv (filas EH1) para un analisis futuro
    de variabilidad entre expertos, que NO es parte de esta app.
  - Imprime al final un resumen en texto plano con las URLs por evaluador.

Nunca lee, copia ni referencia PRIVADO_mapa_id.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import secrets
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas por defecto (parametrizables via CLI o variables de entorno)
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent

DEFAULT_PERFIL_CSV = Path(
    r"G:\Mi unidad\maestria\articulo_proyecto\plan-defensa\titulacion\corpus_1\casos_15_perfil.csv"
)
DEFAULT_SISTEMA_CSV = Path(
    r"C:\ecticsoft\churn\camino_b\resultados\run1_definitiva\recomendaciones_ia.csv"
)
DEFAULT_EXPERTOS_CSV = Path(
    r"G:\Mi unidad\maestria\articulo_proyecto\plan-defensa\titulacion\corpus_1\casos_15_expertos.csv"
)

DEFAULT_DATOS_DIR = PROJECT_DIR / "datos"
DEFAULT_SECRETO_DIR = PROJECT_DIR / "secreto"
DEFAULT_EH1_REF_PATH = PROJECT_DIR / "eh1_referencia.csv"
DEFAULT_BASE_URL = "https://churn-test.ecticsoft.com"

CAMPOS_TEXTO = ("recomendacion", "accion", "plazo", "justificacion")
CAMPOS_PERFIL = ("recency_dias", "frequency", "monetary_usd", "segmento")

FORBIDDEN_FILENAME = "privado_mapa_id.csv"


# ---------------------------------------------------------------------------
# Normalizacion de forma en la capa de presentacion
#
# Aplicada IDENTICAMENTE a sistema y eh2, aqui, al cargar los CSV -- nunca
# se escribe de vuelta a casos_15_expertos.csv ni a recomendaciones_ia.csv,
# que se abren siempre en modo lectura. Motivo: el punto final resulto ser
# una fuga sistematica al 100% entre las dos fuentes (EH2 conserva punto
# final en 2/3 campos de texto en los 15 casos, el sistema en 0/3 -- ver
# revision del panel 2026-08-14). Si un eje delataba de forma perfecta, era
# razonable sospechar que hubiera mas: mayuscula inicial inconsistente,
# comillas/vinetas residuales de una fuente y no de la otra, doble espacio,
# y el acento del campo plazo (EH2 escribe "dias"/"días" mezclado en su CSV
# original, el generador del sistema nunca acentua).
# ---------------------------------------------------------------------------

_PATRON_VINETA_O_GUION_INICIAL = re.compile(r"^\s*[-*••–—]+\s*")
_PATRON_COMILLAS = re.compile(r"[\"'«»‘’“”]")
_PATRON_ESPACIO_ANTES_PUNTUACION = re.compile(r"\s+([,.;:!?])")
_PATRON_ESPACIOS_MULTIPLES = re.compile(r"\s{2,}")


def normalizar_campo_texto(valor: str) -> str:
    """Normaliza un campo de texto libre (recomendacion/accion/justificacion)
    de forma identica sin importar la fuente: sin vineta/guion residual al
    inicio, sin comillas, sin espacio antes de puntuacion, sin espacios
    dobles, sin punto final, con mayuscula inicial forzada."""
    if not valor:
        return valor
    texto = valor.strip()
    texto = _PATRON_VINETA_O_GUION_INICIAL.sub("", texto)
    texto = _PATRON_COMILLAS.sub("", texto)
    texto = _PATRON_ESPACIO_ANTES_PUNTUACION.sub(r"\1", texto)
    texto = _PATRON_ESPACIOS_MULTIPLES.sub(" ", texto)
    texto = texto.strip()
    if texto.endswith("."):
        texto = texto[:-1].rstrip()
    if texto:
        texto = texto[0].upper() + texto[1:]
    return texto


# unidad_singular_o_plural -> (forma singular, forma plural), siempre con
# tilde correcta. Cubre las variantes con y sin tilde que aparecen en el
# corpus real (EH2 escribe "dias" y "días" de forma inconsistente dentro
# de su propio CSV; el sistema nunca acentua).
_UNIDADES_PLAZO = {
    "dia": ("día", "días"), "dias": ("día", "días"),
    "día": ("día", "días"), "días": ("día", "días"),
    "semana": ("semana", "semanas"), "semanas": ("semana", "semanas"),
    "mes": ("mes", "meses"), "meses": ("mes", "meses"),
}
_PATRON_PLAZO = re.compile(r"^\s*(\d+)\s*([A-Za-zÀ-ÿ]+)\s*$")


def normalizar_plazo(valor: str) -> str:
    """Unifica el formato de 'plazo' a 'N unidad' con tilde correcta y
    concordancia singular/plural, sin importar como vino escrito en el
    CSV original (con o sin tilde, con o sin punto final)."""
    if not valor:
        return valor
    texto = valor.strip().rstrip(".")
    m = _PATRON_PLAZO.match(texto)
    if not m:
        return texto
    numero = int(m.group(1))
    par = _UNIDADES_PLAZO.get(m.group(2).lower())
    if par is None:
        return texto
    unidad = par[0] if numero == 1 else par[1]
    return f"{numero} {unidad}"


def normalizar_campos(fila: dict) -> dict:
    return {
        "recomendacion": normalizar_campo_texto(fila["recomendacion"]),
        "accion": normalizar_campo_texto(fila["accion"]),
        "plazo": normalizar_plazo(fila["plazo"]),
        "justificacion": normalizar_campo_texto(fila["justificacion"]),
    }


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------


def _guard_against_privado(path: Path) -> None:
    if path.name.strip().lower() == FORBIDDEN_FILENAME:
        raise RuntimeError(
            f"Ruta rechazada: {path} coincide con el archivo prohibido "
            f"{FORBIDDEN_FILENAME}. Este script nunca debe leer ese archivo."
        )


def normalizar_segmento(valor: str) -> str:
    """'en_riesgo' -> 'En riesgo'. Solo presentacion, el CSV fuente no
    cambia (rfm_segmentado.csv / casos_15_perfil.csv usan guion bajo)."""
    if not valor:
        return valor
    texto = valor.replace("_", " ").strip()
    return texto[0].upper() + texto[1:] if texto else texto


def cargar_perfiles(path: Path) -> dict[int, dict]:
    _guard_against_privado(path)
    perfiles: dict[int, dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            id_caso = int(row["id_caso"])
            perfil = {campo: row[campo] for campo in CAMPOS_PERFIL}
            perfil["segmento"] = normalizar_segmento(perfil["segmento"])
            perfiles[id_caso] = perfil
    return perfiles


def cargar_sistema(path: Path) -> dict[int, dict]:
    _guard_against_privado(path)
    sistema: dict[int, dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            id_caso = int(row["id_caso"])
            sistema[id_caso] = normalizar_campos({campo: row[campo] for campo in CAMPOS_TEXTO})
    return sistema


def cargar_expertos(path: Path) -> tuple[dict[int, dict], list[dict]]:
    """Devuelve (dict EH2 por id_caso, lista de filas crudas EH1)."""
    _guard_against_privado(path)
    eh2: dict[int, dict] = {}
    eh1_filas: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["fuente"].strip().upper() == "EH2":
                id_caso = int(row["id_caso"])
                eh2[id_caso] = normalizar_campos({campo: row[campo] for campo in CAMPOS_TEXTO})
            elif row["fuente"].strip().upper() == "EH1":
                eh1_filas.append(row)
    return eh2, eh1_filas, fieldnames  # type: ignore[return-value]


def escribir_eh1_referencia(eh1_filas: list[dict], fieldnames: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in eh1_filas:
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Asignacion A/B balanceada e independiente por token
# ---------------------------------------------------------------------------


def generar_asignacion(ids_casos: list[int], seed: int) -> dict[int, dict[str, str]]:
    """
    Genera, para un token con la semilla dada, la asignacion A/B por caso.

    Devuelve {id_caso: {"A": "sistema"|"eh2", "B": "sistema"|"eh2"}}.
    Balanceado: 7 u 8 de los 15 casos tienen el sistema como "A".
    """
    rng = random.Random(seed)
    barajados = list(ids_casos)
    rng.shuffle(barajados)

    punto_corte = rng.choice([7, 8])
    sistema_es_a = set(barajados[:punto_corte])

    asignacion: dict[int, dict[str, str]] = {}
    for id_caso in ids_casos:
        if id_caso in sistema_es_a:
            asignacion[id_caso] = {"A": "sistema", "B": "eh2"}
        else:
            asignacion[id_caso] = {"A": "eh2", "B": "sistema"}
    return asignacion


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepara tokens, asignacion A/B y contenido para el panel de evaluacion ciega."
    )
    parser.add_argument(
        "--evaluadores",
        type=int,
        default=int(os.environ.get("NUM_EVALUADORES", 3)),
        help="Numero de evaluadores reales (por defecto 3, o env NUM_EVALUADORES).",
    )
    parser.add_argument("--perfil-csv", type=Path, default=Path(
        os.environ.get("PERFIL_CSV", DEFAULT_PERFIL_CSV)
    ))
    parser.add_argument("--sistema-csv", type=Path, default=Path(
        os.environ.get("SISTEMA_CSV", DEFAULT_SISTEMA_CSV)
    ))
    parser.add_argument("--expertos-csv", type=Path, default=Path(
        os.environ.get("EXPERTOS_CSV", DEFAULT_EXPERTOS_CSV)
    ))
    parser.add_argument("--datos-dir", type=Path, default=Path(
        os.environ.get("DATOS_DIR", DEFAULT_DATOS_DIR)
    ))
    parser.add_argument("--secreto-dir", type=Path, default=Path(
        os.environ.get("SECRETO_DIR", DEFAULT_SECRETO_DIR)
    ))
    parser.add_argument("--eh1-referencia", type=Path, default=Path(
        os.environ.get("EH1_REFERENCIA_CSV", DEFAULT_EH1_REF_PATH)
    ))
    parser.add_argument("--base-url", type=str, default=os.environ.get(
        "BASE_URL", DEFAULT_BASE_URL
    ))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.evaluadores < 1:
        print("ERROR: --evaluadores debe ser >= 1", file=sys.stderr)
        return 1

    perfiles = cargar_perfiles(args.perfil_csv)
    sistema = cargar_sistema(args.sistema_csv)
    eh2, eh1_filas, eh_fieldnames = cargar_expertos(args.expertos_csv)

    ids_perfil = set(perfiles.keys())
    ids_sistema = set(sistema.keys())
    ids_eh2 = set(eh2.keys())

    if not (ids_perfil == ids_sistema == ids_eh2):
        print("ERROR: los conjuntos de id_caso no coinciden entre archivos.", file=sys.stderr)
        print(f"  perfil : {sorted(ids_perfil)}", file=sys.stderr)
        print(f"  sistema: {sorted(ids_sistema)}", file=sys.stderr)
        print(f"  eh2    : {sorted(ids_eh2)}", file=sys.stderr)
        return 1

    if len(ids_perfil) != 15:
        print(f"ERROR: se esperaban 15 casos, se encontraron {len(ids_perfil)}.", file=sys.stderr)
        return 1

    ids_casos = sorted(ids_perfil)

    # eh1 de referencia (no forma parte de la app, solo se preserva)
    escribir_eh1_referencia(eh1_filas, eh_fieldnames, args.eh1_referencia)

    # contenido no secreto: perfil + version sistema + version eh2 por caso
    casos_contenido = {
        str(id_caso): {
            "perfil": perfiles[id_caso],
            "sistema": sistema[id_caso],
            "eh2": eh2[id_caso],
        }
        for id_caso in ids_casos
    }

    evaluadores_json: dict[str, dict] = {}
    decode_json: dict[str, dict] = {}
    resumen: list[dict] = []

    especificaciones = [
        (f"evaluador_{i}", False) for i in range(1, args.evaluadores + 1)
    ] + [("prueba", True)]

    for evaluador_id, es_prueba in especificaciones:
        token = secrets.token_urlsafe(24)
        seed = secrets.randbits(32)

        asignacion = generar_asignacion(ids_casos, seed)

        evaluadores_json[token] = {
            "evaluador_id": evaluador_id,
            "es_prueba": es_prueba,
            "seed": seed,
            "casos": ids_casos,
        }
        decode_json[token] = {
            str(id_caso): asignacion[id_caso] for id_caso in ids_casos
        }

        resumen.append(
            {
                "evaluador_id": evaluador_id,
                "es_prueba": es_prueba,
                "token": token,
                "seed": seed,
                "url": f"{args.base_url.rstrip('/')}/e/{token}",
            }
        )

    # Escritura de salidas
    args.datos_dir.mkdir(parents=True, exist_ok=True)
    args.secreto_dir.mkdir(parents=True, exist_ok=True)

    with (args.datos_dir / "evaluadores.json").open("w", encoding="utf-8") as f:
        json.dump(evaluadores_json, f, ensure_ascii=False, indent=2)

    with (args.datos_dir / "casos.json").open("w", encoding="utf-8") as f:
        json.dump(casos_contenido, f, ensure_ascii=False, indent=2)

    with (args.secreto_dir / "decode.json").open("w", encoding="utf-8") as f:
        json.dump(decode_json, f, ensure_ascii=False, indent=2)

    # Resumen en texto plano
    print("=" * 78)
    print("PANEL DE EVALUACION CIEGA - tokens generados")
    print("=" * 78)
    for item in resumen:
        marca = "  <-- TOKEN DE PRUEBA (no usar en el analisis final)" if item["es_prueba"] else ""
        print(f"{item['evaluador_id']:<14} seed={item['seed']:<12} {item['url']}{marca}")
    print("=" * 78)
    print(f"Casos preparados: {len(ids_casos)}")
    print(f"Evaluadores reales: {args.evaluadores}  (+ 1 token de prueba)")
    print(f"Salidas no secretas -> {args.datos_dir}")
    print(f"Salida secreta      -> {args.secreto_dir}  (NO commitear, NO copiar a la imagen Docker)")
    print(f"Referencia EH1      -> {args.eh1_referencia}")
    print("=" * 78)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
