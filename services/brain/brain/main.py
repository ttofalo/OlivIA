"""Punto de entrada del brain.

Fase 1: consume wsp/in, rutea con Jev y despacha comandos al agente.
Fase 2: transcribe audios y escala al LLM de nivel 2 cuando Jev duda.
Lo que falta está marcado con TODO y tiene su fase en docs/ROADMAP.md.
"""

from __future__ import annotations

import base64
import json
import random
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from . import bus as B
from . import costos
from . import telegram as T
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

# Whisper local cuando la API de transcripción falla. "base" tarda unos 2 s
# en la VPS; uno más grande es más preciso pero tarda el triple.
TRANSCRIBE_FALLBACK_MODEL = "base"

NO_ENTENDI = "No te entendí bien. ¿De qué cámara me hablás?"

# "no me pases foto", "sin foto", "no quiero fotos": Jev lo clasifica como
# snapshot igual, así que el brain lo manda al LLM, que sabe revisar sin foto.
NO_QUIERE_FOTO = re.compile(r"\b(no|sin)\b[^.?!]{0,25}\bfotos?\b", re.IGNORECASE)


@dataclass(eq=False)
class Ronda:
    """Las cámaras de un mismo pedido. Un acuse al empezar y un solo mensaje
    con el resultado de todas al terminar, en vez de uno por cámara."""

    chat: str
    # cámara -> "foto" (manda la imagen) o "revisar" (solo el análisis)
    modos: dict[str, str]
    resultados: dict[str, str | None] = field(default_factory=dict)
    # Cámaras cuya foto ya llegó y se está analizando: el timeout no las toca.
    en_proceso: set[str] = field(default_factory=set)
    sin_respuesta: set[str] = field(default_factory=set)
    cerrada: bool = False


BIENVENIDA = (
    "Hola, soy OlivIA. Te muestro las cámaras de la casa, las muevo y te "
    "aviso si hay alguien. Pedime lo que necesites."
)


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
        # Qué ronda espera la foto de cada cámara en vuelo.
        self._pending: dict[str, Ronda] = {}
        # Última cámara usada por chat, para que "movela a la derecha" sin
        # nombrar cámara se entienda.
        self._last_cam: dict[str, str] = {}
        # Los handlers corren en hilos del pool: el estado en vuelo va con lock.
        self._lock = threading.Lock()
        # Chats que ya recibieron el mensaje de bienvenida, persistido para
        # que un reinicio no salude de nuevo a quien ya conoce al bot.
        self._chats_path = self._settings.media_dir / "chats_conocidos.json"
        self._chats_conocidos: set[str] = self._cargar_chats_conocidos()

    def run(self) -> None:
        self._bus.on_message(self._handle)
        self._bus.connect()
        self._bus.subscribe(B.TOPIC_IN, B.EVT_CAM, B.EVT_BOYERO, B.EVT_AGENT)
        self._iniciar_escucha_telegram()
        log.info("brain arriba", threshold=self._settings.jev_threshold)
        self._bus.loop_forever()

    def _iniciar_escucha_telegram(self) -> None:
        # El gasto se consulta por Telegram, no por WhatsApp. Sin credenciales
        # configuradas, no hay nada que escuchar.
        s = self._settings
        if not s.telegram_bot_token or not s.telegram_chat_id:
            return
        hilo = threading.Thread(
            target=T.escuchar,
            args=(s.telegram_bot_token, s.telegram_chat_id, lambda _texto: self._resumen_gasto()),
            daemon=True,
            name="telegram-gasto",
        )
        hilo.start()

    def _handle(self, topic: str, payload: dict) -> None:
        if topic == B.TOPIC_IN:
            self._handle_inbound(payload)
        elif topic.startswith("casa/evt/cam/"):
            self._handle_cam_event(topic, payload)
        else:
            log.debug("evento sin handler", topic=topic)

    def _cargar_chats_conocidos(self) -> set[str]:
        try:
            datos = json.loads(self._chats_path.read_text(encoding="utf-8"))
            return set(datos)
        except (OSError, json.JSONDecodeError):
            return set()

    def _saludar_si_es_nuevo(self, chat: str) -> None:
        with self._lock:
            if chat in self._chats_conocidos:
                return
            self._chats_conocidos.add(chat)
            try:
                self._settings.media_dir.mkdir(parents=True, exist_ok=True)
                self._chats_path.write_text(
                    json.dumps(sorted(self._chats_conocidos)), encoding="utf-8"
                )
            except OSError:
                log.exception("no pude guardar los chats conocidos")
        self._bus.reply(chat, text=BIENVENIDA)

    def _handle_inbound(self, msg: dict) -> None:
        chat = msg["chat"]
        texto = msg.get("text", "")
        self._saludar_si_es_nuevo(chat)

        audio = msg.get("kind") == "audio"
        if audio:
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
            self._escalate(chat, texto, audio)
            return

        if decision.needs_confirmation():
            # TODO fase 4: guardar la acción pendiente y esperar el sí.
            self._bus.reply(chat, "Eso toca algo físico. Todavía no lo tengo habilitado.")
            return

        self._dispatch(chat, texto, decision, audio)

    def _transcribir(self, chat: str, media_path: str | None) -> str | None:
        if not media_path:
            self._bus.reply(chat, "Me llegó un audio vacío.")
            return None
        s = self._settings
        # Vocabulario para Whisper: sin esto, "Cabaña" sale "campaña".
        prompt = "OlivIA, cámaras: " + ", ".join(
            self._inventory.nombre(c) for c in self._inventory.camaras
        )
        try:
            texto = transcribe(
                Path(media_path),
                s.transcribe_backend,
                s.transcribe_model,
                s.transcribe_api_base_url,
                s.transcribe_api_key,
                prompt=prompt,
            )
        except TranscribeError as exc:
            log.warning("audio sin transcribir", error=str(exc), backend=s.transcribe_backend)
            texto = None
            if s.transcribe_backend == "api":
                # Si la API se cae, Whisper local en la VPS: más lento y menos
                # preciso, pero el audio no se pierde.
                try:
                    texto = transcribe(
                        Path(media_path), "local", TRANSCRIBE_FALLBACK_MODEL, prompt=prompt
                    )
                except TranscribeError as exc_local:
                    log.warning("audio sin transcribir en local", error=str(exc_local))
            if texto is None:
                self._bus.reply(chat, "No pude entender el audio. ¿Me lo escribís?")
                return None
        log.info("audio transcripto", texto=texto)
        return texto

    def _dispatch(self, chat: str, texto: str, decision: Decision, audio: bool = False) -> None:
        if decision.camara:
            self._last_cam[chat] = decision.camara
        if decision.intent == "snapshot" and decision.camara:
            if NO_QUIERE_FOTO.search(texto):
                self._escalate(chat, texto, audio)
                return
            modos = {decision.camara: "foto"}
            self._pedir_camaras(chat, modos, acuse=self._confirmar(modos) if audio else None)
            return

        if decision.intent == "gasto":
            self._gasto(chat)
            return

        if decision.intent == "ptz" and decision.camara:
            # Jev da la cámara pero no el destino. El LLM tiene los presets
            # como enum y saca el "al portón" del texto.
            self._escalate(chat, texto, audio)
            return

        # Cualquier otra cosa (preguntas abiertas, "qué podés hacer", charla)
        # va al LLM de nivel 2 en vez de una respuesta enlatada.
        self._escalate(chat, texto, audio)

    def _confirmar(self, modos: dict[str, str]) -> str:
        """Acuse de un audio: repite qué entendió, para que quien habló sepa
        que se entendió bien antes de ver el resultado."""

        def lista(cams: list[str]) -> str:
            nombres = [self._inventory.nombre(c) for c in cams]
            return (
                nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
            )

        fotos = [c for c, m in modos.items() if m == "foto"]
        revisar = [c for c, m in modos.items() if m == "revisar"]
        partes = []
        if fotos:
            partes.append(f"{'Foto' if len(fotos) == 1 else 'Fotos'} de {lista(fotos)}")
        if revisar:
            partes.append(f"{'reviso' if partes else 'Reviso'} {lista(revisar)}")
        return ", ".join(partes) + ", dale."

    def _escalate(self, chat: str, texto: str, audio: bool = False) -> None:
        """Nivel 2: el LLM interpreta lo que Jev no pudo."""
        reply = self._assistant.answer(texto, ultima_camara=self._last_cam.get(chat))
        # Las fotos y revisiones del mismo pedido van juntas en una ronda.
        modos: dict[str, str] = {}
        for action in reply.actions:
            cam = action["camara"]
            if action["kind"] in ("snapshot", "revisar") and cam:
                self._last_cam[chat] = cam
                # Si pidió la misma cámara con foto y sin foto, gana sin foto.
                if modos.get(cam) != "revisar":
                    modos[cam] = "foto" if action["kind"] == "snapshot" else "revisar"
            else:
                self._run_action(chat, action, audio)
        confirmado = audio and any(
            a["kind"] in ("snapshot", "revisar", "ptz_move", "ptz_preset") for a in reply.actions
        )
        if modos:
            # El texto del LLM hace de acuse: así sale uno solo. Con audio, el
            # acuse es la confirmación de lo que se entendió.
            self._pedir_camaras(chat, modos, acuse=self._confirmar(modos) if audio else reply.text)
        elif reply.text and not confirmado:
            self._bus.reply(chat, reply.text)
        elif not reply.actions:
            self._bus.reply(chat, NO_ENTENDI)

    def _run_action(self, chat: str, action: Action, audio: bool = False) -> None:
        cam = action["camara"]
        if cam:
            self._last_cam[chat] = cam
        if action["kind"] in ("snapshot", "revisar") and cam:
            modos = {cam: "foto" if action["kind"] == "snapshot" else "revisar"}
            self._pedir_camaras(chat, modos, acuse=self._confirmar(modos) if audio else None)
        elif action["kind"] == "ptz_preset" and cam and action["preset"]:
            presets = self._inventory.camaras.get(cam, {}).get("presets") or {}
            numero = presets.get(action["preset"])
            if numero is None:
                log.warning("preset sin número", cam=cam, preset=action["preset"])
                return
            if audio:
                self._bus.reply(
                    chat, text=f"{self._inventory.nombre(cam)} al {action['preset']}, dale."
                )
            self._bus.publish(B.cmd_ptz(cam), {"preset": numero, "chat": chat})
        elif action["kind"] == "ptz_move" and cam and action.get("direction"):
            # Giro corto y acotado; el agente verifica que no quede mirando la pared.
            lado = "derecha" if action["direction"] == "right" else "izquierda"
            acuse = f"{self._inventory.nombre(cam)} a la {lado}, dale."
            self._bus.reply(chat, text=acuse if audio else random.choice(ACKS))
            self._bus.publish(
                B.cmd_ptz(cam),
                {"direction": action["direction"], "duration": 0.6, "speed": 0.5, "chat": chat},
            )
        elif action["kind"] == "gasto":
            self._gasto(chat)
        elif action["kind"] == "estado":
            # TODO fase 4: heartbeat del agente y estado de los boyeros.
            self._bus.reply(chat, "El estado de la casa llega en la fase 4.")

    def _resumen_gasto(self) -> str:
        """Tokens y USD de Jev y DeepSeek, y el saldo que queda en DeepSeek."""
        texto = costos.resumen_texto()
        saldo = costos.saldo_deepseek(self._settings.llm_base_url, self._settings.llm_api_key)
        if saldo is not None:
            texto += f" En DeepSeek quedan USD {saldo}."
        return texto

    def _gasto(self, chat: str) -> None:
        # El gasto se consulta por Telegram, no por WhatsApp: es un dato de
        # la operación de la casa, no algo para un chat familiar. Igual se
        # manda a Telegram en el momento, para no dejar a quien preguntó sin
        # el dato en ningún lado.
        self._bus.reply(chat, text="Ese dato te lo paso por Telegram, ahí lo tenés.")
        T.notificar(
            self._resumen_gasto(),
            self._settings.telegram_bot_token,
            self._settings.telegram_chat_id,
        )

    def _pedir_camaras(self, chat: str, modos: dict[str, str], acuse: str | None = None) -> None:
        # Acuse casi instantáneo, antes de pedirle la foto a las cámaras: le
        # avisa al usuario que ya está trabajando. Uno por pedido, no por cámara.
        self._bus.reply(chat, text=acuse or random.choice(ACKS))
        ronda = Ronda(chat=chat, modos=dict(modos))
        with self._lock:
            for cam in ronda.modos:
                self._pending[cam] = ronda
        for cam in ronda.modos:
            self._bus.publish(B.cmd_snapshot(cam), {"chat": chat})
        timer = threading.Timer(PENDING_TIMEOUT, self._ronda_vencida, args=(ronda,))
        timer.daemon = True
        timer.start()

    def _ronda_vencida(self, ronda: Ronda) -> None:
        """Las cámaras que no mandaron la foto a tiempo cuentan como sin respuesta."""
        with self._lock:
            for cam in ronda.modos:
                if cam in ronda.resultados or cam in ronda.en_proceso:
                    continue
                if self._pending.get(cam) is ronda:
                    del self._pending[cam]
                ronda.resultados[cam] = None
                ronda.sin_respuesta.add(cam)
                log.warning("snapshot sin respuesta del agente", cam=cam)
        self._cerrar_si_completa(ronda)

    def _anotar(self, ronda: Ronda, cam: str, linea: str | None) -> None:
        with self._lock:
            ronda.resultados[cam] = linea
            ronda.en_proceso.discard(cam)
        self._cerrar_si_completa(ronda)

    def _cerrar_si_completa(self, ronda: Ronda) -> None:
        with self._lock:
            if ronda.cerrada or len(ronda.resultados) < len(ronda.modos):
                return
            ronda.cerrada = True
        if ronda.sin_respuesta == set(ronda.modos):
            self._bus.reply(ronda.chat, text=SIN_RESPUESTA)
            return
        lineas = []
        for cam in ronda.modos:
            if cam in ronda.sin_respuesta:
                lineas.append(f"{self._inventory.nombre(cam)}: no me contestó.")
            elif ronda.resultados[cam]:
                lineas.append(ronda.resultados[cam])
        if lineas:
            self._bus.reply(ronda.chat, text="\n".join(lineas))

    def _resultado_snapshot(self, ronda: Ronda, cam: str, payload: dict) -> None:
        nombre = self._inventory.nombre(cam)
        modo = ronda.modos[cam]
        # Una sola foto pedida: los textos de siempre, sin el nombre adelante.
        sola = len(ronda.modos) == 1 and modo == "foto"

        if payload.get("error") or "image_b64" not in payload:
            if sola:
                linea = (
                    f"No pude sacar la foto: {payload['error']}"
                    if payload.get("error")
                    else "El agente no mandó la foto."
                )
            else:
                motivo = str(payload.get("error") or "el agente no mandó la foto")
                linea = f"{nombre}: no la pude ver ({motivo.removeprefix(f'{cam}: ')})."
            self._anotar(ronda, cam, linea)
            return

        if modo == "foto":
            # La foto viene en el evento (decisión 009) y se guarda en el
            # volumen que comparte con el gateway. Sale apenas llega, con el
            # nombre de la cámara de pie de foto.
            filename = Path(payload["filename"]).name
            self._settings.media_dir.mkdir(parents=True, exist_ok=True)
            image_path = self._settings.media_dir / filename
            image_path.write_bytes(base64.b64decode(payload["image_b64"], validate=True))
            self._bus.reply(chat=ronda.chat, text=nombre, image_path=str(image_path))

        # El análisis de personas va en el mensaje único del final.
        veredicto = self._assistant.check_people(payload["image_b64"], cam)
        if sola:
            linea = veredicto
        elif veredicto:
            linea = f"{nombre}: {veredicto}"
        elif modo == "revisar":
            linea = f"{nombre}: no la pude analizar."
        else:
            linea = None
        self._anotar(ronda, cam, linea)

    def _handle_cam_event(self, topic: str, payload: dict) -> None:
        _, _, _, cam_id, evento = topic.split("/", 4)

        if evento == "snapshot":
            with self._lock:
                ronda = self._pending.pop(cam_id, None)
                if ronda is not None:
                    ronda.en_proceso.add(cam_id)
            if ronda is None:
                # Llegó tarde o nadie la pidió: no se manda, porque puede ser
                # de una revisión donde dijeron que no querían foto.
                log.warning("snapshot sin pedido en curso", cam=cam_id)
                return
            self._resultado_snapshot(ronda, cam_id, payload)

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
                self._bus.reply(
                    chat, text=self._inventory.nombre(cam_id), image_path=str(image_path)
                )
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
