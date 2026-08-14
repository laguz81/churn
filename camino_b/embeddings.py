"""
Wrapper del modelo de embeddings (sentence-transformers, local, multilingue).

Un solo punto de carga del modelo para que indexador.py y los agentes en
tiempo de consulta usen exactamente el mismo modelo y la misma normalizacion
de vectores.
"""

from __future__ import annotations

import numpy as np

from config import EMBEDDING_MODEL_NAME

_modelo = None


def _get_modelo():
    global _modelo
    if _modelo is None:
        # Import perezoso: sentence-transformers es pesado de importar y no
        # todos los usos del paquete (p.ej. el validador) lo necesitan.
        from sentence_transformers import SentenceTransformer

        _modelo = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _modelo


def embeber(textos: list[str]) -> np.ndarray:
    """Embebe una lista de textos y devuelve vectores normalizados (L2)
    en float32, listos para similitud coseno via producto interno."""
    modelo = _get_modelo()
    vectores = modelo.encode(
        textos,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectores.astype("float32")
