"""
Validacion programatica del formato de salida del Agente 4, critica para
la validez del estudio (panel ciego). Se valida ANTES de escribir cada
fila al CSV.

Reglas:
  - Limite de palabras por campo (recomendacion, accion, justificacion).
  - Prohibido markdown/formato: vinetas, negritas, encabezados, emojis,
    listas numeradas.
  - Prohibido usar palabras de la lista de tono "consultor/IA".
  - Prohibido filtrar cifras exactas de RFM del caso (recency/frequency/
    monetary) disfrazadas de texto de venta. Es una heuristica que
    compara numeros sueltos en el texto contra los valores reales del
    caso, no una prohibicion generica de numeros (el campo `plazo`
    legitimamente lleva numeros).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from collections import Counter

from config import (
    CAMPOS_SALIDA,
    LIMITE_PALABRAS_ACCION,
    LIMITE_PALABRAS_JUSTIFICACION,
    LIMITE_PALABRAS_RECOMENDACION,
    MAX_REPETICION_LITERAL_PCT,
    PALABRAS_PROHIBIDAS,
)

LIMITES_PALABRAS = {
    "recomendacion": LIMITE_PALABRAS_RECOMENDACION,
    "accion": LIMITE_PALABRAS_ACCION,
    "justificacion": LIMITE_PALABRAS_JUSTIFICACION,
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

_PATRON_NUMERO_CON_UNIDAD = re.compile(
    r"(\d[\d.,]*)\s*(d[ií]as?|transacciones|compras)\b", re.IGNORECASE
)
_PATRON_MONTO = re.compile(r"\$\s*([\d.,]+)")


@dataclass
class ResultadoValidacion:
    valido: bool
    errores: list[str] = field(default_factory=list)


def _contar_palabras(texto: str) -> int:
    return len([p for p in re.split(r"\s+", texto.strip()) if p])


def _validar_limite_palabras(campo: str, valor: str, errores: list[str]) -> None:
    limite = LIMITES_PALABRAS.get(campo)
    if limite is None:
        return
    n = _contar_palabras(valor)
    if n > limite:
        errores.append(f"'{campo}' excede el limite de {limite} palabras (tiene {n})")


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


def _validar_palabras_prohibidas(campo: str, valor: str, errores: list[str]) -> None:
    valor_lower = valor.lower()
    for palabra in PALABRAS_PROHIBIDAS:
        patron = re.compile(rf"\b{re.escape(palabra.lower())}\b")
        if patron.search(valor_lower):
            errores.append(f"'{campo}' usa la palabra prohibida '{palabra}'")


def _validar_fuga_rfm(
    campo: str, valor: str, recency_dias: float, frequency: float, monetary_usd: float, errores: list[str]
) -> None:
    """Heuristica: si aparece un numero seguido de 'dias'/'transacciones'/
    'compras', o un monto en $, que coincide (aprox.) con los valores
    reales del caso, se considera fuga de cifra exacta de RFM."""

    def _num_de(s: str) -> float | None:
        s = s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None

    for match in _PATRON_NUMERO_CON_UNIDAD.finditer(valor):
        numero = _num_de(match.group(1))
        if numero is None:
            continue
        if (
            _aprox_igual(numero, recency_dias)
            or _aprox_igual(numero, frequency)
        ):
            errores.append(
                f"'{campo}' filtra una cifra RFM del caso ('{match.group(0).strip()}')"
            )

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
    umbral_pct: float = MAX_REPETICION_LITERAL_PCT,
) -> ResultadoAntiPlantilla:
    """Verifica, a nivel de CORRIDA completa (no por caso), si algun campo
    repite el mismo valor literal en mas del umbral_pct de las filas.

    Esto es una validacion de sistema, no de caso individual: si el
    sistema esta razonando por cliente, la redaccion deberia variar aunque
    la ACCION elegida se repita. Una repeticion literal alta en
    'recomendacion' o 'justificacion' indica que el generador esta
    aplicando una plantilla de texto fija, lo cual rompe el cegado del
    panel humano vs. IA (ver agentes.py, Agente 3/4)."""
    n = len(filas)
    repeticiones: dict[str, dict[str, int]] = {}
    if n == 0:
        return ResultadoAntiPlantilla(valida=True, repeticiones={})

    for campo in campos:
        conteo = Counter(fila[campo] for fila in filas if fila.get(campo))
        excedidos = {valor: c for valor, c in conteo.items() if (c / n) > umbral_pct}
        if excedidos:
            repeticiones[campo] = excedidos

    return ResultadoAntiPlantilla(valida=(len(repeticiones) == 0), repeticiones=repeticiones)


def validar_salida_agente4(
    salida: dict,
    recency_dias: float,
    frequency: float,
    monetary_usd: float,
) -> ResultadoValidacion:
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
        _validar_fuga_rfm(campo, valor, recency_dias, frequency, monetary_usd, errores)

    # 'plazo' solo se valida por formato basico (sin vinetas/markdown/emoji),
    # no por limite de palabras ni por fuga RFM (es una expresion de tiempo).
    _validar_formato_prohibido("plazo", salida["plazo"], errores)

    return ResultadoValidacion(valido=(len(errores) == 0), errores=errores)
