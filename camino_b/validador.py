"""
Validacion programatica del formato de salida del Agente 4, critica para
la validez del estudio (panel ciego). Se valida ANTES de escribir cada
fila al CSV.

Reglas:
  - Limite de palabras por campo (recomendacion, accion, justificacion).
    'justificacion' tambien tiene un MINIMO (8) ademas del maximo (16),
    desde 2026-08-14: sin piso, el sistema convergia a notas mas largas
    que EH2 en promedio (15.9 vs 13.6 palabras) -- suficiente para verse
    como "un bloque mas denso" en el panel aunque los rangos solaparan.
  - Prohibido markdown/formato: vinetas, negritas, encabezados, emojis,
    listas numeradas.
  - Prohibido usar palabras de la lista de tono "consultor/IA".
  - Prohibido filtrar el MONTO exacto del caso disfrazado de texto de
    venta (heuristica: compara numeros en $ contra monetary_usd real).
    Citar dias/frecuencia SI esta permitido desde 2026-08-14 (ver
    prompts/generador.md): la version anterior de este validador
    tambien rechazaba esas cifras, pero medir el corpus real de
    expertos mostro que EH2 cita "N dias sin comprar" o "sus N compras
    anteriores" en 6/15 casos (40%, sistematico) -- prohibirselo al
    sistema alejaba su registro del humano en vez de acercarlo, y
    ademas era un eje de fuga perfecto para el panel ciego (la opcion
    que citaba una cifra siempre era la humana). El monto en dolares se
    mantiene bloqueado porque ningun experto (EH1 ni EH2) lo cita nunca
    en el corpus real -- no hay precedente humano que lo justifique.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from collections import Counter

from config import (
    CAMPOS_SALIDA,
    LIMITE_PALABRAS_ACCION,
    LIMITE_PALABRAS_JUSTIFICACION,
    LIMITE_PALABRAS_JUSTIFICACION_MIN,
    LIMITE_PALABRAS_RECOMENDACION,
    MAX_REPETICION_ABSOLUTA,
    MAX_REPETICION_ABSOLUTA_PLAZO,
    PALABRAS_PROHIBIDAS,
    PLAZO_MAX_DIAS,
    PLAZO_MIN_DIAS,
)

LIMITES_PALABRAS = {
    "recomendacion": LIMITE_PALABRAS_RECOMENDACION,
    "accion": LIMITE_PALABRAS_ACCION,
    "justificacion": LIMITE_PALABRAS_JUSTIFICACION,
}

# Solo 'justificacion' tiene piso ademas de techo: la densidad visual
# (2026-08-14) mostro que sin minimo el sistema convergia a notas mas
# largas que EH2 de forma sistematica.
MINIMOS_PALABRAS = {
    "justificacion": LIMITE_PALABRAS_JUSTIFICACION_MIN,
}

# Campos sobre los que aplica el chequeo de formato/tono/fuga de RFM.
# 'plazo' se excluye porque es una expresion de tiempo corta, no una
# oracion, y legitimamente contiene numeros.
CAMPOS_ESTILO = ("recomendacion", "accion", "justificacion")

_PATRON_VINETA = re.compile(r"(^|\n)\s*[-*•]\s+")
_PATRON_LISTA_NUMERADA = re.compile(r"(^|\n)\s*\d+[.)]\s+")
_PATRON_NEGRITA_MD = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__)")
_PATRON_ENCABEZADO_MD = re.compile(r"(^|\n)\s*#{1,6}\s+")
_PATRON_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "]"
)

_PATRON_MONTO = re.compile(r"\$\s*([\d.,]+)")

# El campo 'plazo' debe ser CONCRETO: numero + unidad temporal (dias,
# semanas, mes/meses), sin texto adicional. "En las proximas semanas" o
# "lo antes posible" no matchean (no tienen numero) y fallan la validacion.
_PATRON_PLAZO_CONCRETO = re.compile(
    r"^\s*(\d+)\s*(d[ií]as?|semanas?|mes(?:es)?)\s*$", re.IGNORECASE
)
_DIAS_POR_UNIDAD = {"dia": 1, "día": 1, "dias": 1, "días": 1, "semana": 7, "semanas": 7, "mes": 30, "meses": 30}


@dataclass
class ResultadoValidacion:
    valido: bool
    errores: list[str] = field(default_factory=list)


def _contar_palabras(texto: str) -> int:
    return len([p for p in re.split(r"\s+", texto.strip()) if p])


def _validar_limite_palabras(campo: str, valor: str, errores: list[str]) -> None:
    n = _contar_palabras(valor)
    limite = LIMITES_PALABRAS.get(campo)
    if limite is not None and n > limite:
        errores.append(f"'{campo}' excede el limite de {limite} palabras (tiene {n})")
    minimo = MINIMOS_PALABRAS.get(campo)
    if minimo is not None and n < minimo:
        errores.append(f"'{campo}' no llega al minimo de {minimo} palabras (tiene {n})")


def _validar_formato_prohibido(campo: str, valor: str, errores: list[str]) -> None:
    if _PATRON_VINETA.search(valor):
        errores.append(f"'{campo}' contiene vinetas de lista")
    if _PATRON_LISTA_NUMERADA.search(valor):
        errores.append(f"'{campo}' contiene una lista numerada")
    if _PATRON_NEGRITA_MD.search(valor):
        errores.append(f"'{campo}' contiene negrita markdown")
    if _PATRON_ENCABEZADO_MD.search(valor):
        errores.append(f"'{campo}' contiene un encabezado markdown")
    if _PATRON_EMOJI.search(valor):
        errores.append(f"'{campo}' contiene emojis")


def _validar_sin_punto_final(campo: str, valor: str, errores: list[str]) -> None:
    """Ningun campo debe terminar en punto -- coincide con el registro
    telegrafico observado en las recomendaciones de los expertos humanos
    (ver casos_15_expertos.csv, consultado SOLO para calibrar este
    validador, nunca cargado en el contexto de ningun agente).

    Red de respaldo: agentes.agente4_generador ya recorta el punto final
    de forma deterministica antes de que este validador vea la salida
    (el LLM no lo evitaba de forma confiable via instruccion sola, agoto
    reintentos por esto solo). Este chequeo queda como respaldo por si
    algun otro caller construye la salida sin pasar por ese recorte."""
    if valor.rstrip().endswith("."):
        errores.append(f"'{campo}' termina en punto ('{valor.rstrip()[-15:]}')")


def _validar_plazo_concreto(valor: str, errores: list[str]) -> None:
    """El campo 'plazo' debe ser numero + unidad temporal concreta
    (dias/semanas/mes), dentro del rango [PLAZO_MIN_DIAS, PLAZO_MAX_DIAS].
    Expresiones vagas como 'en las proximas semanas' o 'lo antes posible'
    no tienen un numero y fallan aqui."""
    match = _PATRON_PLAZO_CONCRETO.match(valor)
    if not match:
        errores.append(f"'plazo' no es una cifra concreta (numero + unidad): '{valor}'")
        return

    numero = int(match.group(1))
    unidad = match.group(2).lower()
    dias_por_unidad = _DIAS_POR_UNIDAD.get(unidad)
    if dias_por_unidad is None:
        # Cubre variantes plurales/singulares no listadas explicitamente
        # (p.ej. 'meses' ya cubierto, pero por robustez).
        if unidad.startswith("d"):
            dias_por_unidad = 1
        elif unidad.startswith("semana"):
            dias_por_unidad = 7
        else:
            dias_por_unidad = 30

    dias_equivalentes = numero * dias_por_unidad
    if not (PLAZO_MIN_DIAS <= dias_equivalentes <= PLAZO_MAX_DIAS):
        errores.append(
            f"'plazo' ('{valor}' ~= {dias_equivalentes} dias) fuera del rango esperable "
            f"[{PLAZO_MIN_DIAS}, {PLAZO_MAX_DIAS}] dias"
        )


def _validar_palabras_prohibidas(campo: str, valor: str, errores: list[str]) -> None:
    valor_lower = valor.lower()
    for palabra in PALABRAS_PROHIBIDAS:
        p = palabra.lower()
        # Tolera el plural simple en 's' para entradas de una sola palabra
        # (relevante/relevantes, adecuado/adecuados, personalizado/
        # personalizados...). No se aplica a frases de varias palabras.
        sufijo_plural = "" if " " in p else "s?"
        patron = re.compile(rf"\b{re.escape(p)}{sufijo_plural}\b")
        if patron.search(valor_lower):
            errores.append(f"'{campo}' usa la palabra prohibida '{palabra}'")


def _validar_fuga_monto(campo: str, valor: str, monetary_usd: float, errores: list[str]) -> None:
    """Heuristica: si aparece un monto en $ que coincide (aprox.) con el
    monetary_usd real del caso, se considera fuga. Citar dias/frecuencia
    ya NO se valida aqui -- esta permitido desde 2026-08-14, ver
    docstring del modulo."""

    def _num_de(s: str) -> float | None:
        s = s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None

    for match in _PATRON_MONTO.finditer(valor):
        numero = _num_de(match.group(1))
        if numero is None:
            continue
        if _aprox_igual(numero, monetary_usd):
            errores.append(
                f"'{campo}' filtra el monto exacto del caso ('{match.group(0).strip()}')"
            )


def _aprox_igual(a: float, b: float, tolerancia: float = 0.5) -> bool:
    return abs(a - b) <= tolerancia


@dataclass
class ResultadoAntiPlantilla:
    valida: bool
    repeticiones: dict[str, dict[str, int]] = field(default_factory=dict)


def detectar_repeticion_plantilla(
    filas: list[dict],
    campos: tuple[str, ...] = CAMPOS_SALIDA,
    limite_por_defecto: int = MAX_REPETICION_ABSOLUTA,
    limite_plazo: int = MAX_REPETICION_ABSOLUTA_PLAZO,
) -> ResultadoAntiPlantilla:
    """Verifica, a nivel de CORRIDA completa (no por caso), si algun campo
    repite el mismo valor literal mas de `limite_por_defecto` veces (mas
    de `limite_plazo` para el campo 'plazo', que tiene un vocabulario
    razonable mas chico -- "15 dias" es legitimo en varios casos sin ser
    plantilla).

    Umbral en CONTEO ABSOLUTO, calibrado para N=15 (no tiene sentido con N
    chico: cualquier reparto 50/50 en un piloto de 2 casos dispara el
    umbral por definicion -- el llamador debe omitir esta verificacion
    fuera de la corrida completa).

    Esto es una validacion de sistema, no de caso individual: si el
    sistema esta razonando por cliente, la redaccion deberia variar aunque
    la ACCION elegida se repita. Una repeticion literal alta en
    'recomendacion' o 'justificacion' indica que el generador esta
    aplicando una plantilla de texto fija, lo cual rompe el cegado del
    panel humano vs. IA (ver agentes.py, Agente 3/4)."""
    repeticiones: dict[str, dict[str, int]] = {}

    for campo in campos:
        limite = limite_plazo if campo == "plazo" else limite_por_defecto
        conteo = Counter(fila[campo] for fila in filas if fila.get(campo))
        excedidos = {valor: c for valor, c in conteo.items() if c > limite}
        if excedidos:
            repeticiones[campo] = excedidos

    return ResultadoAntiPlantilla(valida=(len(repeticiones) == 0), repeticiones=repeticiones)


def validar_salida_agente4(salida: dict, monetary_usd: float) -> ResultadoValidacion:
    errores: list[str] = []

    for campo in CAMPOS_SALIDA:
        if campo not in salida or not isinstance(salida[campo], str) or not salida[campo].strip():
            errores.append(f"falta el campo '{campo}' o esta vacio")

    if errores:
        return ResultadoValidacion(valido=False, errores=errores)

    for campo in CAMPOS_ESTILO:
        valor = salida[campo]
        _validar_limite_palabras(campo, valor, errores)
        _validar_formato_prohibido(campo, valor, errores)
        _validar_palabras_prohibidas(campo, valor, errores)
        _validar_fuga_monto(campo, valor, monetary_usd, errores)
        _validar_sin_punto_final(campo, valor, errores)

    # 'plazo' no lleva limite de palabras ni chequeo de fuga RFM (es una
    # expresion de tiempo, no una oracion), pero si formato basico, sin
    # punto final, y la regla propia de concrecion (numero + unidad,
    # dentro de rango).
    _validar_formato_prohibido("plazo", salida["plazo"], errores)
    _validar_sin_punto_final("plazo", salida["plazo"], errores)
    _validar_plazo_concreto(salida["plazo"], errores)

    return ResultadoValidacion(valido=(len(errores) == 0), errores=errores)
