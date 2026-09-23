"""Punto de entrada del brain.

Fase 1: consume wsp/in, rutea con Jev y despacha comandos al agente.
Fase 2: transcribe audios y escala al LLM de nivel 2 cuando Jev duda.
Lo que falta está marcado con TODO y tiene su fase en docs/ROADMAP.md.
"""

from __future__ import annotations

import base64
import itertools
import random
import threading
from pathlib import Path

import structlog

from . import bus as B
from . import costos
from .config import Inventory, Settings
from .llm import Action, Assistant
from .router import Decision, Router
from .transcribe import TranscribeError, transcribe

log = structlog.get_logger()

# Acuse inmediato: una foto tarda unos segundos, así que el bot avisa que está
# en eso apenas recibe el pedido.
ACKS = (
    "Dale, ahí te paso.",
    "Estoy en eso.",
    "Ya te la busco.",
    "Un toque y te muestro.",
    "Voy a fijarme.",
    "Dame un segundo.",
)

# Si el agente de casa no devuelve la foto en este tiempo, se avisa en vez de
# dejar al usuario con el acuse y después silencio.
PENDING_TIMEOUT = 15.0
SIN_RESPUESTA = "La casa no me contesta. Fijate que el agente esté prendido."

NO_ENTENDI = "No te entendí bien. ¿De qué cámara me hablás?"


class Brain:
    def __init__(self, settings: Settings, inventory: Inventory) -> None:
        self._settings = settings
        self._inventory = inventory
        self._router = Router(settings, inventory)
        self._assistant = Assistant(settings, inventory)
        self._bus = B.Bus(settings)
        costos.configurar(settings.costs_path)
        # Que ningún id interno (cabania) llegue al chat: el bus lo cambia por
        # el nombre (Cabaña) en todo texto saliente.
        self._bus.set_nombres({cid: inventory.nombre(cid) for cid in inventory.camaras})
        # Qué chat espera el resultado de cada comando en vuelo.
        self._pending: dict[str, str] = {}
        # Última cámara usada por chat, para que "movela a la derecha" sin
        # nombrar cámara se entienda.
        self._last_cam: dict[str, str] = {}
        # Los handlers corren en hilos del pool: el estado en vuelo va con lock,
        # y cada pedido lleva un token para que el timeout no pise uno nuevo.
        self._lock = threading.Lock()
        self._tokens: dict[str, int] = {}
        self._counter = itertools.count()

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
            texto = self._transcribir(chat, msg.get("mediaPath"))
            if texto is None:
                return

        if not texto.strip():
            # Aunque no haya texto, el bot contesta algo: nunca queda mudo.
            self._bus.reply(chat, NO_ENTENDI)
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
            self._escalate(chat, texto)
            return

        if decision.needs_confirmation():
            # TODO fase 4: guardar la acción pendiente y esperar el sí.
            self._bus.reply(chat, "Eso toca algo físico. Todavía no lo tengo habilitado.")
            return

        self._dispatch(chat, texto, decision)

    def _transcribir(self, chat: str, media_path: str | None) -> str | None:
        if not media_path:
            self._bus.reply(chat, "Me llegó un audio vacío.")
            return None
        s = self._settings
        try:
            texto = transcribe(
                Path(media_path),
                s.transcribe_backend,
                s.transcribe_model,
                s.transcribe_api_base_url,
                s.transcribe_api_key,
            )
        except TranscribeError as exc:
            log.warning("audio sin transcribir", error=str(exc))
            self._bus.reply(chat, "No pude entender el audio. ¿Me lo escribís?")
            return None
        log.info("audio transcripto", texto=texto)
        return texto

    def _dispatch(self, chat: str, texto: str, decision: Decision) -> None:
        if decision.camara:
            self._last_cam[chat] = decision.camara
        if decision.intent == "snapshot" and decision.camara:
            self._snapshot(chat, decision.camara)
            return

        if decision.intent == "gasto":
            self._gasto(chat)
            return

        if decision.intent == "ptz" and decision.camara:
            # Jev da la cámara pero no el destino. El LLM tiene los presets
            # como enum y saca el "al portón" del texto.
            self._escalate(chat, texto)
            return

        # Cualquier otra cosa (preguntas abiertas, "qué podés hacer", charla)
        # va al LLM de nivel 2 en vez de una respuesta enlatada.
        self._escalate(chat, texto)

    def _escalate(self, chat: str, texto: str) -> None:
        """Nivel 2: el LLM interpreta lo que Jev no pudo."""
        reply = self._assistant.answer(texto, ultima_camara=self._last_cam.get(chat))
        for action in reply.actions:
            self._run_action(chat, action)
        if reply.text:
            self._bus.reply(chat, reply.text)
        elif not reply.actions:
            self._bus.reply(chat, NO_ENTENDI)

    def _run_action(self, chat: str, action: Action) -> None:
        cam = action["camara"]
        if cam:
            self._last_cam[chat] = cam
        if action["kind"] == "snapshot" and cam:
            self._snapshot(chat, cam)
        elif action["kind"] == "ptz_preset" and cam and action["preset"]:
            presets = self._inventory.camaras.get(cam, {}).get("presets") or {}
            numero = presets.get(action["preset"])
            if numero is None:
                log.warning("preset sin número", cam=cam, preset=action["preset"])
                return
            self._bus.publish(B.cmd_ptz(cam), {"preset": numero, "chat": chat})
        elif action["kind"] == "ptz_move" and cam and action.get("direction"):
            # Giro corto y acotado; el agente verifica que no quede mirando la pared.
            self._bus.reply(chat, text=random.choice(ACKS))
            self._bus.publish(
                B.cmd_ptz(cam),
                {"direction": action["direction"], "duration": 0.6, "speed": 0.5, "chat": chat},
            )
        elif action["kind"] == "gasto":
            self._gasto(chat)
        elif action["kind"] == "estado":
            # TODO fase 4: heartbeat del agente y estado de los boyeros.
            self._bus.reply(chat, "El estado de la casa llega en la fase 4.")

    def _gasto(self, chat: str) -> None:
        """Tokens y USD de Jev y DeepSeek, y el saldo que queda en DeepSeek."""
        texto = costos.resumen_texto()
        saldo = costos.saldo_deepseek(self._settings.llm_base_url, self._settings.llm_api_key)
        if saldo is not None:
            texto += f" En DeepSeek quedan USD {saldo}."
        self._bus.reply(chat, text=texto)

    def _snapshot(self, chat: str, cam: str) -> None:
        # Acuse casi instantáneo, antes de pedirle la foto a la cámara: le avisa
        # al usuario que ya está trabajando.
        self._bus.reply(chat, text=random.choice(ACKS))
        token = next(self._counter)
        with self._lock:
            self._pending[cam] = chat
            self._tokens[cam] = token
        self._bus.publish(B.cmd_snapshot(cam), {"chat": chat})
        timer = threading.Timer(PENDING_TIMEOUT, self._pending_expired, args=(cam, chat, token))
        timer.daemon = True
        timer.start()

    def _pending_expired(self, cam: str, chat: str, token: int) -> None:
        """Se dispara si la foto no volvió a tiempo. Avisa solo si sigue pendiente."""
        with self._lock:
            if self._tokens.get(cam) != token:
                return  # ya se resolvió, o llegó otro pedido más nuevo
            self._pending.pop(cam, None)
            self._tokens.pop(cam, None)
        log.warning("snapshot sin respuesta del agente", cam=cam)
        self._bus.reply(chat, text=SIN_RESPUESTA)

    def _handle_cam_event(self, topic: str, payload: dict) -> None:
        _, _, _, cam_id, evento = topic.split("/", 4)

        if evento == "snapshot":
            with self._lock:
                pendiente = self._pending.pop(cam_id, None)
                self._tokens.pop(cam_id, None)  # llegó: el timeout ya no aplica
            chat = payload.get("chat") or pendiente
            if not chat:
                log.warning("snapshot sin destinatario", cam=cam_id)
                return
            if payload.get("error"):
                self._bus.reply(chat, f"No pude sacar la foto: {payload['error']}")
                return
            if "image_b64" not in payload:
                self._bus.reply(chat, "El agente no mandó la foto.")
                return
            # La foto viene en el evento (decisión 009) y se guarda en el
            # volumen que comparte con el gateway.
            filename = Path(payload["filename"]).name
            self._settings.media_dir.mkdir(parents=True, exist_ok=True)
            image_path = self._settings.media_dir / filename
            image_path.write_bytes(base64.b64decode(payload["image_b64"], validate=True))
            # Primero la foto sola, sin texto.
            self._bus.reply(chat, image_path=str(image_path))
            # Después, en un mensaje aparte, el análisis de personas.
            veredicto = self._assistant.check_people(payload["image_b64"], cam_id)
            if veredicto:
                self._bus.reply(chat, text=veredicto)

        elif evento == "ptz":
            chat = payload.get("chat")
            if not chat:
                return
            if payload.get("error"):
                self._bus.reply(chat, f"No pude mover la cámara: {payload['error']}")
                return
            # El agente informa cómo terminó el giro: ok, tope (no se movió más)
            # o pared (se fue a un lugar sin nada y volvió). Siempre manda foto.
            lado = {"left": "izquierda", "right": "derecha"}.get(payload.get("direction"), "")
            resultado = payload.get("result", "ok")
            if resultado == "tope":
                texto = f"La cámara ya está muy a la {lado}, no da más."
            elif resultado == "pared":
                texto = f"Más a la {lado} ya se ve la pared. La dejé donde estaba."
            else:
                texto = None
            if "image_b64" in payload:
                filename = Path(payload.get("filename", f"{cam_id}-ptz.jpg")).name
                self._settings.media_dir.mkdir(parents=True, exist_ok=True)
                image_path = self._settings.media_dir / filename
                image_path.write_bytes(base64.b64decode(payload["image_b64"], validate=True))
                self._bus.reply(chat, image_path=str(image_path))
                if texto:
                    self._bus.reply(chat, text=texto)
            else:
                self._bus.reply(chat, text=texto or "Listo, la moví.")

        elif evento == "motion":
            # TODO fase 5: triage con router.triage_motion antes de despertar a nadie.
            log.info("movimiento", cam=cam_id, payload=payload)


def main() -> None:
    settings = Settings.from_env()
    inventory = Inventory.load(settings.devices_path)
    Brain(settings, inventory).run()


if __name__ == "__main__":
    main()
