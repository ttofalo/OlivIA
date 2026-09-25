"""Nivel 2: respuestas abiertas y combinación de acciones con un LLM."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

import structlog
from openai import OpenAI

from . import costos
from .config import Inventory, Settings

log = structlog.get_logger()

FALLBACK_TEXT = "No pude pensar la respuesta ahora, probá de nuevo en un rato."
NOT_CONFIGURED_TEXT = "El nivel 2 no está configurado. Falta LLM_API_KEY."


class Action(TypedDict):
    kind: Literal["snapshot", "ptz_preset", "ptz_move", "estado", "gasto"]
    camara: str | None
    preset: str | None
    direction: NotRequired[str | None]  # solo ptz_move: "left" | "right"


@dataclass
class Reply:
    text: str | None
    actions: list[Action]


class Assistant:
    def __init__(self, settings: Settings, inventory: Inventory, client=None) -> None:
        self._settings = settings
        self._inventory = inventory
        self._client = client
        if self._client is None and settings.llm_api_key:
            self._client = OpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                timeout=settings.llm_timeout,
            )

    def check_people(self, image_b64: str, camara: str) -> str | None:
        """Mira la foto buscando SOLO personas y devuelve un veredicto corto.

        Usa el modelo con visión. Si no hay LLM o falla, devuelve None y quien
        llama manda la foto igual, sin análisis.
        """
        if not self._settings.llm_api_key:
            return None
        system = (
            "Sos OlivIA, la seguridad de una casa. Te paso una captura de una "
            "cámara. Tu única tarea es mirar con MUCHA atención si hay PERSONAS. "
            "Respondé muy breve, una sola línea, castellano rioplatense. Si NO hay "
            "nadie, decí algo como 'No se ve a nadie, todo tranquilo'. Si ves una o "
            "más personas, avisá claro, empezando con 'Ojo' y dónde están. No "
            "describas el paisaje, los muebles ni la vegetación: solo personas. "
            "Sin emojis."
        )
        try:
            # Sin reintentos y con timeout corto: si la visión falla, la foto ya
            # salió y no hay que bloquear el brain hasta 60 s esperándola.
            vision = self._client.with_options(timeout=8.0, max_retries=0)
            response = vision.chat.completions.create(
                model=self._settings.llm_vision_model,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Cámara {self._inventory.nombre(camara)}. ¿Hay alguien?",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                            },
                        ],
                    },
                ],
                temperature=0.3,
                # Alto a propósito: estos modelos razonan y con poco presupuesto
                # gastan todo en el razonamiento y devuelven vacío.
                max_tokens=400,
                extra_body={"effort": self._settings.llm_effort}
                if self._settings.llm_effort
                else {},
            )
            costos.anotar(
                "deepseek",
                getattr(response, "model", None) or self._settings.llm_vision_model,
                getattr(response, "usage", None),
                "vision",
            )
            texto = response.choices[0].message.content
            return texto.strip() if texto and texto.strip() else None
        except Exception:
            log.exception("no pude describir la imagen", model=self._settings.llm_vision_model)
            return None

    def answer(
        self,
        texto: str,
        historial: list[dict] | None = None,
        ultima_camara: str | None = None,
    ) -> Reply:
        if not self._settings.llm_api_key:
            return Reply(text=NOT_CONFIGURED_TEXT, actions=[])

        system = self._system_prompt()
        if ultima_camara:
            # Contexto mínimo de conversación: "movela a la derecha" sin decir
            # cuál se refiere a la última cámara que se usó en este chat.
            system += (
                f"\n\nLa última cámara usada en este chat fue '{ultima_camara}'. "
                "Si el pedido no nombra una cámara, es esa. No preguntes cuál."
            )
        messages = [{"role": "system", "content": system}]
        if historial:
            messages.extend(historial)
        messages.append({"role": "user", "content": texto})

        try:
            kwargs = {
                "model": self._settings.llm_model,
                "messages": messages,
                "tools": self._tools(),
                "tool_choice": "auto",
                "max_tokens": self._settings.llm_max_tokens,
            }
            if self._settings.llm_effort:
                kwargs["extra_body"] = {"effort": self._settings.llm_effort}
            response = self._client.chat.completions.create(**kwargs)
            costos.anotar(
                "deepseek",
                getattr(response, "model", None) or self._settings.llm_model,
                getattr(response, "usage", None),
                "chat",
            )
            message = response.choices[0].message
            text = message.content.strip() if message.content and message.content.strip() else None
            actions = self._actions_from(message.tool_calls or [])
            return Reply(text=text, actions=actions)
        except Exception:
            log.exception("falló el LLM de nivel 2", model=self._settings.llm_model)
            return Reply(text=FALLBACK_TEXT, actions=[])

    def _system_prompt(self) -> str:
        return (
            "Sos OlivIA, la asistente de una casa. Le contestás a la familia por "
            "WhatsApp, en castellano rioplatense, como una persona.\n\n"
            "Tu ÚNICO tema es la casa: cámaras, fotos, movimiento de cámaras, "
            "boyeros, pileta, temperatura, seguridad, y lo que vos podés hacer. "
            "Cualquier otra cosa (programación, cultura general, tareas, cuentas, "
            "chistes, consejos, noticias, lo que sea fuera de la casa) NO la "
            "respondés, sin excepción ni aunque insistan: contestás en una frase "
            "que solo te ocupás de la casa, y nada más. No explicás, no ayudás "
            "'un poquito', no das el dato igual.\n\n"
            "Cómo escribís:\n"
            "- Corto. Una o dos frases. Como un mensaje de WhatsApp, no un mail.\n"
            "- Prohibido usar emojis. Ninguno, nunca.\n"
            "- Nada de listas, viñetas ni títulos. Texto corrido.\n"
            "- Nada de relleno: no digas 'te aviso con honestidad', 'genial', "
            "'perfecto', 'claro que sí', ni cierres con '¿querés que...?' o "
            "'¿en qué te ayudo?'. Andá al grano.\n"
            "- No repitas la pregunta ni anuncies lo que vas a hacer.\n"
            "- A las cámaras las nombrás con su nombre de persona (Cabaña, Frente, "
            "Cochera, Fondo), nunca con el id interno como 'cabania'. Los ids son "
            "solo para llamar a las tools.\n\n"
            "Qué podés hacer: sacar una foto de una cámara (sacar_foto), mover una "
            "cámara a un punto guardado, los presets del inventario (mover_camara), "
            "y girarla un poco a la izquierda o la derecha (girar_camara). Si "
            "preguntan cuánto gastamos en IA o el saldo, usá consultar_gasto: ese "
            "dato se manda por Telegram, no lo digas vos ni inventes un número. "
            "Lo que todavía no anda: boyeros, "
            "temperatura de la pileta, avisos solos; si preguntan, decilo en una "
            "frase, sin vueltas. No inventes cámaras ni presets. Inventario:\n\n"
            f"{self._inventory_text()}"
        )

    def _inventory_text(self) -> str:
        lines = ["Cámaras:"]
        if not self._inventory.camaras:
            lines.append("- ninguna")
        for camara, datos in self._inventory.camaras.items():
            nombre = self._inventory.nombre(camara)
            descripcion = datos.get("descripcion") or nombre
            presets = ", ".join(self._presets(camara)) or "ninguno"
            # El id (cabania) es solo para las tools; a la gente se le habla con
            # el nombre (Cabaña).
            lines.append(
                f"- {nombre} [id para tools: {camara}]: {str(descripcion).strip()}. "
                f"Presets: {presets}"
            )

        lines.append("Boyeros:")
        if not self._inventory.boyeros:
            lines.append("- ninguno")
        for boyero, datos in self._inventory.boyeros.items():
            descripcion = datos.get("descripcion") or datos.get("nombre") or boyero
            lines.append(f"- {boyero}: {str(descripcion).strip()}")
        return "\n".join(lines)

    def _tools(self) -> list[dict]:
        camaras = list(self._inventory.camaras)
        presets = sorted(
            {preset for camara in self._inventory.camaras for preset in self._presets(camara)}
        )
        presets_por_camara = "; ".join(
            f"{camara}: {', '.join(self._presets(camara)) or 'ninguno'}"
            for camara in self._inventory.camaras
        )
        return [
            {
                "type": "function",
                "function": {
                    "name": "sacar_foto",
                    "description": "Saca una foto actual de una cámara.",
                    "parameters": {
                        "type": "object",
                        "properties": {"camara": {"type": "string", "enum": camaras}},
                        "required": ["camara"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mover_camara",
                    "description": f"Mueve una cámara a uno de sus presets. {presets_por_camara}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "camara": {"type": "string", "enum": camaras},
                            "preset": {"type": "string", "enum": presets},
                        },
                        "required": ["camara", "preset"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "girar_camara",
                    "description": (
                        "Gira una cámara un poco hacia un lado, sin ir a un preset. "
                        "Para 'movela a la derecha', 'un poco más a la izquierda'."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "camara": {"type": "string", "enum": camaras},
                            "direccion": {"type": "string", "enum": ["izquierda", "derecha"]},
                        },
                        "required": ["camara", "direccion"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "consultar_gasto",
                    "description": (
                        "Cuánto se gastó en IA (DeepSeek y Jev), tokens y USD. El dato "
                        "no se manda por acá, se manda por Telegram: la tool solo avisa "
                        "eso, no des vos el número ni digas cuánto es."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "consultar_estado",
                    "description": "Consulta el estado general de la casa o sus equipos.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "que": {
                                "type": "string",
                                "enum": ["casa", "boyeros", "agente"],
                            }
                        },
                        "required": ["que"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def _actions_from(self, tool_calls) -> list[Action]:
        actions: list[Action] = []
        for call in tool_calls:
            name = call.function.name
            try:
                arguments = json.loads(call.function.arguments)
            except (json.JSONDecodeError, TypeError):
                log.warning("tool call descartada", tool=name, motivo="argumentos inválidos")
                continue
            if not isinstance(arguments, dict):
                log.warning("tool call descartada", tool=name, motivo="argumentos inválidos")
                continue

            action = self._action(name, arguments)
            if action is not None:
                actions.append(action)
        return actions

    def _action(self, name: str, arguments: dict) -> Action | None:
        if name == "sacar_foto":
            camara = arguments.get("camara")
            if not isinstance(camara, str) or camara not in self._inventory.camaras:
                self._log_invalid(name, camara=camara)
                return None
            return {"kind": "snapshot", "camara": camara, "preset": None}

        if name == "mover_camara":
            camara = arguments.get("camara")
            preset = arguments.get("preset")
            if (
                not isinstance(camara, str)
                or camara not in self._inventory.camaras
                or not isinstance(preset, str)
                or preset not in self._presets(camara)
            ):
                self._log_invalid(name, camara=camara, preset=preset)
                return None
            return {"kind": "ptz_preset", "camara": camara, "preset": preset}

        if name == "girar_camara":
            camara = arguments.get("camara")
            direccion = arguments.get("direccion")
            if (
                not isinstance(camara, str)
                or camara not in self._inventory.camaras
                or direccion not in ("izquierda", "derecha")
            ):
                self._log_invalid(name, camara=camara, direccion=direccion)
                return None
            return {
                "kind": "ptz_move",
                "camara": camara,
                "preset": None,
                "direction": "left" if direccion == "izquierda" else "right",
            }

        if name == "consultar_gasto":
            return {"kind": "gasto", "camara": None, "preset": None}

        if name == "consultar_estado":
            que = arguments.get("que")
            if que not in ("casa", "boyeros", "agente"):
                self._log_invalid(name, que=que)
                return None
            return {"kind": "estado", "camara": None, "preset": None}

        self._log_invalid(name)
        return None

    def _presets(self, camara: str) -> list[str]:
        datos = self._inventory.camaras.get(camara, {})
        presets = datos.get("presets", {})
        if isinstance(presets, dict):
            return list(presets)
        if isinstance(presets, list):
            return [preset for preset in presets if isinstance(preset, str)]
        return []

    @staticmethod
    def _log_invalid(tool: str, **arguments) -> None:
        log.warning("tool call descartada", tool=tool, motivo="fuera del inventario", **arguments)
