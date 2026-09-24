"""Reporte diario de gasto por Telegram.

Standalone, sin MQTT: lee el mismo `costos.jsonl` que escribe el brain y
manda el resumen. Pensado para un cron del host a las 21hs Argentina
(00:00 UTC), fuera del proceso del brain para no competir con sus hilos.

    python -m brain.reporte_diario
"""

from __future__ import annotations

import structlog

from . import costos
from .config import Settings
from .telegram import notificar

log = structlog.get_logger()


def main() -> None:
    settings = Settings.from_env()
    costos.configurar(settings.costs_path)

    texto = costos.resumen_texto()
    saldo = costos.saldo_deepseek(settings.llm_base_url, settings.llm_api_key)
    if saldo is not None:
        texto += f" En DeepSeek quedan USD {saldo}."

    mensaje = f"Gasto de hoy en OlivIA. {texto}"
    log.info("reporte diario", texto=mensaje)

    if not notificar(mensaje, settings.telegram_bot_token, settings.telegram_chat_id):
        log.warning("no se mandó el reporte diario (sin Telegram configurado o falló el envío)")


if __name__ == "__main__":
    main()
