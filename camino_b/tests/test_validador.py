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

from validador import detectar_repeticion_plantilla, validar_salida_agente4

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
        "recomendacion": "Llámalo esta semana y ofrecele la promocion de vinos vigente antes de que se enfrie la relacion",
        "accion": "Llamada telefonica",
        "plazo": "8 dias",
        "justificacion": "Hace varios meses que no compra y suele responder bien a promociones de vinos",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check("caso valido pasa sin errores", r.valido, str(r.errores))


def test_excede_limite_palabras_recomendacion():
    salida = {
        "recomendacion": " ".join(["palabra"] * 30),
        "accion": "Llamar por telefono y ofrecer la promocion vigente.",
        "plazo": "8 dias",
        "justificacion": "Justificacion corta y valida para este cliente en particular.",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "recomendacion de 30 palabras falla por limite (25)",
        not r.valido and any("recomendacion" in e and "limite" in e for e in r.errores),
        str(r.errores),
    )


def test_excede_limite_palabras_accion():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos antes de que se enfrie la relacion comercial.",
        "accion": " ".join(["palabra"] * 15),
        "plazo": "8 dias",
        "justificacion": "Justificacion corta y valida para este cliente en particular.",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "accion de 15 palabras falla por limite (4)",
        not r.valido and any("'accion'" in e and "limite" in e for e in r.errores),
        str(r.errores),
    )


def test_justificacion_bajo_minimo_falla():
    # Rango [8, 16] desde 2026-08-14 (ver config.py): sin piso, el sistema
    # convergia a notas mas largas que EH2, densidad visual distinta.
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos",
        "accion": "Llamada",
        "plazo": "8 dias",
        "justificacion": "Cliente inactivo, ofrecerle promocion",  # 4 palabras
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "justificacion de 4 palabras falla por el minimo de 8",
        not r.valido and any("'justificacion'" in e and "minimo" in e for e in r.errores),
        str(r.errores),
    )


def test_justificacion_sobre_maximo_falla():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos",
        "accion": "Llamada",
        "plazo": "8 dias",
        "justificacion": " ".join(["palabra"] * 17),
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "justificacion de 17 palabras falla por el nuevo limite de 16",
        not r.valido and any("'justificacion'" in e and "limite" in e for e in r.errores),
        str(r.errores),
    )


def test_justificacion_dentro_de_rango_pasa():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos",
        "accion": "Llamada",
        "plazo": "8 dias",
        "justificacion": " ".join(["palabra"] * 12),  # dentro de [8, 16]
    }
    r = validar_salida_agente4(salida, MONETARY)
    check("justificacion de 12 palabras (dentro de [8,16]) pasa", r.valido, str(r.errores))


def test_accion_de_5_palabras_falla_limite_nuevo():
    # Limite bajado de 12 a 4 el 2026-08-14 (ver config.py): 'accion' debe
    # ser un canal, no una descripcion. 5 palabras ya es demasiado.
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos",
        "accion": "Llamar por telefono al cliente",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "accion de 5 palabras falla por el nuevo limite de 4",
        not r.valido and any("'accion'" in e and "limite" in e for e in r.errores),
        str(r.errores),
    )


def test_accion_de_4_palabras_pasa():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos",
        "accion": "Correo de verificacion breve",  # 4 palabras, justo en el limite
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check("accion de 4 palabras (limite inclusive) pasa", r.valido, str(r.errores))


def test_vinetas_prohibidas():
    salida = {
        "recomendacion": "- Llamarlo\n- Ofrecerle la promocion vigente de vinos que le puede interesar mucho",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "vinetas de lista son rechazadas",
        not r.valido and any("vineta" in e for e in r.errores),
        str(r.errores),
    )


def test_negrita_markdown_prohibida():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele **la promocion vigente de vinos** antes de que se enfrie la relacion.",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "negrita markdown es rechazada",
        not r.valido and any("negrita" in e for e in r.errores),
        str(r.errores),
    )


def test_emoji_prohibido():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos 🍷 antes de que se enfrie la relacion.",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular.",
    }
    r = validar_salida_agente4(salida, MONETARY)
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
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "'optimizar' es rechazada",
        not r.valido and any("optimizar" in e for e in r.errores),
        str(r.errores),
    )


def test_palabra_prohibida_no_hace_falso_positivo_por_subcadena():
    # "clave" prohibida como palabra completa, no debe disparar en "declive"
    salida = {
        "recomendacion": "Llámalo esta semana porque su interes esta en declive y podria responder bien a una promocion vigente",
        "accion": "Llamada",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "'declive' no dispara falso positivo de 'clave'",
        r.valido,
        str(r.errores),
    )


def test_citar_dias_del_perfil_ya_no_se_rechaza():
    # Hasta el 2026-08-14 este campo se rechazaba (fuga de RFM). Medir el
    # corpus real de expertos mostro que EH2 cita "N dias sin comprar" en
    # 6/15 casos (40%, sistematico) -- prohibirselo al sistema alejaba su
    # registro del humano en vez de acercarlo, y era ademas un eje de fuga
    # perfecto para el panel ciego. Ver validador.py docstring del modulo.
    salida = {
        "recomendacion": "Llámalo porque lleva 159 dias sin comprar y podria interesarle la promocion vigente de vinos",
        "accion": "Llamada",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "citar '159 dias' (cifra de recencia real del caso) ya no se rechaza",
        r.valido,
        str(r.errores),
    )


def test_fuga_monto_exacto():
    # El monto SI se sigue bloqueando: ningun experto (EH1 ni EH2) lo cita
    # nunca en el corpus real, a diferencia de dias/frecuencia.
    salida = {
        "recomendacion": "Llámalo esta semana, historicamente compro $1401 y podria interesarle la promocion vigente de vinos",
        "accion": "Llamada",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "monto exacto ($1401) es rechazado",
        not r.valido and any("filtra" in e for e in r.errores),
        str(r.errores),
    )


def test_plazo_con_numero_no_dispara_fuga():
    # El plazo SI puede tener numeros propios de la accion, no del perfil.
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos antes de que se enfrie la relacion",
        "accion": "Llamada",
        "plazo": "15 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "plazo con numero propio de la accion (15 dias, no es RFM) no dispara fuga",
        r.valido,
        str(r.errores),
    )


def test_punto_final_es_rechazado():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos.",
        "accion": "Llamar por telefono y ofrecer la promocion vigente",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "'recomendacion' con punto final es rechazada",
        not r.valido and any("termina en punto" in e for e in r.errores),
        str(r.errores),
    )


def test_plazo_vago_es_rechazado():
    # Reproduce el defecto real: "en las proximas semanas" no tiene numero.
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos",
        "accion": "Llamar por telefono y ofrecer la promocion vigente",
        "plazo": "En las proximas semanas",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "plazo vago sin numero ('en las proximas semanas') es rechazado",
        not r.valido and any("no es una cifra concreta" in e for e in r.errores),
        str(r.errores),
    )


def test_plazo_lo_antes_posible_es_rechazado():
    # Reproduce el otro defecto real: "lo antes posible." (sin numero, con punto).
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos",
        "accion": "Llamar por telefono y ofrecer la promocion vigente",
        "plazo": "Lo antes posible.",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "'lo antes posible.' es rechazado (sin numero y con punto final)",
        not r.valido
        and any("no es una cifra concreta" in e for e in r.errores)
        and any("termina en punto" in e for e in r.errores),
        str(r.errores),
    )


def test_plazo_fuera_de_rango_es_rechazado():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos",
        "accion": "Llamar por telefono y ofrecer la promocion vigente",
        "plazo": "2 dias",  # bajo el minimo de 3
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "plazo de 2 dias (bajo el minimo de 3) es rechazado",
        not r.valido and any("fuera del rango esperable" in e for e in r.errores),
        str(r.errores),
    )

    salida["plazo"] = "2 meses"  # 60 dias equivalentes, sobre el maximo de 30
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "plazo de 2 meses (sobre el maximo de 30 dias) es rechazado",
        not r.valido and any("fuera del rango esperable" in e for e in r.errores),
        str(r.errores),
    )


def test_plazo_1_mes_en_el_limite_pasa():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos",
        "accion": "Llamada",
        "plazo": "1 mes",  # 30 dias, justo en el limite superior
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check("plazo '1 mes' (30 dias, limite superior inclusive) pasa", r.valido, str(r.errores))


def test_palabra_prohibida_crucial():
    # Reproduce el registro de "informe" detectado en una corrida real:
    # "Es crucial contactar al cliente..." -- ningun vendedor escribe asi.
    salida = {
        "recomendacion": "Es crucial contactar al cliente para ofrecerle la promocion vigente de vinos",
        "accion": "Llamada",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "'crucial' es rechazada (registro de informe, no de vendedor)",
        not r.valido and any("crucial" in e for e in r.errores),
        str(r.errores),
    )


def test_palabra_prohibida_personalizado():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele productos personalizados de la linea de vinos",
        "accion": "Llamada",
        "plazo": "8 dias",
        "justificacion": "Es una recomendacion clara para reactivar a este cliente en particular",
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "'personalizado' es rechazada",
        not r.valido and any("personalizado" in e for e in r.errores),
        str(r.errores),
    )


def test_campo_faltante():
    salida = {
        "recomendacion": "Llámalo esta semana y ofrecele la promocion vigente de vinos antes de que se enfrie la relacion.",
        "accion": "Llamar por telefono al cliente.",
        "plazo": "8 dias",
        # falta 'justificacion'
    }
    r = validar_salida_agente4(salida, MONETARY)
    check(
        "campo faltante ('justificacion') es rechazado",
        not r.valido and any("justificacion" in e for e in r.errores),
        str(r.errores),
    )


def test_antiplantilla_detecta_repeticion_excesiva():
    # Reproduce el patron real de la corrida 2026-08-14: 9/15 'recomendacion'
    # identica, muy por encima del limite absoluto por defecto (3).
    filas = [{"recomendacion": "Realizar un seguimiento ligero.", "accion": "x", "plazo": "y", "justificacion": "z"}] * 9
    filas += [{"recomendacion": f"Recomendacion distinta {i}.", "accion": "x", "plazo": "y", "justificacion": "z"} for i in range(6)]
    r = detectar_repeticion_plantilla(filas)
    check(
        "9/15 (60%) de 'recomendacion' identica se detecta y marca la corrida invalida",
        not r.valida and "recomendacion" in r.repeticiones,
        str(r.repeticiones),
    )
    check(
        "el conteo reportado para la frase repetida es 9",
        r.repeticiones.get("recomendacion", {}).get("Realizar un seguimiento ligero.") == 9,
    )


def test_antiplantilla_no_dispara_con_variacion_normal():
    # 15 casos: 'recomendacion'/'accion'/'justificacion' repiten a lo sumo
    # 3 veces cada valor (limite por defecto, no excede: estricto '>'), y
    # 'plazo' repite "2 semanas" 5 veces (justo el limite mas laxo para
    # ese campo, tampoco excede).
    filas = [
        {
            "recomendacion": f"Recomendacion {i % 5}",
            "accion": f"Accion {i % 5}",
            "plazo": "2 semanas" if i < 5 else f"{i} dias",
            "justificacion": f"Justificacion {i % 5}",
        }
        for i in range(15)
    ]
    r = detectar_repeticion_plantilla(filas)
    check("variacion normal (repeticion en el limite permitido) no marca la corrida invalida", r.valida, str(r.repeticiones))


def test_antiplantilla_lista_vacia_no_revienta():
    r = detectar_repeticion_plantilla([])
    check("lista vacia de filas es valida por definicion (nada que evaluar)", r.valida)


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
