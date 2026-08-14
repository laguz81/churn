"""
Carga y chunking del corpus (SOLO los archivos .md de la whitelist).

Regla dura: este modulo nunca debe hacer os.listdir/glob sobre
CORPUS_DIR. Toda lectura pasa por config.CORPUS_WHITELIST, que enumera
explicitamente los archivos permitidos. casos_15_expertos.csv y
PRIVADO_mapa_id.csv jamas se mencionan ni se abren aqui.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from config import CLAVES_ACCIONES, CORPUS_WHITELIST


@dataclass(frozen=True)
class Chunk:
    """Un bloque coherente del corpus (una accion, una promocion, una
    seccion de politica), listo para embeber."""

    chunk_id: str
    titulo: str
    texto: str
    fuente: str  # nombre logico del archivo ("acciones", "promociones", "politica")


_HEADING_RE = re.compile(r"^##\s+(.*)$", re.MULTILINE)


def _split_por_encabezados_h2(texto_md: str) -> list[tuple[str, str]]:
    """Divide un markdown en secciones por encabezados de nivel 2 (##).

    Devuelve una lista de (titulo_seccion, cuerpo_seccion). El contenido
    antes del primer '##' (si existe) se descarta porque en estos 3
    documentos es siempre metadata de procedencia, no contenido a indexar.
    """
    matches = list(_HEADING_RE.finditer(texto_md))
    secciones: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        titulo = match.group(1).strip()
        inicio_cuerpo = match.end()
        fin_cuerpo = matches[i + 1].start() if i + 1 < len(matches) else len(texto_md)
        cuerpo = texto_md[inicio_cuerpo:fin_cuerpo].strip()
        secciones.append((titulo, cuerpo))
    return secciones


def _leer_whitelisted(clave: str) -> str:
    if clave not in CORPUS_WHITELIST:
        raise ValueError(f"'{clave}' no esta en la whitelist del corpus: {list(CORPUS_WHITELIST)}")
    ruta: Path = CORPUS_WHITELIST[clave]
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontro el archivo del corpus: {ruta}")
    return ruta.read_text(encoding="utf-8")


def cargar_chunks_acciones() -> list[Chunk]:
    """Chunkea todos los archivos de config.CLAVES_ACCIONES por seccion
    '## Accion N: ...' y los combina en un unico indice de acciones de
    primer nivel.

    Se descartan las secciones de procedencia y la lista de "acciones que
    NO deben recomendarse nunca" (no son acciones candidatas a recuperar,
    son restricciones globales). Con acciones_retencion_1.md (Accion 1-3)
    + acciones_retencion_2.md (Accion 4) da exactamente 4 chunks.

    Valida que cada numero de accion aparezca una sola vez entre todos los
    archivos: si dos archivos definen "Accion 2", es un error del corpus
    (contenido duplicado o mal versionado), no algo que deba fusionarse
    silenciosamente.
    """
    chunks: list[Chunk] = []
    numeros_vistos: dict[str, str] = {}  # numero -> archivo donde aparecio
    for clave in CLAVES_ACCIONES:
        texto = _leer_whitelisted(clave)
        for titulo, cuerpo in _split_por_encabezados_h2(texto):
            if not re.match(r"^Acci[oó]n\s+\d+\s*:", titulo, re.IGNORECASE):
                continue
            numero_match = re.search(r"\d+", titulo)
            numero = numero_match.group(0) if numero_match else str(len(chunks) + 1)
            if numero in numeros_vistos:
                raise ValueError(
                    f"Accion {numero} aparece en '{clave}' pero ya se habia "
                    f"cargado desde '{numeros_vistos[numero]}'. Revisa el corpus: "
                    "cada numero de accion debe ser unico entre todos los archivos "
                    "listados en config.CLAVES_ACCIONES."
                )
            numeros_vistos[numero] = clave
            chunks.append(
                Chunk(
                    chunk_id=f"accion_{numero}",
                    titulo=titulo,
                    texto=f"{titulo}\n\n{cuerpo}",
                    fuente=clave,
                )
            )
    chunks.sort(key=lambda c: int(re.search(r"\d+", c.chunk_id).group(0)))
    return chunks


def cargar_chunks_promociones() -> list[Chunk]:
    """Chunkea promociones_vigentes_1.md por seccion '## Promocion N: ...'.

    Se descartan procedencia, nota metodologica y notas adicionales,
    quedando exactamente 10 chunks (Promocion 1 a Promocion 10).
    """
    texto = _leer_whitelisted("promociones")
    chunks: list[Chunk] = []
    for titulo, cuerpo in _split_por_encabezados_h2(texto):
        if not re.match(r"^Promoci[oó]n\s+\d+\s*:", titulo, re.IGNORECASE):
            continue
        numero_match = re.search(r"\d+", titulo)
        numero = numero_match.group(0) if numero_match else str(len(chunks) + 1)
        chunks.append(
            Chunk(
                chunk_id=f"promocion_{numero}",
                titulo=titulo,
                texto=f"{titulo}\n\n{cuerpo}",
                fuente="promociones",
            )
        )
    return chunks


def cargar_chunks_politica() -> list[Chunk]:
    """Chunkea politica_descuentos_1.md por seccion '## ...' (sin filtrar
    por numero, ya que aqui las secciones son tematicas: descuentos
    autorizados, limite maximo, condiciones de credito, etc.).

    Se excluye la seccion 'Procedencia' porque es metadata del documento,
    no una regla de negocio.
    """
    texto = _leer_whitelisted("politica")
    chunks: list[Chunk] = []
    for titulo, cuerpo in _split_por_encabezados_h2(texto):
        if titulo.strip().lower() == "procedencia":
            continue
        slug = re.sub(r"[^a-z0-9]+", "_", titulo.lower()).strip("_")
        chunks.append(
            Chunk(
                chunk_id=f"politica_{slug}",
                titulo=titulo,
                texto=f"{titulo}\n\n{cuerpo}",
                fuente="politica",
            )
        )
    return chunks
