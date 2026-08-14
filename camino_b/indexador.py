"""
Construye (o reconstruye) los 3 indices vectoriales del sistema:
  - acciones.index      (4 chunks: Accion 1-3 de acciones_retencion_1.md +
                          Accion 4 de acciones_retencion_2.md, agregada
                          2026-08-14 tras resolver el gap del umbral $500)
  - promociones.index   (10 chunks: Promocion 1..10 de promociones_vigentes_1.md)
  - politica.index      (secciones de politica_descuentos_1.md; no se
                          consulta por similitud en el pipeline actual, se
                          indexa para dejar el corpus completo trazado y
                          disponible para uso futuro)

Uso:
    python indexador.py

Es la UNICA forma soportada de (re)generar los indices. Si el corpus
vuelve a cambiar (nueva accion, nueva promocion), basta con volver a
correr este script.
"""

from __future__ import annotations

import sys

from config import (
    INDICE_ACCIONES_META_PATH,
    INDICE_ACCIONES_PATH,
    INDICE_POLITICA_META_PATH,
    INDICE_POLITICA_PATH,
    INDICE_PROMOCIONES_META_PATH,
    INDICE_PROMOCIONES_PATH,
    ensure_dirs,
)
from corpus import cargar_chunks_acciones, cargar_chunks_politica, cargar_chunks_promociones
from embeddings import embeber
from vectorstore import FAISS_DISPONIBLE, VectorIndex


def _construir_indice(nombre: str, chunks, ruta_indice, ruta_meta) -> VectorIndex:
    if not chunks:
        raise RuntimeError(f"No se extrajo ningun chunk para el indice '{nombre}'")
    textos = [c.texto for c in chunks]
    vectores = embeber(textos)
    indice = VectorIndex(chunks, vectores)
    indice.guardar(ruta_indice, ruta_meta)
    print(f"[{nombre}] {len(chunks)} chunks indexados (backend={indice.backend}) -> {ruta_indice}")
    for c in chunks:
        print(f"    - {c.chunk_id}: {c.titulo}")
    return indice


def main() -> None:
    ensure_dirs()
    print(f"Backend de similitud: {'faiss' if FAISS_DISPONIBLE else 'numpy (fallback, fuerza bruta)'}")
    print("Cargando y chunkeando corpus (whitelist de 4 archivos .md)...")

    chunks_acciones = cargar_chunks_acciones()
    chunks_promociones = cargar_chunks_promociones()
    chunks_politica = cargar_chunks_politica()

    if len(chunks_acciones) != 4:
        print(
            f"AVISO: se esperaban 4 acciones de nivel superior, se encontraron {len(chunks_acciones)}. "
            "Revisa el formato de encabezados en acciones_retencion_1.md y acciones_retencion_2.md.",
            file=sys.stderr,
        )
    if len(chunks_promociones) != 10:
        print(
            f"AVISO: se esperaban 10 promociones, se encontraron {len(chunks_promociones)}. "
            "Revisa el formato de encabezados en promociones_vigentes_1.md.",
            file=sys.stderr,
        )

    _construir_indice("acciones", chunks_acciones, INDICE_ACCIONES_PATH, INDICE_ACCIONES_META_PATH)
    _construir_indice("promociones", chunks_promociones, INDICE_PROMOCIONES_PATH, INDICE_PROMOCIONES_META_PATH)
    _construir_indice("politica", chunks_politica, INDICE_POLITICA_PATH, INDICE_POLITICA_META_PATH)

    print("Listo.")


if __name__ == "__main__":
    main()
