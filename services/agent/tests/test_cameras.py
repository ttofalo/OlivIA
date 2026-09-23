from typing import Any, ClassVar

import pytest

from agent import cameras
from agent.config import Camera


class PTZFalso:
    def __init__(self) -> None:
        self.llamadas: list[tuple[str, dict[str, Any]]] = []

    def ContinuousMove(self, params: dict[str, Any]) -> None:  # noqa: N802 (nombre ONVIF)
        self.llamadas.append(("ContinuousMove", params))

    def Stop(self, params: dict[str, Any]) -> None:  # noqa: N802
        self.llamadas.append(("Stop", params))

    def GotoPreset(self, params: dict[str, Any]) -> None:  # noqa: N802
        self.llamadas.append(("GotoPreset", params))

    def SetPreset(self, params: dict[str, Any]) -> None:  # noqa: N802
        self.llamadas.append(("SetPreset", params))


class ONVIFFalso:
    """Doble del cliente ONVIF. El perfil siempre tiene token '000'."""

    instancias: ClassVar[list["ONVIFFalso"]] = []

    def __init__(self, ip: str, port: int, user: str, password: str) -> None:
        self.ip = ip
        self.port = port
        self.user = user
        self.password = password
        self.ptz = PTZFalso()
        self.instancias.append(self)

    def create_media_service(self):
        perfil = type("Perfil", (), {"token": "000"})()
        return type("Media", (), {"GetProfiles": lambda self: [perfil]})()

    def create_ptz_service(self):
        return self.ptz


@pytest.fixture(autouse=True)
def onvif_falso(monkeypatch: pytest.MonkeyPatch) -> None:
    ONVIFFalso.instancias.clear()
    monkeypatch.setattr(cameras, "ONVIFCamera", ONVIFFalso)


def test_move_arranca_y_frena(monkeypatch: pytest.MonkeyPatch, camara: Camera) -> None:
    monkeypatch.setattr(cameras, "_sleep", lambda _: None)

    cameras.move(camara, "left", duration=0.2, speed=0.5)

    cliente = ONVIFFalso.instancias[0]
    assert cliente.ip == camara.ip
    assert cliente.port == 8899  # onvif_port None -> 8899 por defecto
    nombres = [c[0] for c in cliente.ptz.llamadas]
    assert nombres == ["ContinuousMove", "Stop"]
    velocidad = cliente.ptz.llamadas[0][1]["Velocity"]["PanTilt"]
    assert velocidad["x"] < 0 and velocidad["y"] == 0  # left = pan negativo


def test_move_recorta_la_duracion_al_tope(monkeypatch: pytest.MonkeyPatch, camara: Camera) -> None:
    dormido: list[float] = []
    monkeypatch.setattr(cameras, "_sleep", lambda s: dormido.append(s))

    cameras.move(camara, "right", duration=99.0, speed=5.0)

    assert dormido == [cameras.MAX_MOVE_SECONDS]  # nunca más que el tope


def test_move_frena_aunque_falle_la_espera(
    monkeypatch: pytest.MonkeyPatch, camara: Camera
) -> None:
    def falla(_: float) -> None:
        raise ValueError("falló la espera")

    monkeypatch.setattr(cameras, "_sleep", falla)

    with pytest.raises(ValueError, match="falló la espera"):
        cameras.move(camara, "right")

    cliente = ONVIFFalso.instancias[0]
    assert cliente.ptz.llamadas[-1][0] == "Stop"  # frenó igual


def test_move_sin_ptz_falla(camara: Camera) -> None:
    object.__setattr__(camara, "ptz", False)

    with pytest.raises(RuntimeError, match="no tiene PTZ"):
        cameras.move(camara, "up")

    assert not ONVIFFalso.instancias


@pytest.mark.parametrize(
    ("accion", "comando"),
    [(cameras.goto_preset, "GotoPreset"), (cameras.save_preset, "SetPreset")],
)
def test_preset_usa_el_token_como_string(accion: Any, comando: str, camara: Camera) -> None:
    accion(camara, 4)

    cliente = ONVIFFalso.instancias[0]
    assert cliente.ptz.llamadas == [(comando, {"ProfileToken": "000", "PresetToken": "4"})]
