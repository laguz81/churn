"""
app.py

Aplicacion Flask de evaluacion ciega A/B (panel de evaluadores humanos).

Reglas de diseno criticas (ver especificacion del estudio):
  - Sin login: el token en la URL es la unica credencial.
  - Solo lectura: nunca se editan las recomendaciones mostradas.
  - Nunca se revela la fuente: en ninguna respuesta HTTP (HTML, JSON,
    encabezados, comentarios, atributos data-, JS visible en consola)
    deben aparecer las palabras "sistema", "IA", "EH1", "EH2", "experto"
    o similares en las rutas de cara al evaluador. Solo "A" y "B".
  - Un caso a la vez, en orden ascendente de id_caso, sin poder volver
    atras ni re-ver/re-calificar un caso ya enviado.
  - Token invalido -> pagina generica tipo 404, sin distinguir motivos.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

import db

BASE_DIR = Path(__file__).resolve().parent

DATOS_DIR = Path(os.environ.get("DATOS_DIR", BASE_DIR / "datos"))
SECRETO_DIR = Path(os.environ.get("SECRETO_DIR", BASE_DIR / "secreto"))
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "data" / "respuestas.db"))

CRITERIOS = ("relevancia", "viabilidad")
ETIQUETAS = ("A", "B")

RELEVANCIA_ANCLAS = {
    1: "Nada pertinente. Serviría para cualquier cliente o no aplica a este caso.",
    2: "Poco pertinente.",
    3: "Medianamente pertinente. Aplica, pero de forma general.",
    4: "Pertinente.",
    5: "Muy pertinente. Responde a la situación específica de este cliente.",
}
VIABILIDAD_ANCLAS = {
    1: "Nada viable. No se puede ejecutar como está planteada.",
    2: "Poco viable. Requeriría autorizaciones o recursos no disponibles.",
    3: "Medianamente viable. Ejecutable con ajustes.",
    4: "Viable.",
    5: "Muy viable. Ejecutable de inmediato, tal como está descrita.",
}

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)


# ---------------------------------------------------------------------------
# Carga de datos no secretos / secretos (releida en cada arranque; los
# archivos son pequenos y se regeneran solo al correr preparar_evaluacion.py,
# no hace falta cache de proceso mas alla de un simple lazy-load con reintento)
# ---------------------------------------------------------------------------


class DatosNoDisponibles(RuntimeError):
    pass


def _cargar_json(path: Path) -> dict:
    if not path.exists():
        raise DatosNoDisponibles(f"No existe {path}. Ejecuta preparar_evaluacion.py primero.")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def cargar_evaluadores() -> dict:
    return _cargar_json(DATOS_DIR / "evaluadores.json")


def cargar_casos_contenido() -> dict:
    return _cargar_json(DATOS_DIR / "casos.json")


def cargar_decode() -> dict:
    return _cargar_json(SECRETO_DIR / "decode.json")


db.init_db(DB_PATH)


# ---------------------------------------------------------------------------
# Helpers de dominio
# ---------------------------------------------------------------------------


def _resolver_token(token: str):
    """Devuelve (info_evaluador, casos_ids) o None si el token no existe."""
    try:
        evaluadores = cargar_evaluadores()
    except DatosNoDisponibles:
        return None
    info = evaluadores.get(token)
    if info is None:
        return None
    return info


def _siguiente_caso_pendiente(token: str, casos_ids: list[int]) -> int | None:
    with db.connect(DB_PATH) as conn:
        respondidos = db.casos_respondidos(conn, token)
    for id_caso in casos_ids:
        if id_caso not in respondidos:
            return id_caso
    return None


def _construir_opciones(token: str, id_caso: int) -> tuple[dict, dict]:
    """Devuelve (opcion_a, opcion_b) ya resueltas por el decode, sin exponer la fuente."""
    decode = cargar_decode()
    contenido = cargar_casos_contenido()

    mapa_token = decode.get(token)
    if mapa_token is None:
        abort(404)
    mapa_caso = mapa_token.get(str(id_caso))
    if mapa_caso is None:
        abort(404)

    ficha_caso = contenido.get(str(id_caso))
    if ficha_caso is None:
        abort(404)

    fuente_a = mapa_caso["A"]
    fuente_b = mapa_caso["B"]

    opcion_a = dict(ficha_caso[fuente_a])
    opcion_b = dict(ficha_caso[fuente_b])
    return opcion_a, opcion_b


def _perfil_caso(id_caso: int) -> dict:
    contenido = cargar_casos_contenido()
    ficha = contenido.get(str(id_caso))
    if ficha is None:
        abort(404)
    return ficha["perfil"]


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------


@app.errorhandler(404)
def no_encontrado(_error):
    return render_template("no_encontrado.html"), 404


@app.route("/e/<token>/")
def entrada(token: str):
    info = _resolver_token(token)
    if info is None:
        abort(404)

    casos_ids = info["casos"]
    siguiente = _siguiente_caso_pendiente(token, casos_ids)
    if siguiente is None:
        return redirect(url_for("gracias", token=token, _external=True))
    return redirect(url_for("ver_caso", token=token, id_caso=siguiente, _external=True))


@app.route("/e/<token>/caso/<int:id_caso>", methods=["GET"])
def ver_caso(token: str, id_caso: int):
    info = _resolver_token(token)
    if info is None:
        abort(404)

    casos_ids = info["casos"]
    if id_caso not in casos_ids:
        abort(404)

    siguiente = _siguiente_caso_pendiente(token, casos_ids)
    if siguiente is None:
        return redirect(url_for("gracias", token=token, _external=True))
    if siguiente != id_caso:
        # No se permite ver un caso ya respondido ni saltarse casos.
        return redirect(url_for("ver_caso", token=token, id_caso=siguiente, _external=True))

    perfil = _perfil_caso(id_caso)
    opcion_a, opcion_b = _construir_opciones(token, id_caso)
    posicion = casos_ids.index(id_caso) + 1

    return render_template(
        "caso.html",
        token=token,
        id_caso=id_caso,
        posicion=posicion,
        total=len(casos_ids),
        perfil=perfil,
        opcion_a=opcion_a,
        opcion_b=opcion_b,
        relevancia_anclas=RELEVANCIA_ANCLAS,
        viabilidad_anclas=VIABILIDAD_ANCLAS,
        errores=[],
        valores_previos={},
        es_prueba=bool(info["es_prueba"]),
    )


def _validar_puntaje(form, campo: str, errores: list[str]) -> int | None:
    crudo = form.get(campo, "").strip()
    if crudo == "":
        errores.append(f"Falta responder: {campo}.")
        return None
    try:
        valor = int(crudo)
    except ValueError:
        errores.append(f"Valor inválido en: {campo}.")
        return None
    if valor < 1 or valor > 5:
        errores.append(f"Fuera de rango (1-5) en: {campo}.")
        return None
    return valor


@app.route("/e/<token>/caso/<int:id_caso>", methods=["POST"])
def enviar_caso(token: str, id_caso: int):
    info = _resolver_token(token)
    if info is None:
        abort(404)

    casos_ids = info["casos"]
    if id_caso not in casos_ids:
        abort(404)

    siguiente = _siguiente_caso_pendiente(token, casos_ids)
    if siguiente is None:
        return redirect(url_for("gracias", token=token, _external=True))
    if siguiente != id_caso:
        return redirect(url_for("ver_caso", token=token, id_caso=siguiente, _external=True))

    errores: list[str] = []
    relevancia_a = _validar_puntaje(request.form, "relevancia_a", errores)
    viabilidad_a = _validar_puntaje(request.form, "viabilidad_a", errores)
    relevancia_b = _validar_puntaje(request.form, "relevancia_b", errores)
    viabilidad_b = _validar_puntaje(request.form, "viabilidad_b", errores)

    comentario = request.form.get("comentario", "").strip()
    if len(comentario) > 200:
        errores.append("El comentario supera los 200 caracteres.")
    comentario_final = comentario if comentario else None

    if errores:
        perfil = _perfil_caso(id_caso)
        opcion_a, opcion_b = _construir_opciones(token, id_caso)
        posicion = casos_ids.index(id_caso) + 1
        return (
            render_template(
                "caso.html",
                token=token,
                id_caso=id_caso,
                posicion=posicion,
                total=len(casos_ids),
                perfil=perfil,
                opcion_a=opcion_a,
                opcion_b=opcion_b,
                relevancia_anclas=RELEVANCIA_ANCLAS,
                viabilidad_anclas=VIABILIDAD_ANCLAS,
                errores=errores,
                valores_previos=request.form,
                es_prueba=bool(info["es_prueba"]),
            ),
            400,
        )

    timestamp_utc = datetime.now(timezone.utc).isoformat()
    with db.connect(DB_PATH) as conn:
        db.insertar_respuesta(
            conn,
            token=token,
            evaluador_id=info["evaluador_id"],
            es_prueba=bool(info["es_prueba"]),
            id_caso=id_caso,
            relevancia_a=relevancia_a,
            viabilidad_a=viabilidad_a,
            relevancia_b=relevancia_b,
            viabilidad_b=viabilidad_b,
            comentario=comentario_final,
            timestamp_utc=timestamp_utc,
        )

    return redirect(url_for("entrada", token=token, _external=True))


@app.route("/e/<token>/gracias")
def gracias(token: str):
    info = _resolver_token(token)
    if info is None:
        abort(404)

    casos_ids = info["casos"]
    siguiente = _siguiente_caso_pendiente(token, casos_ids)
    if siguiente is not None:
        return redirect(url_for("ver_caso", token=token, id_caso=siguiente, _external=True))

    return render_template(
        "gracias.html", token=token, total=len(casos_ids), es_prueba=bool(info["es_prueba"])
    )


@app.route("/e/<token>/reiniciar", methods=["POST"])
def reiniciar_simulacion(token: str):
    """Borra las respuestas de un token y lo manda de vuelta al caso 1.

    SOLO funciona para tokens marcados es_prueba=True en evaluadores.json
    (generados por preparar_evaluacion.py). Para un token de evaluador
    real, esto responde 403 sin tocar la base -- las respuestas de un
    evaluador real nunca deben poder borrarse desde la interfaz, o el
    "no se puede recalificar un caso" dejaria de significar algo."""
    info = _resolver_token(token)
    if info is None:
        abort(404)
    if not info["es_prueba"]:
        abort(403)

    with db.connect(DB_PATH) as conn:
        db.borrar_respuestas_token(conn, token)

    return redirect(url_for("entrada", token=token, _external=True))


if __name__ == "__main__":
    # Solo para pruebas locales rapidas fuera de Docker. En Docker se usa
    # gunicorn (ver Dockerfile), nunca este modo.
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
