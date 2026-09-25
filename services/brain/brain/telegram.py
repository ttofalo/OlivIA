"""Telegram: avisos (reporte diario, caídas) y la consulta de gasto.

El gasto en IA se consulta solo acá, no por WhatsApp: es un dato de la
operación de la casa, no algo que tenga que quedar en un chat familiar. Un
mensaje que falla no puede tumbar quien lo llama: siempre atrapa el error y
lo loguea, nunca lo propaga.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx
import structlog

log = structlog.get_logger()

# Long-polling: Telegram mantiene la conexión abierta hasta que hay un
# mensaje nuevo o se cumple el timeout, así que no hace falta consultar en
# loop ajustado. 25s dentro del timeout HTTP de 35s, con margen.
POLL_TIMEOUT = 25


def notificar(texto: str, token: str, chat_id: str) -> bool:
    """Manda `texto` por el bot de Telegram. True si salió bien."""
    if not token or not chat_id:
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": texto},
            timeout=10.0,
        )
        r.raise_for_status()
        return True
    except Exception:
        log.exception("no pude avisar por Telegram")
        return False


def _actualizaciones(token: str, offset: int) -> list[dict]:
    r = httpx.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": offset, "timeout": POLL_TIMEOUT},
        timeout=POLL_TIMEOUT + 10,
    )
    r.raise_for_status()
    return r.json().get("result", [])


def escuchar(
    token: str,
    chat_id: str,
    responder: Callable[[str], str | None],
    *,
    limite_iteraciones: int | None = None,
) -> None:
    """Loop de long-polling: por cada mensaje de texto que llegue del chat
    autorizado, llama a `responder(texto)` y manda lo que devuelva. Ignora
    cualquier otro chat, para que nadie más le pregunte el gasto a este bot.
    `limite_iteraciones` es solo para los tests, en producción corre siempre.
    """
    offset = 0
    iteraciones = 0
    while limite_iteraciones is None or iteraciones < limite_iteraciones:
        iteraciones += 1
        try:
            actualizaciones = _actualizaciones(token, offset)
        except Exception:
            log.exception("no pude consultar Telegram, reintento en 5s")
            time.sleep(5)
            continue
        for u in actualizaciones:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            texto = msg.get("text")
            chat = str(msg.get("chat", {}).get("id", ""))
            if not texto or chat != str(chat_id):
                continue
            try:
                respuesta = responder(texto)
            except Exception:
                log.exception("fallo respondiendo por Telegram")
                continue
            if respuesta:
                notificar(respuesta, token, chat_id)
