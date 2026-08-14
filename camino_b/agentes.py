"""
Los 4 agentes del sistema tipo blackboard (adaptado de ARAG, Maragheh et
al. 2025, arXiv:2506.21931):

  1. PERFILADOR   - interpreta el perfil RFM del cliente (sin tocar el corpus)
  2. VERIFICADOR  - inferencia de relevancia jerarquica sobre acciones/promos
  3. SINTETIZADOR - reduce ruido: condensa solo lo que paso el umbral theta
  4. ORDENADOR/GENERADOR - redacta la recomendacion final en 4 campos

Cada agente lee su prompt desde camino_b/prompts/*.md (nunca inline en
Python) y llama al LLM con temperature=0 y seed fijo via llm_client.

## Decision de diseno: regla de umbral + jerarquia (Agente 2)

El enunciado original dice "discard anything scoring below threshold
theta" y, por separado, "ONLY IF the winning action is Accion 3 ...
retrieve+score the 10 promotions". Esas dos reglas se combinan asi:

  1. Se puntuan las 3 acciones candidatas.
  2. Se descartan (no pasan a los agentes siguientes) las que puntuan
     por debajo de theta.
  3. La "accion ganadora" es la de mayor score ENTRE LAS QUE SUPERARON
     theta. Si ninguna supera theta, no hay accion ganadora y el caso
     queda marcado para no continuar con una recomendacion sin base
     (bandera `sin_opcion_viable` en la traza).
  4. Si la accion ganadora es "accion_3", se recuperan y puntuan las 10
     promociones, se descartan las que no superan theta, y se elige la
     de mayor score entre las restantes como sub-opcion ganadora. Si
     ninguna promocion supera theta, Accion 3 sigue siendo valida por si
     sola (el propio corpus indica que no se descarta por falta de
     promocion vigente: se ofrece a precio normal).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import PROMPTS, THETA_RELEVANCIA, TOP_K_ACCIONES, TOP_K_PROMOCIONES
from corpus import Chunk
from embeddings import embeber
from llm_client import RespuestaLLM, completar_chat
from vectorstore import VectorIndex

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _cargar_plantilla(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _render(plantilla: str, valores: dict[str, str]) -> str:
    texto = plantilla
    for clave, valor in valores.items():
        texto = texto.replace("{{" + clave + "}}", valor)
    return texto


def _parsear_json_llm(texto: str) -> dict[str, Any]:
    limpio = _CODE_FENCE_RE.sub("", texto).strip()
    try:
        return json.loads(limpio)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"El LLM no devolvio JSON valido. Texto crudo:\n{texto}"
        ) from exc


def _formatear_candidatas(chunks_con_score_previo: list[Chunk]) -> str:
    bloques = []
    for c in chunks_con_score_previo:
        bloques.append(f"### id: {c.chunk_id}\n{c.texto}")
    return "\n\n".join(bloques)


@dataclass
class ItemEvaluado:
    chunk_id: str
    titulo: str
    score: float
    justificacion: str
    aprobado: bool


@dataclass
class TrazaCaso:
    """Blackboard de un caso: acumula la salida de cada agente para
    trazabilidad completa (se serializa a trazas_agentes.json)."""

    id_caso: Any
    caso_entrada: dict = field(default_factory=dict)
    agente1: dict = field(default_factory=dict)
    agente2: dict = field(default_factory=dict)
    agente3: dict = field(default_factory=dict)
    agente4: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id_caso": self.id_caso,
            "caso_entrada": self.caso_entrada,
            "agente1_perfilador": self.agente1,
            "agente2_verificador": self.agente2,
            "agente3_sintetizador": self.agente3,
            "agente4_generador": self.agente4,
        }


def _meta_llm(resp: RespuestaLLM) -> dict:
    return {
        "modelo": resp.modelo,
        "seed": resp.seed,
        "temperatura": resp.temperatura,
        "response_id": resp.response_id,
        "system_fingerprint": resp.system_fingerprint,
    }


# ---------------------------------------------------------------------------
# Agente 1 — PERFILADOR
# ---------------------------------------------------------------------------


def agente1_perfilador(caso: dict) -> dict:
    """caso: {'id_caso':, 'recency_dias':, 'frequency':, 'monetary_usd':, 'segmento':}"""
    plantilla = _cargar_plantilla(PROMPTS.perfilador)
    caso_json = json.dumps(
        {
            "recency_dias": caso["recency_dias"],
            "frequency": caso["frequency"],
            "monetary_usd": caso["monetary_usd"],
            "segmento": caso["segmento"],
        },
        ensure_ascii=False,
    )
    prompt_renderizado = _render(plantilla, {"CASO_JSON": caso_json})

    respuesta = completar_chat(
        system_prompt="Eres el Agente 1 (PERFILADOR) de un sistema de retencion de clientes.",
        user_prompt=prompt_renderizado,
    )
    salida = _parsear_json_llm(respuesta.texto)

    return {
        "input": {"caso": caso},
        "prompt_renderizado": prompt_renderizado,
        "output": salida,
        "llm": _meta_llm(respuesta),
    }


# ---------------------------------------------------------------------------
# Agente 2 — VERIFICADOR
# ---------------------------------------------------------------------------


def _puntuar_candidatas(resumen_perfil: str, candidatas: list[Chunk], tipo_candidatas: str) -> list[ItemEvaluado]:
    plantilla = _cargar_plantilla(PROMPTS.verificador)
    prompt_renderizado = _render(
        plantilla,
        {
            "RESUMEN_PERFIL": resumen_perfil,
            "TIPO_CANDIDATAS": tipo_candidatas,
            "CANDIDATAS": _formatear_candidatas(candidatas),
        },
    )
    respuesta = completar_chat(
        system_prompt="Eres el Agente 2 (VERIFICADOR) de un sistema de retencion de clientes.",
        user_prompt=prompt_renderizado,
    )
    salida = _parsear_json_llm(respuesta.texto)

    evaluaciones_por_id = {e["id"]: e for e in salida.get("evaluaciones", [])}
    resultado: list[ItemEvaluado] = []
    for c in candidatas:
        ev = evaluaciones_por_id.get(c.chunk_id, {"score": 0.0, "justificacion": "sin evaluacion del LLM"})
        score = float(ev.get("score", 0.0))
        resultado.append(
            ItemEvaluado(
                chunk_id=c.chunk_id,
                titulo=c.titulo,
                score=score,
                justificacion=str(ev.get("justificacion", "")),
                aprobado=score >= THETA_RELEVANCIA,
            )
        )
    return resultado, prompt_renderizado, respuesta


def agente2_verificador(
    resumen_perfil: str,
    indice_acciones: VectorIndex,
    indice_promociones: VectorIndex,
) -> dict:
    vector_consulta = embeber([resumen_perfil])[0]

    candidatas_acciones = [c for c, _score in indice_acciones.buscar(vector_consulta, TOP_K_ACCIONES)]
    evaluadas_acciones, prompt_acciones, resp_acciones = _puntuar_candidatas(
        resumen_perfil, candidatas_acciones, "acciones de retencion"
    )

    aprobadas_acciones = [e for e in evaluadas_acciones if e.aprobado]
    descartadas_acciones = [e for e in evaluadas_acciones if not e.aprobado]

    accion_ganadora = max(aprobadas_acciones, key=lambda e: e.score) if aprobadas_acciones else None

    resultado: dict[str, Any] = {
        "theta": THETA_RELEVANCIA,
        "acciones_evaluadas": [e.__dict__ for e in evaluadas_acciones],
        "acciones_descartadas": [e.__dict__ for e in descartadas_acciones],
        "accion_ganadora": accion_ganadora.__dict__ if accion_ganadora else None,
        "prompt_acciones": prompt_acciones,
        "llm_acciones": _meta_llm(resp_acciones),
        "promociones_evaluadas": [],
        "promociones_descartadas": [],
        "promocion_ganadora": None,
        "sin_opcion_viable": accion_ganadora is None,
        "items_aprobados_para_agente3": [],
    }

    if accion_ganadora is None:
        return resultado

    items_aprobados: list[dict] = [
        {
            "chunk_id": accion_ganadora.chunk_id,
            "titulo": accion_ganadora.titulo,
            "score": accion_ganadora.score,
            "justificacion": accion_ganadora.justificacion,
            "texto": next(c.texto for c in candidatas_acciones if c.chunk_id == accion_ganadora.chunk_id),
        }
    ]

    # Regla de jerarquia: solo si gana Accion 3 se recuperan y puntuan promociones.
    if accion_ganadora.chunk_id == "accion_3":
        candidatas_promos = [c for c, _score in indice_promociones.buscar(vector_consulta, TOP_K_PROMOCIONES)]
        evaluadas_promos, prompt_promos, resp_promos = _puntuar_candidatas(
            resumen_perfil, candidatas_promos, "promociones vigentes"
        )
        aprobadas_promos = [e for e in evaluadas_promos if e.aprobado]
        descartadas_promos = [e for e in evaluadas_promos if not e.aprobado]
        promo_ganadora = max(aprobadas_promos, key=lambda e: e.score) if aprobadas_promos else None

        resultado["promociones_evaluadas"] = [e.__dict__ for e in evaluadas_promos]
        resultado["promociones_descartadas"] = [e.__dict__ for e in descartadas_promos]
        resultado["promocion_ganadora"] = promo_ganadora.__dict__ if promo_ganadora else None
        resultado["prompt_promociones"] = prompt_promos
        resultado["llm_promociones"] = _meta_llm(resp_promos)

        if promo_ganadora is not None:
            items_aprobados.append(
                {
                    "chunk_id": promo_ganadora.chunk_id,
                    "titulo": promo_ganadora.titulo,
                    "score": promo_ganadora.score,
                    "justificacion": promo_ganadora.justificacion,
                    "texto": next(c.texto for c in candidatas_promos if c.chunk_id == promo_ganadora.chunk_id),
                }
            )

    resultado["items_aprobados_para_agente3"] = items_aprobados
    return resultado


# ---------------------------------------------------------------------------
# Agente 3 — SINTETIZADOR
# ---------------------------------------------------------------------------


def agente3_sintetizador(items_aprobados: list[dict]) -> dict:
    plantilla = _cargar_plantilla(PROMPTS.sintetizador)

    if not items_aprobados:
        opciones_texto = "(ninguna opcion supero el umbral de relevancia para este cliente)"
    else:
        bloques = []
        for item in items_aprobados:
            bloques.append(
                f"### {item['titulo']} (score={item['score']:.2f})\n"
                f"Justificacion de relevancia: {item['justificacion']}\n\n{item['texto']}"
            )
        opciones_texto = "\n\n".join(bloques)

    prompt_renderizado = _render(plantilla, {"OPCIONES_APROBADAS": opciones_texto})

    respuesta = completar_chat(
        system_prompt="Eres el Agente 3 (SINTETIZADOR) de un sistema de retencion de clientes.",
        user_prompt=prompt_renderizado,
    )
    salida = _parsear_json_llm(respuesta.texto)

    return {
        "input": {"items_aprobados": items_aprobados},
        "prompt_renderizado": prompt_renderizado,
        "output": salida,
        "llm": _meta_llm(respuesta),
    }


# ---------------------------------------------------------------------------
# Agente 4 — ORDENADOR/GENERADOR
# ---------------------------------------------------------------------------


def agente4_generador(resumen_perfil: str, contexto_condensado: str) -> tuple[dict, str, RespuestaLLM]:
    """Una sola llamada al LLM; el reintento ante fallos de validacion lo
    maneja el pipeline (que es quien conoce las reglas de validacion y los
    datos del caso para el chequeo de fuga de RFM)."""
    plantilla = _cargar_plantilla(PROMPTS.generador)
    prompt_renderizado = _render(
        plantilla,
        {"RESUMEN_PERFIL": resumen_perfil, "CONTEXTO_CONDENSADO": contexto_condensado},
    )
    respuesta = completar_chat(
        system_prompt="Eres el Agente 4 (ORDENADOR/GENERADOR) de un sistema de retencion de clientes.",
        user_prompt=prompt_renderizado,
    )
    salida = _parsear_json_llm(respuesta.texto)
    return salida, prompt_renderizado, respuesta
