"""
Cliente delgado sobre la API de OpenAI (chat completions) usado por los 4
agentes. Centraliza: chequeo temprano de la API key, temperature=0 fijo,
seed fijo, y el nombre de modelo pinneado por config.

No se llama a este modulo desde indexador.py ni desde el validador: solo
los agentes (perfilador, verificador, sintetizador, generador) lo usan.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import LLM_SEED, LLM_TEMPERATURE, OPENAI_MODEL, get_openai_api_key

_cliente = None


@dataclass
class RespuestaLLM:
    texto: str
    modelo: str
    seed: int
    temperatura: float
    response_id: str | None
    system_fingerprint: str | None


def _get_cliente():
    global _cliente
    if _cliente is None:
        # Falla rapido y con mensaje claro ANTES de tocar el SDK de openai,
        # en vez de dejar que este reviente con un error generico de auth.
        api_key = get_openai_api_key()
        from openai import OpenAI

        _cliente = OpenAI(api_key=api_key)
    return _cliente


def completar_chat(system_prompt: str, user_prompt: str) -> RespuestaLLM:
    """Hace una llamada de chat completion con temperature=0 y seed fijo.

    Lanza RuntimeError con mensaje claro si OPENAI_API_KEY no esta
    configurada (via get_openai_api_key, llamado antes de crear el
    cliente).
    """
    cliente = _get_cliente()
    respuesta = cliente.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=LLM_TEMPERATURE,
        seed=LLM_SEED,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    texto = respuesta.choices[0].message.content or ""
    return RespuestaLLM(
        texto=texto,
        modelo=respuesta.model,
        seed=LLM_SEED,
        temperatura=LLM_TEMPERATURE,
        response_id=getattr(respuesta, "id", None),
        system_fingerprint=getattr(respuesta, "system_fingerprint", None),
    )
