"""Cliente MQTT del brain y los topics del sistema."""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

from .config import Settings

TOPIC_IN = "wsp/in"
TOPIC_OUT = "wsp/out"


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
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        self._settings = settings

    def connect(self) -> None:
        self._client.connect(self._settings.mqtt_host, self._settings.mqtt_port, keepalive=60)

    def on_message(self, handler: Callable[[str, dict[str, Any]], None]) -> None:
        def _cb(_client, _userdata, msg) -> None:
            handler(msg.topic, json.loads(msg.payload))

        self._client.on_message = _cb

    def subscribe(self, *topics: str) -> None:
        for t in topics:
            self._client.subscribe(t, qos=1)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._client.publish(topic, json.dumps(payload), qos=1)

    def reply(self, chat: str, text: str | None = None, image_path: str | None = None) -> None:
        self.publish(TOPIC_OUT, {"chat": chat, "text": text, "imagePath": image_path})

    def loop_forever(self) -> None:
        self._client.loop_forever()
