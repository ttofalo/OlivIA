"""Avisos por Telegram: el reporte diario de gasto y, más adelante, alertas.

Un mensaje que falla no puede tumbar quien lo llama: siempre atrapa el error
y lo loguea, nunca lo propaga.
"""

from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger()


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
