from dataclasses import dataclass
from typing import Any

import pytest

import brain.router as router_module
from brain.config import Inventory, Settings
from brain.router import Router


@dataclass
class Respuesta:
    choice: str | None = None
    confidence: float = 0.0
    probabilities: dict[str, float] | None = None
    score: float = 0.0
    noul: float = 0.0


class ClienteFalso:
    instancia: "ClienteFalso | None" = None

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.llamada: dict[str, Any] = {}
        ClienteFalso.instancia = self

    def system_one(self, **kwargs: Any) -> Any:
        self.llamada = kwargs
        return type(
            "Resultado",
            (),
            {
                "model": "jev-falso",
                "answers": {
                    "intent": Respuesta("snapshot", 0.96, {"snapshot": 0.96}),
                    "camara": Respuesta("ninguna", 0.91, {"ninguna": 0.91}),
                    "boyero": Respuesta("ninguno", 0.88, {"ninguno": 0.88}),
                    "urgencia": Respuesta(score=0.4),
                    "es_accion_fisica": Respuesta(noul=0.1),
                },
            },
        )()


def test_route_envia_estado_y_criteria_del_inventario(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    inventario: Inventory,
) -> None:
    monkeypatch.setattr(router_module, "TypeSafeClient", ClienteFalso)
    contexto = {"chat": "familia", "ultimo_intent": "otro"}

    decision = Router(settings, inventario).route("Mostrame la entrada", contexto)

    cliente = ClienteFalso.instancia
    assert cliente is not None
    assert cliente.api_key == "clave-de-prueba"
    assert cliente.llamada["state"] == {
        "mensaje": "Mostrame la entrada",
        "contexto": contexto,
    }
    assert cliente.llamada["questions"]["camara"].criteria == inventario.camara_criteria()
    assert decision.camara is None
    assert decision.boyero is None
    assert decision.model == "jev-falso"
