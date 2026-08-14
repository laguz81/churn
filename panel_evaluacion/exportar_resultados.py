#!/usr/bin/env python3
"""
exportar_resultados.py

Exporta las respuestas guardadas en SQLite a los formatos requeridos para
el analisis del panel de evaluacion. Excluye SIEMPRE las filas de token(s)
de prueba (es_prueba=1).

Salidas (formato ancho -> largo):
  - calificaciones.csv : evaluador, id_caso, etiqueta, criterio, puntaje
      Cada evento de envio (una fila en SQLite) se expande a 4 filas:
      (A,relevancia) (A,viabilidad) (B,relevancia) (B,viabilidad)
  - comentarios.csv    : evaluador, id_caso, comentario, timestamp
      Solo filas donde realmente se escribio un comentario.

No expone ni necesita secreto/decode.json: ese archivo es el que ya sirve
como "diccionario etiqueta -> fuente" para el analisis posterior; no se
duplica aqui.

Uso:
    python exportar_resultados.py --db data/respuestas.db --salida .
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = Path(os.environ.get("DB_PATH", BASE_DIR / "data" / "respuestas.db"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exporta calificaciones.csv y comentarios.csv")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--salida", type=Path, default=BASE_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.db.exists():
        print(f"ERROR: no existe la base de datos {args.db}")
        return 1

    args.salida.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    try:
        filas = conn.execute(
            """
            SELECT evaluador_id, id_caso, relevancia_a, viabilidad_a,
                   relevancia_b, viabilidad_b, comentario, timestamp_utc
            FROM respuestas
            WHERE es_prueba = 0
            ORDER BY evaluador_id, id_caso
            """
        ).fetchall()
    finally:
        conn.close()

    calif_path = args.salida / "calificaciones.csv"
    coment_path = args.salida / "comentarios.csv"

    n_calif = 0
    n_coment = 0

    with calif_path.open("w", encoding="utf-8", newline="") as f_calif, \
         coment_path.open("w", encoding="utf-8", newline="") as f_coment:

        w_calif = csv.writer(f_calif)
        w_calif.writerow(["evaluador", "id_caso", "etiqueta", "criterio", "puntaje"])

        w_coment = csv.writer(f_coment)
        w_coment.writerow(["evaluador", "id_caso", "comentario", "timestamp"])

        for fila in filas:
            expandido = [
                ("A", "relevancia", fila["relevancia_a"]),
                ("A", "viabilidad", fila["viabilidad_a"]),
                ("B", "relevancia", fila["relevancia_b"]),
                ("B", "viabilidad", fila["viabilidad_b"]),
            ]
            for etiqueta, criterio, puntaje in expandido:
                w_calif.writerow([fila["evaluador_id"], fila["id_caso"], etiqueta, criterio, puntaje])
                n_calif += 1

            if fila["comentario"]:
                w_coment.writerow(
                    [fila["evaluador_id"], fila["id_caso"], fila["comentario"], fila["timestamp_utc"]]
                )
                n_coment += 1

    print(f"calificaciones.csv -> {calif_path}  ({n_calif} filas)")
    print(f"comentarios.csv    -> {coment_path}  ({n_coment} filas)")
    print("(filas de token(s) de prueba excluidas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
