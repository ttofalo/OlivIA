"""Nivel 1: el router de intents con Jev.

Cada mensaje de WhatsApp pasa por acá antes que por cualquier otra cosa. Jev
devuelve una decisión tipada con confianza calibrada en 70 a 500 ms, y las
opciones son las claves del inventario, así que no puede nombrar un dispositivo
que no existe.

Si la confianza no alcanza el umbral, el brain escala al LLM de nivel 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

from . import costos
from .config import Inventory, Settings

INTENT_CRITERIA = {
    "snapshot": "Ver una cámara ahora, pedir una foto, imagen o que le muestre algo",
    "ptz": "Mover, girar, apuntar una cámara a otro lado o llevarla a un preset",
    "preset_save": "Guardar la posición actual de una cámara con un nombre",
    "boyero_estado": "Preguntar cómo está un boyero eléctrico, sin pedir que cambie",
    "boyero_set": "Prender o apagar un boyero eléctrico",
    "estado_general": "Preguntar cómo está todo, un resumen de la casa",
    "historia": "Preguntar por algo que pasó antes, buscar una grabación",
    "gasto": "Preguntar cuánto gastamos o cuánto saldo queda en la IA, DeepSeek o Jev, tokens o plata",
    "otro": "Charla, saludo, pregunta abierta o algo que no encaja en lo anterior",
}

URGENCIA_NIVELES = [
    "Curiosidad, puede esperar",
    "Quiere verlo ahora",
    "Suena a que algo está pasando",
]


@dataclass
class Decision:
    intent: str
    intent_confidence: float
    camara: str | None
    camara_confidence: float
    boyero: str | None
    urgencia: float
    es_accion_fisica: float
    model: str
    raw: dict[str, Any]

    def confident_enough(self, threshold: float) -> bool:
        """El intent y el dispositivo tienen que pasar los dos.

        Un intent claro con una cámara dudosa termina en la cámara equivocada,
        que es peor que preguntar.
        """
        if self.intent_confidence < threshold:
            return False
        if self.intent in ("snapshot", "ptz", "preset_save"):
            return self.camara is not None and self.camara_confidence >= threshold
        if self.intent in ("boyero_estado", "boyero_set"):
            return self.boyero is not None
        return True

    def needs_confirmation(self) -> bool:
        """Acciones sobre el mundo real piden confirmación por WhatsApp.

        Mover una cámara o sacar una foto es físico pero inofensivo: nunca pide
        confirmación. La confirmación es para cortar o prender un boyero.
        """
        if self.intent in ("snapshot", "ptz", "preset_save"):
            return False
        return self.intent == "boyero_set" or self.es_accion_fisica > 0.5


class Router:
    def __init__(self, settings: Settings, inventory: Inventory) -> None:
        self._settings = settings
        self._inventory = inventory
        self._client = TypeSafeClient(api_key=settings.typesafe_api_key)

    def route(self, texto: str, contexto: dict[str, Any] | None = None) -> Decision:
        state: dict[str, Any] = {"mensaje": texto}
        if contexto:
            state["contexto"] = contexto

        response = self._client.system_one(
            model=self._settings.jev_model,
            state=state,
            questions={
                "intent": Choice(
                    instructions="Qué está pidiendo el usuario",
                    criteria=INTENT_CRITERIA,
                ),
                "camara": Choice(
                    instructions="A qué cámara se refiere el mensaje",
                    criteria=self._inventory.camara_criteria(),
                ),
                "boyero": Choice(
                    instructions="A qué boyero se refiere el mensaje",
                    criteria=self._inventory.boyero_criteria(),
                ),
                "urgencia": Score(
                    instructions="Qué tan urgente suena el pedido",
                    criteria=URGENCIA_NIVELES,
                ),
                "es_accion_fisica": Noul(
                    instructions=(
                        "El pedido implica accionar algo en el mundo real, "
                        "como cortar la corriente de un boyero o abrir un portón"
                    ),
                ),
            },
        )

        costos.anotar(
            "jev", getattr(response, "model", None), getattr(response, "usage", None), "router"
        )

        a = response.answers
        camara = a["camara"].choice
        boyero = a["boyero"].choice

        return Decision(
            intent=a["intent"].choice,
            intent_confidence=a["intent"].confidence,
            camara=None if camara == "ninguna" else camara,
            camara_confidence=a["camara"].confidence,
            boyero=None if boyero == "ninguno" else boyero,
            urgencia=a["urgencia"].score,
            es_accion_fisica=a["es_accion_fisica"].noul,
            model=response.model,
            raw={
                "intent_probabilities": a["intent"].probabilities,
                "camara_probabilities": a["camara"].probabilities,
            },
        )


def triage_motion(client: TypeSafeClient, model: str, evento: dict[str, Any]) -> tuple[str, float]:
    """Nivel 1 para alertas de movimiento.

    El NVR tira decenas de eventos por noche y la mayoría es un perro. Jev
    decide qué hacer con cada uno sin meter un LLM en el loop.
    """
    response = client.system_one(
        model=model,
        state=evento,
        questions={
            "accion": Choice(
                instructions="Qué hacer con esta detección de movimiento",
                criteria={
                    "avisar": "Avisar ahora mismo por WhatsApp con la foto",
                    "anotar": "Guardarlo para el resumen de la mañana",
                    "descartar": "Ruido, no vale la pena registrarlo",
                },
            ),
        },
    )
    a = response.answers["accion"]
    return a.choice, a.confidence
