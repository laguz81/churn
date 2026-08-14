"""
Orquesta el pipeline completo de 4 agentes sobre casos_15_perfil.csv.

IMPORTANTE (lease antes de ejecutar):
  Este script SI llama a la API de OpenAI de verdad (4+ llamadas LLM por
  caso). Al final de cada corrida se ejecuta una validacion anti-plantilla
  a nivel de CORRIDA (no por caso): si algun campo de salida repite el
  mismo valor literal en mas de config.MAX_REPETICION_LITERAL_PCT de los
  casos, la corrida completa se marca invalida en
  resultados/validacion_corrida.json (o su equivalente bajo --casos) y se
  imprime una advertencia clara en stderr. El CSV se escribe de todas
  formas para poder inspeccionar la salida cruda.

Fuente de casos: UNICAMENTE config.CASOS_PERFIL_CSV
(corpus_1/casos_15_perfil.csv). Este modulo NUNCA debe leer
casos_15_expertos.csv ni PRIVADO_mapa_id.csv; esos nombres no aparecen en
ninguna ruta de codigo de este archivo.

Uso:
    python pipeline.py                  # los 15 casos, corrida completa
    python pipeline.py --casos 1,2      # solo id_caso 1 y 2 (piloto de formato)

Con --casos, las salidas se escriben en un subdirectorio propio dentro de
resultados/ (p.ej. resultados/piloto_casos_1_2/) para no pisar ni
mezclarse con los archivos de la corrida completa de los 15.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone

from agentes import (
    TrazaCaso,
    agente1_perfilador,
    agente2_verificador,
    agente3_sintetizador,
    agente4_generador,
)
from config import (
    CASOS_PERFIL_CSV,
    INDICE_ACCIONES_META_PATH,
    INDICE_ACCIONES_PATH,
    INDICE_PROMOCIONES_META_PATH,
    INDICE_PROMOCIONES_PATH,
    LLM_MAX_RETRIES_AGENTE4,
    MAX_REPETICION_LITERAL_PCT,
    RECOMENDACIONES_CSV,
    RUN_LOG_JSONL,
    TRAZAS_JSON,
    ensure_dirs,
    get_openai_api_key,
)
from validador import detectar_repeticion_plantilla, validar_salida_agente4
from vectorstore import VectorIndex


def _cargar_casos() -> list[dict]:
    """Unica funcion autorizada para leer casos del estudio. Lee
    exclusivamente config.CASOS_PERFIL_CSV (casos_15_perfil.csv)."""
    with open(CASOS_PERFIL_CSV, encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        casos = []
        for fila in lector:
            casos.append(
                {
                    "id_caso": fila["id_caso"],
                    "recency_dias": float(fila["recency_dias"]),
                    "frequency": float(fila["frequency"]),
                    "monetary_usd": float(fila["monetary_usd"]),
                    "segmento": fila["segmento"],
                }
            )
        return casos


def _procesar_caso(caso: dict, indice_acciones: VectorIndex, indice_promociones: VectorIndex) -> tuple[TrazaCaso, dict, dict]:
    """Corre el caso a traves de los 4 agentes. Devuelve (traza, fila_csv, entrada_run_log)."""
    traza = TrazaCaso(id_caso=caso["id_caso"], caso_entrada=caso)

    salida_a1 = agente1_perfilador(caso)
    traza.agente1 = salida_a1
    resumen_perfil = salida_a1["output"]["resumen_perfil"]

    salida_a2 = agente2_verificador(
        resumen_perfil, indice_acciones, indice_promociones, monetary_usd=caso["monetary_usd"]
    )
    traza.agente2 = salida_a2
    contradiccion_umbral = salida_a2.get("contradiccion_umbral")
    contradiccion_umbral_objetivo = salida_a2.get("contradiccion_umbral_objetivo")

    salida_a3 = agente3_sintetizador(resumen_perfil, salida_a2["items_aprobados_para_agente3"])
    traza.agente3 = salida_a3
    contexto_condensado = salida_a3["output"]["contexto_condensado"]

    revision_manual = False
    ultimo_error: list[str] = []
    salida_final: dict = {}
    intentos_a4 = []

    for intento in range(1, LLM_MAX_RETRIES_AGENTE4 + 1):
        salida_a4, prompt_a4, resp_a4 = agente4_generador(resumen_perfil, contexto_condensado)
        resultado_validacion = validar_salida_agente4(
            salida_a4,
            recency_dias=caso["recency_dias"],
            frequency=caso["frequency"],
            monetary_usd=caso["monetary_usd"],
        )
        intentos_a4.append(
            {
                "intento": intento,
                "output": salida_a4,
                "prompt_renderizado": prompt_a4,
                "llm": {
                    "modelo": resp_a4.modelo,
                    "seed": resp_a4.seed,
                    "temperatura": resp_a4.temperatura,
                    "response_id": resp_a4.response_id,
                },
                "validacion": {
                    "valido": resultado_validacion.valido,
                    "errores": resultado_validacion.errores,
                },
            }
        )
        salida_final = salida_a4
        ultimo_error = resultado_validacion.errores
        if resultado_validacion.valido:
            break
    else:
        # Se agotaron los reintentos sin que ningun intento pasara la
        # validacion: se escribe la ultima salida igual, pero marcada
        # para revision manual (nunca se descarta el caso en silencio).
        revision_manual = True

    if contradiccion_umbral or contradiccion_umbral_objetivo:
        # Agente 2 aprobo a la vez dos acciones cuyas condiciones de uso
        # se excluyen mutuamente sobre el mismo umbral (contradiccion_umbral,
        # detectada en la propia respuesta del LLM), o aprobo una accion
        # que contradice el monto REAL del caso, conocido en codigo, sin
        # que hubiera empate ni contradiccion textual (contradiccion_umbral_
        # objetivo -- ver agentes.py, caso real: id_caso 1 en la corrida del
        # 2026-08-14). El "ganador" que se uso para continuar el pipeline es
        # solo un mejor esfuerzo; la fila se marca para revision manual sin
        # importar que el formato de Agente 4 haya validado bien.
        revision_manual = True

    traza.agente4 = {"intentos": intentos_a4, "revision_manual": revision_manual}

    fila_csv = {
        "id_caso": caso["id_caso"],
        "recomendacion": salida_final.get("recomendacion", ""),
        "accion": salida_final.get("accion", ""),
        "plazo": salida_final.get("plazo", ""),
        "justificacion": salida_final.get("justificacion", ""),
        "revision_manual": revision_manual,
    }

    entrada_log = {
        "id_caso": caso["id_caso"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "modelo": intentos_a4[-1]["llm"]["modelo"] if intentos_a4 else None,
        "temperatura": 0,
        "seed": intentos_a4[-1]["llm"]["seed"] if intentos_a4 else None,
        "intentos_agente4": len(intentos_a4),
        "revision_manual": revision_manual,
        "ultimo_error_validacion": ultimo_error,
        "acciones_descartadas_por_umbral": salida_a2["acciones_descartadas"],
        "promociones_descartadas_por_umbral": salida_a2["promociones_descartadas"],
        "theta": salida_a2["theta"],
        "contradiccion_umbral_agente2": contradiccion_umbral,
        "contradiccion_umbral_objetivo_agente2": contradiccion_umbral_objetivo,
    }

    return traza, fila_csv, entrada_log


def _parsear_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--casos",
        type=str,
        default=None,
        help="Lista separada por comas de id_caso a procesar (p.ej. '1,2'). "
        "Si se omite, procesa los 15 casos completos.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parsear_args()

    # Falla rapido si falta la API key, antes de cargar modelos/indices.
    get_openai_api_key()
    ensure_dirs()

    if not INDICE_ACCIONES_PATH.exists() and not INDICE_ACCIONES_PATH.with_suffix(".npy").exists():
        raise RuntimeError(
            "No se encontro el indice de acciones. Corre 'python indexador.py' antes del pipeline."
        )

    indice_acciones = VectorIndex.cargar(INDICE_ACCIONES_PATH, INDICE_ACCIONES_META_PATH)
    indice_promociones = VectorIndex.cargar(INDICE_PROMOCIONES_PATH, INDICE_PROMOCIONES_META_PATH)

    casos = _cargar_casos()

    if args.casos:
        ids_pedidos = [s.strip() for s in args.casos.split(",") if s.strip()]
        casos = [c for c in casos if c["id_caso"] in ids_pedidos]
        faltantes = set(ids_pedidos) - {c["id_caso"] for c in casos}
        if faltantes:
            raise ValueError(f"id_caso no encontrado en casos_15_perfil.csv: {sorted(faltantes)}")
        etiqueta = "piloto_casos_" + "_".join(ids_pedidos)
        dir_salida = RECOMENDACIONES_CSV.parent / etiqueta
        dir_salida.mkdir(parents=True, exist_ok=True)
        ruta_recomendaciones = dir_salida / RECOMENDACIONES_CSV.name
        ruta_trazas = dir_salida / TRAZAS_JSON.name
        ruta_run_log = dir_salida / RUN_LOG_JSONL.name
    else:
        ruta_recomendaciones = RECOMENDACIONES_CSV
        ruta_trazas = TRAZAS_JSON
        ruta_run_log = RUN_LOG_JSONL

    filas_csv: list[dict] = []
    trazas: list[dict] = []

    with open(ruta_run_log, "w", encoding="utf-8") as log_f:
        for caso in casos:
            traza, fila_csv, entrada_log = _procesar_caso(caso, indice_acciones, indice_promociones)
            filas_csv.append(fila_csv)
            trazas.append(traza.to_dict())
            log_f.write(json.dumps(entrada_log, ensure_ascii=False) + "\n")
            print(f"caso {caso['id_caso']}: revision_manual={fila_csv['revision_manual']}")

    with open(ruta_recomendaciones, "w", encoding="utf-8", newline="") as csv_f:
        campos = ["id_caso", "recomendacion", "accion", "plazo", "justificacion", "revision_manual"]
        escritor = csv.DictWriter(csv_f, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(filas_csv)

    ruta_trazas.write_text(json.dumps(trazas, ensure_ascii=False, indent=2), encoding="utf-8")

    resultado_antiplantilla = detectar_repeticion_plantilla(filas_csv)
    ruta_validacion_corrida = ruta_recomendaciones.parent / "validacion_corrida.json"
    ruta_validacion_corrida.write_text(
        json.dumps(
            {
                "valida": resultado_antiplantilla.valida,
                "n_casos": len(casos),
                "umbral_repeticion_pct": MAX_REPETICION_LITERAL_PCT,
                "repeticiones_excesivas": resultado_antiplantilla.repeticiones,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nListo. {len(casos)} casos procesados.")
    print(f"  -> {ruta_recomendaciones}")
    print(f"  -> {ruta_trazas}")
    print(f"  -> {ruta_run_log}")
    print(f"  -> {ruta_validacion_corrida}")

    if not resultado_antiplantilla.valida:
        print(
            "\n*** CORRIDA MARCADA COMO INVALIDA (validacion anti-plantilla) ***",
            file=sys.stderr,
        )
        print(
            f"Uno o mas campos repiten el mismo valor literal en mas del "
            f"{MAX_REPETICION_LITERAL_PCT:.0%} de los {len(casos)} casos -- el sistema no esta "
            f"individualizando por cliente. Detalle en {ruta_validacion_corrida}:",
            file=sys.stderr,
        )
        for campo, valores in resultado_antiplantilla.repeticiones.items():
            for valor, conteo in valores.items():
                print(f"  '{campo}' ({conteo}/{len(casos)}): {valor!r}", file=sys.stderr)


if __name__ == "__main__":
    main()
