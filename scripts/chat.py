#!/usr/bin/env python3
"""Chat local por MQTT para probar OlivIA sin WhatsApp."""

from __future__ import annotations

import argparse
import json
import time
import uuid

import paho.mqtt.client as mqtt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(connected, _userdata, _flags, reason_code, _properties) -> None:
        if reason_code != 0:
            raise RuntimeError(f"MQTT rechazó la conexión: {reason_code}")
        connected.subscribe("wsp/out", qos=1)
        print(
            f"Conectado a {args.host}:{args.port}. Escribí un mensaje (Ctrl-D para salir)."
        )

    def on_message(_client, _userdata, message) -> None:
        payload = json.loads(message.payload)
        if payload.get("text"):
            print(f"OlivIA: {payload['text']}")
        if payload.get("imagePath"):
            print(f"OlivIA [imagen]: {payload['imagePath']}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    try:
        while True:
            text = input("> ").strip()
            if not text:
                continue
            payload = {
                "id": str(uuid.uuid4()),
                "chat": "local",
                "from": "local",
                "text": text,
                "kind": "text",
                "timestamp": int(time.time() * 1000),
            }
            client.publish("wsp/in", json.dumps(payload), qos=1)
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
