"""
Smoke test de la red de seguridad de contradiccion de umbral (Agente 2).

Prueba _detectar_contradiccion_umbral() de forma aislada, con
ItemEvaluado construidos a mano (no requiere OPENAI_API_KEY ni corpus
real: es una funcion pura sobre una lista de scores/justificaciones).

Uso:
    python -m tests.test_agentes
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentes import ItemEvaluado, _detectar_contradiccion_umbral

_falla = []


def check(nombre: str, condicion: bool, detalle: str = "") -> None:
    estado = "OK  " if condicion else "FAIL"
    print(f"[{estado}] {nombre}" + (f" -- {detalle}" if detalle and not condicion else ""))
    if not condicion:
        _falla.append(nombre)


def _item(chunk_id: str, score: float, aprobado: bool) -> ItemEvaluado:
    return ItemEvaluado(chunk_id=chunk_id, titulo=chunk_id, score=score, justificacion="test", aprobado=aprobado)


def main() -> int:
    # --- Caso reproducido en la corrida real (casos 13/14 del piloto):
    #     accion_1 y accion_4 aprobadas a la vez, contradiccion real. ---
    evaluadas_contradictorias = [
        _item("accion_4", 1.0, True),
        _item("accion_3", 0.5, False),
        _item("accion_1", 1.0, True),
        _item("accion_2", 0.0, False),
    ]
    resultado = _detectar_contradiccion_umbral(evaluadas_contradictorias)
    check(
        "accion_1 y accion_4 ambas aprobadas se detecta como contradiccion",
        resultado is not None and resultado["par"] == ["accion_1", "accion_4"],
        f"resultado={resultado}",
    )

    # --- Caso limpio (caso 2 del piloto): solo accion_4 aprobada. ---
    evaluadas_limpias_bajo = [
        _item("accion_4", 1.0, True),
        _item("accion_3", 0.5, False),
        _item("accion_1", 0.0, False),
        _item("accion_2", 0.0, False),
    ]
    check(
        "solo accion_4 aprobada no dispara contradiccion",
        _detectar_contradiccion_umbral(evaluadas_limpias_bajo) is None,
    )

    # --- Caso limpio (caso 1 del piloto): solo accion_1 aprobada. ---
    evaluadas_limpias_sobre = [
        _item("accion_4", 0.0, False),
        _item("accion_3", 0.8, True),
        _item("accion_1", 1.0, True),
        _item("accion_2", 0.5, False),
    ]
    check(
        "accion_1 y accion_3 aprobadas a la vez NO dispara contradiccion (no son mutuamente excluyentes)",
        _detectar_contradiccion_umbral(evaluadas_limpias_sobre) is None,
    )

    # --- Caso con datos incompletos (p.ej. accion_4 no vino en la lista,
    #     no deberia reventar). ---
    evaluadas_sin_accion4 = [
        _item("accion_1", 1.0, True),
        _item("accion_2", 0.5, False),
        _item("accion_3", 0.3, False),
    ]
    check(
        "lista sin accion_4 no revienta y no dispara contradiccion",
        _detectar_contradiccion_umbral(evaluadas_sin_accion4) is None,
    )

    if _falla:
        print(f"\n{len(_falla)} test(s) fallaron: {_falla}")
        return 1
    print("\nTodos los tests de agentes (red de seguridad) pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
