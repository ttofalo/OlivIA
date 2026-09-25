"""El brain de punta a punta, con Jev, el LLM y el bus falsos."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import pytest

import brain.main as main_module
from brain.llm import Reply
from brain.main import NO_ENTENDI, Brain
from brain.router import Decision


class BusFalso:
    def __init__(self, _settings) -> None:
        self.published: list[tuple[str, dict]] = []
        self.replies: list[dict] = []

    def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))

    def reply(self, chat: str, text: str | None = None, image_path: str | None = None) -> None:
        self.replies.append({"chat": chat, "text": text, "image_path": image_path})

    def set_nombres(self, nombres: dict[str, str]) -> None:
        self.nombres = nombres


@dataclass
class RouterFalso:
    decision: Decision
    textos: list[str] = field(default_factory=list)

    def __call__(self, _settings, _inventory) -> RouterFalso:
        return self

    def route(self, texto: str, contexto: Any = None) -> Decision:
        self.textos.append(texto)
        return self.decision


@dataclass
class AssistantFalso:
    reply: Reply
    textos: list[str] = field(default_factory=list)

    def __call__(self, _settings, _inventory) -> AssistantFalso:
        return self

    def answer(self, texto: str, historial=None, ultima_camara=None) -> Reply:
        self.textos.append(texto)
        return self.reply

    def check_people(self, image_b64: str, camara: str) -> str | None:
        return None  # sin visión en los tests: se manda solo la foto


def decision(intent: str, conf: float, camara: str | None = None, cam_conf: float = 0.95):
    return Decision(
        intent=intent,
        intent_confidence=conf,
        camara=camara,
        camara_confidence=cam_conf,
        boyero=None,
        urgencia=0.0,
        es_accion_fisica=0.0,
        model="jev-falso",
        raw={},
    )


@pytest.fixture
def armar(monkeypatch, settings, inventario):
    """Construye un Brain con las piezas falsas que le pases."""

    def _armar(
        router: RouterFalso, assistant: AssistantFalso | None = None
    ) -> tuple[Brain, BusFalso]:
        assistant = assistant or AssistantFalso(Reply(text=None, actions=[]))
        monkeypatch.setattr(main_module, "Router", router)
        monkeypatch.setattr(main_module, "Assistant", assistant)
        monkeypatch.setattr(main_module.B, "Bus", BusFalso)
        brain = Brain(settings, inventario)
        return brain, brain._bus

    return _armar


def test_snapshot_seguro_publica_el_comando(armar):
    brain, bus = armar(RouterFalso(decision("snapshot", 0.95, "entrada")))

    brain._handle_inbound({"chat": "c1", "text": "foto de la entrada", "kind": "text"})

    assert bus.published == [("casa/cmd/cam/entrada/snapshot", {"chat": "c1"})]
    assert brain._pending["entrada"].chat == "c1"
    assert brain._pending["entrada"].modos == {"entrada": "foto"}


def test_jev_snapshot_con_no_me_pases_foto_va_al_llm(armar):
    llm = AssistantFalso(
        Reply(text=None, actions=[{"kind": "revisar", "camara": "entrada", "preset": None}])
    )
    brain, _ = armar(RouterFalso(decision("snapshot", 0.95, "entrada")), llm)

    brain._handle_inbound(
        {"chat": "c1", "text": "revisá la entrada, no me pases foto", "kind": "text"}
    )

    assert llm.textos == ["revisá la entrada, no me pases foto"]
    assert brain._pending["entrada"].modos == {"entrada": "revisar"}


def test_jev_dudoso_escala_al_llm_y_ejecuta_sus_acciones(armar):
    llm = AssistantFalso(
        Reply(text="Ahí va", actions=[{"kind": "snapshot", "camara": "patio", "preset": None}])
    )
    brain, bus = armar(RouterFalso(decision("snapshot", 0.4)), llm)

    brain._handle_inbound({"chat": "c1", "text": "mostrame atrás", "kind": "text"})

    assert llm.textos == ["mostrame atrás"]
    assert bus.published == [("casa/cmd/cam/patio/snapshot", {"chat": "c1"})]
    # Primero la bienvenida (chat nuevo), después el texto del LLM, que hace
    # de acuse: uno solo, no el del LLM más uno enlatado.
    assert bus.replies == [
        {"chat": "c1", "text": main_module.BIENVENIDA, "image_path": None},
        {"chat": "c1", "text": "Ahí va", "image_path": None},
    ]


def test_llm_sin_texto_ni_acciones_pide_que_repita(armar):
    brain, bus = armar(RouterFalso(decision("otro", 0.3)))

    brain._handle_inbound({"chat": "c1", "text": "eh", "kind": "text"})

    assert bus.replies[-1]["text"] == NO_ENTENDI


def test_ptz_traduce_el_preset_a_numero(armar, inventario):
    inventario.camaras["entrada"]["presets"] = {"porton": 1, "camino": 2}
    llm = AssistantFalso(
        Reply(text=None, actions=[{"kind": "ptz_preset", "camara": "entrada", "preset": "camino"}])
    )
    brain, bus = armar(RouterFalso(decision("ptz", 0.95, "entrada")), llm)

    brain._handle_inbound({"chat": "c1", "text": "apuntá la entrada al camino", "kind": "text"})

    assert bus.published == [("casa/cmd/cam/entrada/ptz", {"preset": 2, "chat": "c1"})]
    # Sin acuse de texto propio del ptz_preset; solo la bienvenida por ser
    # chat nuevo.
    assert bus.replies == [{"chat": "c1", "text": main_module.BIENVENIDA, "image_path": None}]


def test_audio_se_transcribe_antes_de_rutear(armar, monkeypatch, tmp_path):
    router = RouterFalso(decision("snapshot", 0.95, "entrada"))
    brain, bus = armar(router)
    monkeypatch.setattr(main_module, "transcribe", lambda *a, **k: "foto de la entrada")

    brain._handle_inbound({"chat": "c1", "kind": "audio", "mediaPath": str(tmp_path / "a.ogg")})

    assert router.textos == ["foto de la entrada"]
    assert bus.published[0][0] == "casa/cmd/cam/entrada/snapshot"


def test_audio_que_falla_avisa_y_no_rutea(armar, monkeypatch):
    router = RouterFalso(decision("snapshot", 0.95, "entrada"))
    brain, bus = armar(router)

    def falla(*_a, **_k):
        raise main_module.TranscribeError("ruido")

    monkeypatch.setattr(main_module, "transcribe", falla)

    brain._handle_inbound({"chat": "c1", "kind": "audio", "mediaPath": "/x.ogg"})

    assert router.textos == []
    assert "audio" in bus.replies[-1]["text"]


def test_evento_snapshot_guarda_la_foto_y_la_manda(armar, settings):
    brain, bus = armar(RouterFalso(decision("otro", 0.9)))
    brain._pedir_camaras("c1", {"entrada": "foto"})
    bus.replies.clear()
    foto = b"\x89PNG-falso"

    brain._handle_cam_event(
        "casa/evt/cam/entrada/snapshot",
        {"image_b64": base64.b64encode(foto).decode(), "filename": "../entrada-1.png"},
    )

    guardada = settings.media_dir / "entrada-1.png"
    assert guardada.read_bytes() == foto
    # El pie de foto es el nombre de la cámara, no el análisis. Sin visión
    # (fake devuelve None), no llega un segundo mensaje.
    assert bus.replies == [{"chat": "c1", "text": "Entrada", "image_path": str(guardada)}]
    assert brain._pending == {}


def test_evento_snapshot_con_error_lo_cuenta(armar):
    brain, bus = armar(RouterFalso(decision("otro", 0.9)))
    brain._pedir_camaras("c1", {"entrada": "foto"})

    brain._handle_cam_event("casa/evt/cam/entrada/snapshot", {"chat": "c1", "error": "timeout"})

    assert bus.replies[-1]["text"] == "No pude sacar la foto: timeout"


FOTO_B64 = base64.b64encode(b"\xff\xd8-falso").decode()


class AssistantConVision(AssistantFalso):
    def check_people(self, image_b64: str, camara: str) -> str | None:
        return "No se ve a nadie."


def test_revisar_varias_camaras_un_acuse_un_mensaje_y_ninguna_foto(armar, inventario):
    inventario.camaras["fondo"] = {"nombre": "Fondo"}
    llm = AssistantConVision(
        Reply(
            text=None,
            actions=[
                {"kind": "revisar", "camara": c, "preset": None}
                for c in ("entrada", "patio", "fondo")
            ],
        )
    )
    brain, bus = armar(RouterFalso(decision("otro", 0.3)), llm)

    brain._handle_inbound({"chat": "c1", "text": "todo ok? no me pases foto", "kind": "text"})
    evt = {"chat": "c1", "image_b64": FOTO_B64, "filename": "x.jpg"}
    brain._handle_cam_event("casa/evt/cam/entrada/snapshot", evt)
    brain._handle_cam_event(
        "casa/evt/cam/patio/snapshot",
        {"chat": "c1", "error": "patio: no pude conectar con la cámara"},
    )
    brain._handle_cam_event("casa/evt/cam/fondo/snapshot", evt)

    textos = [r["text"] for r in bus.replies[1:]]  # sin la bienvenida
    assert all(r["image_path"] is None for r in bus.replies)
    assert len(textos) == 2
    assert textos[0] in main_module.ACKS
    assert textos[1] == (
        "Entrada: No se ve a nadie.\n"
        "Patio: no la pude ver (no pude conectar con la cámara).\n"
        "Fondo: No se ve a nadie."
    )


def test_fotos_de_varias_camaras_salen_y_el_analisis_va_junto(armar):
    llm = AssistantConVision(
        Reply(
            text=None,
            actions=[
                {"kind": "snapshot", "camara": c, "preset": None} for c in ("entrada", "patio")
            ],
        )
    )
    brain, bus = armar(RouterFalso(decision("otro", 0.3)), llm)

    brain._handle_inbound({"chat": "c1", "text": "fotos de todas", "kind": "text"})
    for cam in ("entrada", "patio"):
        brain._handle_cam_event(
            f"casa/evt/cam/{cam}/snapshot",
            {"chat": "c1", "image_b64": FOTO_B64, "filename": f"{cam}.jpg"},
        )

    fotos = [r for r in bus.replies if r["image_path"]]
    assert [f["text"] for f in fotos] == ["Entrada", "Patio"]
    assert bus.replies[-1]["text"] == "Entrada: No se ve a nadie.\nPatio: No se ve a nadie."


def test_ronda_vencida_avisa_las_que_no_contestaron(armar):
    brain, bus = armar(RouterFalso(decision("otro", 0.9)), AssistantConVision(Reply(None, [])))
    brain._pedir_camaras("c1", {"entrada": "revisar", "patio": "revisar"})
    ronda = brain._pending["entrada"]
    brain._handle_cam_event(
        "casa/evt/cam/entrada/snapshot",
        {"chat": "c1", "image_b64": FOTO_B64, "filename": "x.jpg"},
    )

    brain._ronda_vencida(ronda)

    assert bus.replies[-1]["text"] == "Entrada: No se ve a nadie.\nPatio: no me contestó."
    assert brain._pending == {}


def test_foto_que_llega_sin_pedido_no_se_manda(armar):
    brain, bus = armar(RouterFalso(decision("otro", 0.9)))

    brain._handle_cam_event(
        "casa/evt/cam/entrada/snapshot",
        {"chat": "c1", "image_b64": FOTO_B64, "filename": "x.jpg"},
    )

    assert bus.replies == []


def test_evento_ptz_confirma(armar):
    brain, bus = armar(RouterFalso(decision("otro", 0.9)))

    brain._handle_cam_event("casa/evt/cam/entrada/ptz", {"chat": "c1", "ok": True})

    assert bus.replies[-1]["text"] == "Listo, la moví."


def test_evento_ptz_con_foto_lleva_el_nombre_de_pie(armar, settings):
    brain, bus = armar(RouterFalso(decision("otro", 0.9)))
    foto = b"\xff\xd8-falso"

    brain._handle_cam_event(
        "casa/evt/cam/entrada/ptz",
        {
            "chat": "c1",
            "result": "ok",
            "direction": "right",
            "image_b64": base64.b64encode(foto).decode(),
            "filename": "entrada-ptz.jpg",
        },
    )

    guardada = settings.media_dir / "entrada-ptz.jpg"
    assert bus.replies == [{"chat": "c1", "text": "Entrada", "image_path": str(guardada)}]


def test_gasto_no_se_contesta_por_whatsapp_se_manda_a_telegram(armar, monkeypatch):
    llm = AssistantFalso(Reply(text="no debería llamarme", actions=[]))
    brain, bus = armar(RouterFalso(decision("gasto", 0.95)), llm)
    monkeypatch.setattr(main_module.costos, "resumen_texto", lambda: "Hoy: nada gastado.")
    enviados = []
    monkeypatch.setattr(
        main_module.T,
        "notificar",
        lambda texto, token, chat_id: enviados.append((texto, token, chat_id)) or True,
    )

    brain._handle_inbound({"chat": "c1", "text": "cuánto gastamos?", "kind": "text"})

    assert llm.textos == []
    # Por WhatsApp no se da el dato, solo se avisa que llega por otro lado.
    assert bus.replies == [
        {"chat": "c1", "text": main_module.BIENVENIDA, "image_path": None},
        {
            "chat": "c1",
            "text": "Ese dato te lo paso por Telegram, ahí lo tenés.",
            "image_path": None,
        },
    ]
    # El dato real sí sale, pero por Telegram.
    assert enviados == [("Hoy: nada gastado.", "", "")]


def test_saluda_solo_la_primera_vez_por_chat(armar):
    brain, bus = armar(RouterFalso(decision("otro", 0.3)))

    brain._handle_inbound({"chat": "c1", "text": "hola", "kind": "text"})
    brain._handle_inbound({"chat": "c1", "text": "hola de nuevo", "kind": "text"})
    brain._handle_inbound({"chat": "c2", "text": "hola", "kind": "text"})

    saludos = [r for r in bus.replies if r["text"] == main_module.BIENVENIDA]
    assert len(saludos) == 2  # una vez por chat, c1 y c2, no de nuevo para c1
    assert brain._chats_conocidos == {"c1", "c2"}


def test_la_bienvenida_persiste_entre_reinicios(armar, settings, inventario, monkeypatch):
    brain, _ = armar(RouterFalso(decision("otro", 0.3)))
    brain._handle_inbound({"chat": "c1", "text": "hola", "kind": "text"})

    monkeypatch.setattr(main_module, "Router", RouterFalso(decision("otro", 0.3)))
    monkeypatch.setattr(main_module.B, "Bus", BusFalso)
    brain2 = Brain(settings, inventario)
    brain2._handle_inbound({"chat": "c1", "text": "hola otra vez", "kind": "text"})

    saludos = [r for r in brain2._bus.replies if r["text"] == main_module.BIENVENIDA]
    assert saludos == []  # ya lo conocía de antes de reiniciar
