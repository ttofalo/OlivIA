"""Cliente MQTT del brain y los topics del sistema."""

from __future__ import annotations

import json
import re
import ssl
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import paho.mqtt.client as mqtt
import structlog

from .config import Settings

log = structlog.get_logger()

TOPIC_IN = "wsp/in"
TOPIC_OUT = "wsp/out"

# Rangos de emojis y pictogramas. OlivIA no usa ninguno: se filtran de toda
# respuesta, sin importar lo que devuelva el modelo.
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff"
    "\U00002190-\U000021ff\U00002300-\U000023ff️‍]"
)


def _sin_emojis(texto: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", _EMOJI.sub("", texto)).strip()


def _con_nombres(texto: str, nombres: dict[str, str]) -> str:
    """Reemplaza ids internos (cabania) por el nombre para la gente (Cabaña).

    Red de seguridad para que un id nunca llegue al chat, diga lo que diga el
    modelo. Solo palabras completas, sin importar mayúsculas.
    """
    for cam_id, nombre in nombres.items():
        if cam_id.lower() == nombre.lower():
            continue
        texto = re.sub(rf"\b{re.escape(cam_id)}\b", nombre, texto, flags=re.IGNORECASE)
    return texto


def cmd_snapshot(cam_id: str) -> str:
    return f"casa/cmd/cam/{cam_id}/snapshot"


def cmd_ptz(cam_id: str) -> str:
    return f"casa/cmd/cam/{cam_id}/ptz"


def cmd_preset_save(cam_id: str) -> str:
    return f"casa/cmd/cam/{cam_id}/preset/save"


def cmd_boyero(boyero_id: str) -> str:
    return f"casa/cmd/boyero/{boyero_id}/set"


EVT_CAM = "casa/evt/cam/+/+"
EVT_BOYERO = "casa/evt/boyero/+/+"
EVT_AGENT = "casa/evt/agent/+"


class Bus:
    def __init__(self, settings: Settings) -> None:
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.username_pw_set(settings.mqtt_user, settings.mqtt_pass)
        if settings.mqtt_tls:
            self._client.tls_set(ca_certs=settings.mqtt_ca or None, cert_reqs=ssl.CERT_REQUIRED)
        self._settings = settings
        # Cada mensaje se procesa en un hilo aparte. paho no envía lo que se
        # publica dentro de un callback hasta que el callback termina, así que
        # una llamada lenta (Jev, LLM, visión) retenía la foto y frenaba todo el
        # brain. Con el pool, la foto sale al instante y los pedidos no se pisan.
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="brain")
        # id de cámara -> nombre humano, para el filtro de salida.
        self._nombres: dict[str, str] = {}

    def set_nombres(self, nombres: dict[str, str]) -> None:
        self._nombres = dict(nombres)

    def connect(self) -> None:
        self._client.connect(self._settings.mqtt_host, self._settings.mqtt_port, keepalive=60)

    def on_message(self, handler: Callable[[str, dict[str, Any]], None]) -> None:
        def _run(topic: str, payload: dict[str, Any]) -> None:
            try:
                handler(topic, payload)
            except Exception:
                log.exception("handler falló", topic=topic)

        def _cb(_client, _userdata, msg) -> None:
            self._pool.submit(_run, msg.topic, json.loads(msg.payload))

        self._client.on_message = _cb

    def subscribe(self, *topics: str) -> None:
        for t in topics:
            self._client.subscribe(t, qos=1)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._client.publish(topic, json.dumps(payload), qos=1)

    def reply(self, chat: str, text: str | None = None, image_path: str | None = None) -> None:
        if text:
            text = _con_nombres(_sin_emojis(text), self._nombres)
        self.publish(TOPIC_OUT, {"chat": chat, "text": text, "imagePath": image_path})

    def loop_forever(self) -> None:
        self._client.loop_forever()
