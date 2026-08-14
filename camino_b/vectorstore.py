"""
Almacen vectorial con backend FAISS y fallback automatico a busqueda por
fuerza bruta con numpy (coseno) si faiss-cpu no esta disponible/instalable
en este interprete (Python 3.13 es reciente; algunos paquetes de ML tardan
en publicar wheels).

Con un corpus de ~15 chunks en total, la fuerza bruta con numpy es mas que
suficiente en rendimiento: no hay ninguna perdida practica de calidad de
busqueda por usar el fallback.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from corpus import Chunk

try:
    import faiss  # type: ignore

    FAISS_DISPONIBLE = True
except ImportError:  # pragma: no cover - depende del entorno
    faiss = None  # type: ignore
    FAISS_DISPONIBLE = False


class VectorIndex:
    """Indice vectorial sobre una lista de Chunks, con backend FAISS o
    fallback numpy segun disponibilidad del paquete faiss."""

    def __init__(self, chunks: list[Chunk], vectores: np.ndarray):
        if len(chunks) != vectores.shape[0]:
            raise ValueError("chunks y vectores deben tener la misma longitud")
        self.chunks = chunks
        self.vectores = vectores.astype("float32")
        self.backend = "faiss" if FAISS_DISPONIBLE else "numpy"
        self._faiss_index = None
        if FAISS_DISPONIBLE:
            dim = self.vectores.shape[1]
            self._faiss_index = faiss.IndexFlatIP(dim)
            self._faiss_index.add(self.vectores)

    def buscar(self, vector_consulta: np.ndarray, k: int) -> list[tuple[Chunk, float]]:
        """Devuelve hasta k pares (chunk, score_similitud_coseno),
        ordenados de mayor a menor similitud."""
        k = min(k, len(self.chunks))
        if k == 0:
            return []
        consulta = vector_consulta.astype("float32").reshape(1, -1)

        if self.backend == "faiss":
            scores, indices = self._faiss_index.search(consulta, k)
            pares = [
                (self.chunks[idx], float(score))
                for score, idx in zip(scores[0], indices[0])
                if idx != -1
            ]
        else:
            # Vectores ya normalizados -> producto interno == coseno.
            scores = self.vectores @ consulta[0]
            top_idx = np.argsort(-scores)[:k]
            pares = [(self.chunks[i], float(scores[i])) for i in top_idx]
        return pares

    def guardar(self, ruta_indice: Path, ruta_meta: Path) -> None:
        ruta_indice.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "backend": self.backend,
            "chunks": [asdict(c) for c in self.chunks],
        }
        ruta_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        if self.backend == "faiss":
            faiss.write_index(self._faiss_index, str(ruta_indice))
        else:
            np.save(ruta_indice.with_suffix(".npy"), self.vectores)

    @classmethod
    def cargar(cls, ruta_indice: Path, ruta_meta: Path) -> "VectorIndex":
        meta = json.loads(ruta_meta.read_text(encoding="utf-8"))
        chunks = [Chunk(**c) for c in meta["chunks"]]
        backend_guardado = meta["backend"]

        if backend_guardado == "faiss" and not FAISS_DISPONIBLE:
            raise RuntimeError(
                f"El indice en {ruta_indice} fue creado con backend 'faiss' pero "
                "faiss no esta disponible en este interprete. Reindexa con "
                "'python indexador.py' en este entorno."
            )

        if backend_guardado == "faiss":
            instancia = cls.__new__(cls)
            instancia.chunks = chunks
            instancia.backend = "faiss"
            instancia._faiss_index = faiss.read_index(str(ruta_indice))
            instancia.vectores = instancia._faiss_index.reconstruct_n(0, len(chunks))
            return instancia
        else:
            vectores = np.load(ruta_indice.with_suffix(".npy"))
            instancia = cls.__new__(cls)
            instancia.chunks = chunks
            instancia.vectores = vectores
            instancia.backend = "numpy"
            instancia._faiss_index = None
            return instancia
