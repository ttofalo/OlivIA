"""Punto de entrada del brain.

Fase 1: consume wsp/in, rutea con Jev y despacha comandos al agente.
Lo que falta está marcado con TODO y tiene su fase en docs/ROADMAP.md.
"""

from __future__ import annotations

import structlog

from . import bus as B
from .config import Inventory, Settings
from .router import Router

log = structlog.get_logger()


class Brain:
    def __init__(self, settings: Settings, inventory: Inventory) -> None:
        self._settings = settings
        self._inventory = inventory
        self._router = Router(settings, inventory)
        self._bus = B.Bus(settings)
        # Qué chat espera el resultado de cada comando en vuelo.
        self._pending: dict[str, str] = {}

    def run(self) -> None:
        self._bus.on_message(self._handle)
        self._bus.connect()
        self._bus.subscribe(B.TOPIC_IN, B.EVT_CAM, B.EVT_BOYERO, B.EVT_AGENT)
        log.info("brain arriba", threshold=self._settings.jev_threshold)
        self._bus.loop_forever()

    def _handle(self, topic: str, payload: dict) -> None:
        if topic == B.TOPIC_IN:
            self._handle_inbound(payload)
        elif topic.startswith("casa/evt/cam/"):
            self._handle_cam_event(topic, payload)
        else:
            log.debug("evento sin handler", topic=topic)

    def _handle_inbound(self, msg: dict) -> None:
        chat = msg["chat"]
        texto = msg.get("text", "")

        if msg.get("kind") == "audio":
            # TODO fase 2: transcribir msg["mediaPath"] y seguir con el texto.
            self._bus.reply(chat, "Todavía no escucho audios. Escribime por ahora.")
            return

        if not texto.strip():
            return

        decision = self._router.route(texto)
        log.info(
            "decision",
            intent=decision.intent,
            conf=round(decision.intent_confidence, 3),
            camara=decision.camara,
            model=decision.model,
        )
        # TODO fase 2: persistir la decisión en postgres para calibrar el umbral.

        if not decision.confident_enough(self._settings.jev_threshold):
            # TODO fase 2: acá entra Claude en vez de pedir que repita.
            self._bus.reply(chat, "No te entendí bien. ¿De qué cámara me hablás?")
            return

        if decision.needs_confirmation():
            # TODO fase 4: guardar la acción pendiente y esperar el sí.
            self._bus.reply(chat, "Eso toca algo físico. Todavía no lo tengo habilitado.")
            return

        self._dispatch(chat, decision)

    def _dispatch(self, chat: str, decision) -> None:
        if decision.intent == "snapshot" and decision.camara:
            topic = B.cmd_snapshot(decision.camara)
            self._pending[decision.camara] = chat
            self._bus.publish(topic, {"chat": chat})
            return

        if decision.intent == "ptz" and decision.camara:
            # TODO fase 3: parsear a dónde moverla. Jev da la cámara, falta el destino.
            self._bus.reply(chat, "Mover cámaras llega en la fase 3.")
            return

        self._bus.reply(chat, "Eso todavía no lo sé hacer.")

    def _handle_cam_event(self, topic: str, payload: dict) -> None:
        _, _, _, cam_id, evento = topic.split("/", 4)

        if evento == "snapshot":
            chat = payload.get("chat") or self._pending.pop(cam_id, None)
            if not chat:
                log.warning("snapshot sin destinatario", cam=cam_id)
                return
            if payload.get("error"):
                self._bus.reply(chat, f"No pude sacar la foto: {payload['error']}")
                return
            self._bus.reply(chat, image_path=payload["path"])

        elif evento == "motion":
            # TODO fase 5: triage con router.triage_motion antes de despertar a nadie.
            log.info("movimiento", cam=cam_id, payload=payload)


def main() -> None:
    settings = Settings.from_env()
    inventory = Inventory.load(settings.devices_path)
    Brain(settings, inventory).run()


if __name__ == "__main__":
    main()
