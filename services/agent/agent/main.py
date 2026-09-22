"""Punto de entrada del agente local.

Se conecta al VPS y espera comandos. No escucha en ningún puerto.
"""

from __future__ import annotations

import json
import ssl
import threading
import time

import paho.mqtt.client as mqtt
import requests
import structlog

from . import cameras, snapshot
from .config import Camera, Settings, load_cameras

log = structlog.get_logger()

CMD_CAM = "casa/cmd/cam/+/+"


class Agent:
    def __init__(self, settings: Settings, cams: dict[str, Camera]) -> None:
        self._settings = settings
        self._cams = cams
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.username_pw_set(settings.mqtt_user, settings.mqtt_pass)
        if settings.mqtt_tls:
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        # Si el agente se cae, el broker avisa por su cuenta.
        self._client.will_set(
            "casa/evt/agent/heartbeat", json.dumps({"alive": False}), qos=1, retain=True
        )

    def run(self) -> None:
        self._client.connect(self._settings.mqtt_host, self._settings.mqtt_port, keepalive=60)
        threading.Thread(target=self._heartbeat, daemon=True).start()
        log.info("agente arriba", camaras=list(self._cams))
        self._client.loop_forever()

    def _on_connect(self, _client, _userdata, _flags, reason_code, _props) -> None:
        log.info("conectado al VPS", reason=str(reason_code))
        self._client.subscribe(CMD_CAM, qos=1)

    def _heartbeat(self) -> None:
        while True:
            self._client.publish(
                "casa/evt/agent/heartbeat",
                json.dumps({"alive": True, "ts": time.time()}),
                qos=0,
                retain=True,
            )
            time.sleep(self._settings.heartbeat_seconds)

    def _on_message(self, _client, _userdata, msg) -> None:
        # Cada comando en su thread: un snapshot tarda segundos y no puede
        # bloquear a los demás.
        threading.Thread(target=self._handle, args=(msg.topic, msg.payload), daemon=True).start()

    def _handle(self, topic: str, raw: bytes) -> None:
        parts = topic.split("/")
        cam_id, action = parts[3], parts[4]
        payload = json.loads(raw) if raw else {}

        cam = self._cams.get(cam_id)
        if cam is None:
            self._emit(cam_id, action, {"error": f"no tengo la cámara {cam_id}"})
            return

        try:
            if action == "snapshot":
                path = snapshot.grab(cam, self._settings.snapshot_dir)
                remote = self._upload(path)
                self._emit(cam_id, "snapshot", {"path": remote, "chat": payload.get("chat")})

            elif action == "ptz":
                if "preset" in payload:
                    cameras.goto_preset(cam, int(payload["preset"]))
                else:
                    cameras.move(
                        cam,
                        payload["direction"],
                        duration=float(payload.get("duration", 0.5)),
                        speed=int(payload.get("speed", 4)),
                    )
                self._emit(cam_id, "ptz", {"ok": True, "chat": payload.get("chat")})

            else:
                self._emit(cam_id, action, {"error": f"acción desconocida: {action}"})

        except Exception as exc:  # el agente no se muere por un comando fallido
            log.exception("comando falló", cam=cam_id, action=action)
            self._emit(cam_id, action, {"error": str(exc), "chat": payload.get("chat")})

    def _upload(self, path) -> str:
        """Sube la foto al VPS y devuelve la ruta con la que la ve el gateway."""
        with path.open("rb") as fh:
            response = requests.post(
                self._settings.upload_url,
                files={"file": (path.name, fh, "image/jpeg")},
                headers={"Authorization": f"Bearer {self._settings.upload_token}"},
                timeout=30,
            )
        response.raise_for_status()
        return response.json()["path"]

    def _emit(self, cam_id: str, evento: str, payload: dict) -> None:
        self._client.publish(f"casa/evt/cam/{cam_id}/{evento}", json.dumps(payload), qos=1)


def main() -> None:
    settings = Settings.from_env()
    cams = load_cameras(settings.devices_path)
    if not cams:
        raise SystemExit("devices.yaml no tiene cámaras. Correr scripts/discover.py primero.")
    Agent(settings, cams).run()


if __name__ == "__main__":
    main()
