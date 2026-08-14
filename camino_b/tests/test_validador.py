"""
Smoke tests del validador de formato de salida (Agente 4).

No requieren OPENAI_API_KEY ni datos de casos reales: los ejemplos de
texto son sinteticos, inventados para este test, y NO se derivan de
casos_15_expertos.csv.

Uso:
    python -m tests.test_validador
  (o, si pytest esta instalado: pytest tests/test_validador.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validador import validar_salida_agente4

# Caso sintetico de referencia para el chequeo de fuga de RFM.
RECENCY = 159.0
FREQUENCY = 5.0
MONETARY = 1401.30

_falla = []


def check(nombre: str, condicion: bool, detalle: str = "") -> None:
    estado = "OK  " if condicion else "FAIL"
    print(f"[{estado}] {nombre}" + (f" -- {detalle}" if detalle and not condicion else ""))
    if not condicion:
        _falla.append(nombre)


def test_caso_valido_pasa():
    salida = {
        "recomendacion": "Llamalo esta semana y ofrecele la promocion de vinos vigente antes de que se enfrie la relacion.",
        "accion": "Llamar por telefono y presentar la promocion vigente de vinos.",
        "plazo": "8 dias",
        "justificacion": "Hace varios meses que no compra y suele responder bien a promociones de vinos.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check("caso valido pasa sin errores", r.valido, str(r.errores))


def test_excede_limite_palabras_recomendacion():
    salida = {
        "recomendacion": " ".join(["palabra"] * 30),
        "accion": "Llamar por telefono y ofrecer la promocion vigente.",
        "plazo": "8 dias",
        "justificacion": "Justificacion corta y valida para este cliente en particular.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "recomendacion de 30 palabras falla por limite (25)",
        not r.valido and any("recomendacion" in e and "limite" in e for e in r.errores),
        str(r.errores),
    )


def test_excede_limite_palabras_accion():
    salida = {
        "recomendacion": "Llamalo esta semana y ofrecele la promocion vigente de vinos antes de que se enfrie la relacion comercial.",
        "accion": " ".join(["palabra"] * 15),
        "plazo": "8 dias",
        "justificacion": "Justificacion corta y valida para este cliente en particular.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "accion de 15 palabras falla por limite (12)",
        not r.valido and any("'accion'" in e and "limite" in e for e in r.errores),
        str(r.errores),
    )


def test_vinetas_prohibidas():
    salida = {
        "recomendacion": "- Llamarlo\n- Ofrecerle la promocion vigente de vinos que le puede interesar mucho",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "vinetas de lista son rechazadas",
        not r.valido and any("vineta" in e for e in r.errores),
        str(r.errores),
    )


def test_negrita_markdown_prohibida():
    salida = {
        "recomendacion": "Llamalo esta semana y ofrecele **la promocion vigente de vinos** antes de que se enfrie la relacion.",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "negrita markdown es rechazada",
        not r.valido and any("negrita" in e for e in r.errores),
        str(r.errores),
    )


def test_emoji_prohibido():
    salida = {
        "recomendacion": "Llamalo esta semana y ofrecele la promocion vigente de vinos 🍷 antes de que se enfrie la relacion.",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "emoji es rechazado",
        not r.valido and any("emoji" in e for e in r.errores),
        str(r.errores),
    )


def test_palabra_prohibida_optimizar():
    salida = {
        "recomendacion": "Hay que optimizar el contacto con este cliente ofreciendole la promocion vigente de vinos esta semana.",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "'optimizar' es rechazada",
        not r.valido and any("optimizar" in e for e in r.errores),
        str(r.errores),
    )


def test_palabra_prohibida_no_hace_falso_positivo_por_subcadena():
    # "clave" prohibida como palabra completa, no debe disparar en "declive"
    salida = {
        "recomendacion": "Llamalo esta semana porque su interes esta en declive y podria responder bien a una promocion vigente.",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "'declive' no dispara falso positivo de 'clave'",
        r.valido,
        str(r.errores),
    )


def test_fuga_recencia_exacta():
    salida = {
        "recomendacion": "Llamalo porque lleva 159 dias sin comprar y podria interesarle la promocion vigente de vinos.",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "cifra exacta de recencia (159 dias) es rechazada",
        not r.valido and any("filtra" in e for e in r.errores),
        str(r.errores),
    )


def test_fuga_monto_exacto():
    salida = {
        "recomendacion": "Llamalo esta semana, historicamente compro $1401 y podria interesarle la promocion vigente de vinos.",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "monto exacto ($1401) es rechazado",
        not r.valido and any("filtra" in e for e in r.errores),
        str(r.errores),
    )


def test_plazo_con_numero_no_dispara_fuga():
    # El plazo SI puede tener numeros propios de la accion, no del perfil.
    salida = {
        "recomendacion": "Llamalo esta semana y ofrecele la promocion vigente de vinos antes de que se enfrie la relacion.",
        "accion": "Llamar por telefono y ofrecer la promocion vigente.",
        "plazo": "15 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "plazo con numero propio de la accion (15 dias, no es RFM) no dispara fuga",
        r.valido,
        str(r.errores),
    )


def test_campo_faltante():
    salida = {
        "recomendacion": "Llamalo esta semana y ofrecele la promocion vigente de vinos antes de que se enfrie la relacion.",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        # falta 'justificacion'
    }
    r = validar_salida_agente4(salida, RECENCY, FREQUENCY, MONETARY)
    check(
        "campo faltante ('justificacion') es rechazado",
        not r.valido and any("justificacion" in e for e in r.errores),
        str(r.errores),
    )


def main() -> int:
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            fn()
    if _falla:
        print(f"\n{len(_falla)} test(s) fallaron: {_falla}")
        return 1
    print("\nTodos los tests del validador pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
