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

from agentes import (
    ItemEvaluado,
    _detectar_contradiccion_umbral,
    _detectar_contradiccion_umbral_objetivo,
    _quitar_punto_final,
)

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

    # ------------------------------------------------------------------
    # _detectar_contradiccion_umbral_objetivo: verifica contra el monto
    # REAL del caso, no contra lo que el LLM dijo sobre el otro par.
    # Reproduce el caso real de la corrida 2026-08-14 (id_caso 1): monto
    # muy por encima de $500, accion_1 rechazada, accion_4 aprobada, SIN
    # empate ni contradiccion textual -- la primera red no lo atrapaba.
    # ------------------------------------------------------------------
    evaluadas_caso1_real = [
        _item("accion_4", 1.0, True),
        _item("accion_3", 0.5, False),
        _item("accion_1", 0.0, False),
        _item("accion_2", 0.0, False),
    ]
    resultado_obj = _detectar_contradiccion_umbral_objetivo(evaluadas_caso1_real, monetary_usd=1401.30)
    check(
        "accion_4 aprobada con monto muy por encima de $500 se detecta (caso real id_caso 1)",
        resultado_obj is not None and resultado_obj["tipo"] == "accion_4_aprobada_pese_a_superar_umbral",
        f"resultado={resultado_obj}",
    )
    check(
        "_detectar_contradiccion_umbral (self-contradiccion) NO detecta el caso 1 real (sin empate)",
        _detectar_contradiccion_umbral(evaluadas_caso1_real) is None,
    )

    check(
        "accion_1 aprobada con monto bajo $500 se detecta",
        (
            lambda r: r is not None and r["tipo"] == "accion_1_aprobada_pese_a_no_superar_umbral"
        )(
            _detectar_contradiccion_umbral_objetivo(
                [_item("accion_1", 1.0, True), _item("accion_4", 0.0, False)], monetary_usd=148.99
            )
        ),
    )
    check(
        "veredicto correcto (accion_1 aprobada, monto sobre $500) no dispara nada",
        _detectar_contradiccion_umbral_objetivo(
            [_item("accion_1", 1.0, True), _item("accion_4", 0.0, False)], monetary_usd=1537.77
        )
        is None,
    )
    check(
        "veredicto correcto (accion_4 aprobada, monto bajo $500) no dispara nada",
        _detectar_contradiccion_umbral_objetivo(
            [_item("accion_1", 0.0, False), _item("accion_4", 1.0, True)], monetary_usd=148.99
        )
        is None,
    )
    check(
        "lista de promociones (sin accion_1/accion_4) no revienta y no dispara nada",
        _detectar_contradiccion_umbral_objetivo(
            [_item("promocion_1", 0.9, True), _item("promocion_2", 0.2, False)], monetary_usd=1401.30
        )
        is None,
    )

    # ------------------------------------------------------------------
    # _quitar_punto_final: el LLM no evita el punto final de forma
    # confiable via instruccion (agoto 3/3 reintentos en 2/2 casos piloto
    # reales), asi que se recorta de forma deterministica.
    # ------------------------------------------------------------------
    check("quita el punto final simple", _quitar_punto_final("Llamar por telefono.") == "Llamar por telefono")
    check("quita el punto final con espacio previo", _quitar_punto_final("Llamar por telefono . ") == "Llamar por telefono")
    check("no toca texto sin punto final", _quitar_punto_final("Llamar por telefono") == "Llamar por telefono")
    check(
        "no toca puntos suspensivos ni abreviaturas internas (solo el ultimo caracter)",
        _quitar_punto_final("Cliente Sr. Perez, llamar hoy.") == "Cliente Sr. Perez, llamar hoy",
    )

    if _falla:
        print(f"\n{len(_falla)} test(s) fallaron: {_falla}")
        return 1
    print("\nTodos los tests de agentes (red de seguridad) pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
