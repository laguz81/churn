"""
Smoke test del indexador: construye los indices reales a partir del
corpus (los 3 .md whitelisted) y corre un par de consultas de similitud
para comprobar que la recuperacion trae los chunks correctos.

No requiere OPENAI_API_KEY (no llama a ningun LLM, solo al modelo de
embeddings local). Requiere sentence-transformers y, si esta disponible,
faiss-cpu (si no, usa el fallback numpy de forma transparente).

Uso:
    python -m tests.test_indexador
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus import cargar_chunks_acciones, cargar_chunks_politica, cargar_chunks_promociones
from embeddings import embeber
from vectorstore import VectorIndex

_falla = []


def check(nombre: str, condicion: bool, detalle: str = "") -> None:
    estado = "OK  " if condicion else "FAIL"
    print(f"[{estado}] {nombre}" + (f" -- {detalle}" if detalle and not condicion else ""))
    if not condicion:
        _falla.append(nombre)


def main() -> int:
    print("Cargando chunks del corpus real (whitelist de 3 .md)...")
    chunks_acciones = cargar_chunks_acciones()
    chunks_promociones = cargar_chunks_promociones()
    chunks_politica = cargar_chunks_politica()

    check("se extraen exactamente 3 acciones", len(chunks_acciones) == 3, f"{len(chunks_acciones)} encontradas")
    check("se extraen exactamente 10 promociones", len(chunks_promociones) == 10, f"{len(chunks_promociones)} encontradas")
    check("se extrae al menos 1 seccion de politica", len(chunks_politica) >= 1, f"{len(chunks_politica)} encontradas")

    print("Embebiendo y construyendo indices en memoria...")
    vec_acciones = embeber([c.texto for c in chunks_acciones])
    indice_acciones = VectorIndex(chunks_acciones, vec_acciones)
    print(f"  backend usado: {indice_acciones.backend}")

    vec_promos = embeber([c.texto for c in chunks_promociones])
    indice_promos = VectorIndex(chunks_promociones, vec_promos)

    # --- Consulta 1: perfil de cliente inactivo hace tiempo, sin visitas ---
    consulta_1 = (
        "Cliente que lleva mucho tiempo sin comprar, no ha respondido a "
        "llamadas ni WhatsApp, el vendedor no pasa por su zona habitualmente."
    )
    vec_q1 = embeber([consulta_1])[0]
    resultados_1 = indice_acciones.buscar(vec_q1, k=3)
    top1_id = resultados_1[0][0].chunk_id
    check(
        "consulta de cliente inactivo sin respuesta a canales virtuales trae Accion 1 o 3 en el top",
        top1_id in ("accion_1", "accion_3"),
        f"top1={top1_id}, scores={[(c.chunk_id, round(s,3)) for c,s in resultados_1]}",
    )

    # --- Consulta 2: interes en promociones de vino ---
    consulta_2 = "Cliente interesado en descuentos y promociones vigentes de vinos para reactivar la compra."
    vec_q2 = embeber([consulta_2])[0]
    resultados_2 = indice_acciones.buscar(vec_q2, k=3)
    top1_id_2 = resultados_2[0][0].chunk_id
    check(
        "consulta sobre promociones vigentes trae Accion 3 en el top",
        top1_id_2 == "accion_3",
        f"top1={top1_id_2}, scores={[(c.chunk_id, round(s,3)) for c,s in resultados_2]}",
    )

    # --- Consulta 3: sobre promociones de vino especificas ---
    consulta_3 = "Descuento semanal rotativo por variedad de uva, aplica directo sin monto minimo."
    vec_q3 = embeber([consulta_3])[0]
    resultados_3 = indice_promos.buscar(vec_q3, k=3)
    top1_id_3 = resultados_3[0][0].chunk_id
    check(
        "consulta sobre descuento semanal por varietal trae promocion_1 en el top",
        top1_id_3 == "promocion_1",
        f"top1={top1_id_3}, scores={[(c.chunk_id, round(s,3)) for c,s in resultados_3]}",
    )

    # --- Persistencia: guardar y recargar el indice de acciones ---
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ruta_indice = Path(tmp) / "acciones_test.index"
        ruta_meta = Path(tmp) / "acciones_test_meta.json"
        indice_acciones.guardar(ruta_indice, ruta_meta)
        recargado = VectorIndex.cargar(ruta_indice, ruta_meta)
        check(
            "el indice recargado desde disco conserva el numero de chunks",
            len(recargado.chunks) == len(chunks_acciones),
        )
        resultados_recarga = recargado.buscar(vec_q2, k=1)
        check(
            "el indice recargado devuelve el mismo top1 que el original",
            resultados_recarga[0][0].chunk_id == top1_id_2,
        )

    if _falla:
        print(f"\n{len(_falla)} test(s) fallaron: {_falla}")
        return 1
    print("\nTodos los tests del indexador pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
