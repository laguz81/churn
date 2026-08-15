"""
db.py

Acceso minimo a SQLite (stdlib) para las respuestas del panel de
evaluacion. Una fila por evento de envio de caso por token.

No importa Flask: se usa tanto desde app.py (en tiempo de peticion) como
desde exportar_resultados.py (fuera de peticion, en un script aparte).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS respuestas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    evaluador_id TEXT NOT NULL,
    es_prueba INTEGER NOT NULL,
    id_caso INTEGER NOT NULL,
    relevancia_a INTEGER NOT NULL,
    viabilidad_a INTEGER NOT NULL,
    relevancia_b INTEGER NOT NULL,
    viabilidad_b INTEGER NOT NULL,
    comentario TEXT,
    timestamp_utc TEXT NOT NULL,
    UNIQUE(token, id_caso)
);
"""


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect(db_path: str | Path):
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def casos_respondidos(conn: sqlite3.Connection, token: str) -> set[int]:
    rows = conn.execute(
        "SELECT id_caso FROM respuestas WHERE token = ?", (token,)
    ).fetchall()
    return {row["id_caso"] for row in rows}


def insertar_respuesta(
    conn: sqlite3.Connection,
    *,
    token: str,
    evaluador_id: str,
    es_prueba: bool,
    id_caso: int,
    relevancia_a: int,
    viabilidad_a: int,
    relevancia_b: int,
    viabilidad_b: int,
    comentario: str | None,
    timestamp_utc: str,
) -> bool:
    """Inserta una respuesta. Devuelve False si el par (token, id_caso) ya existia."""
    try:
        conn.execute(
            """
            INSERT INTO respuestas (
                token, evaluador_id, es_prueba, id_caso,
                relevancia_a, viabilidad_a, relevancia_b, viabilidad_b,
                comentario, timestamp_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token,
                evaluador_id,
                1 if es_prueba else 0,
                id_caso,
                relevancia_a,
                viabilidad_a,
                relevancia_b,
                viabilidad_b,
                comentario,
                timestamp_utc,
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        return False


def borrar_respuestas_token(conn: sqlite3.Connection, token: str) -> int:
    """Borra todas las respuestas de un token. Usado solo por la ruta de
    reinicio de simulacion (app.py), que a su vez solo la habilita para
    tokens marcados es_prueba=True. No filtra por es_prueba aqui mismo
    -- la app es responsable de no llamar esto para un token real."""
    cur = conn.execute("DELETE FROM respuestas WHERE token = ?", (token,))
    conn.commit()
    return cur.rowcount
