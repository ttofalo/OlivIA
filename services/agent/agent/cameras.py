"""PTZ y presets por DVRIP.

Las cámaras son XiongMai (se venden como iCSee, XMEye, Sofia). Hablan un
protocolo propietario en el puerto 34567 que implementa python-dvr de OpenIPC.
ONVIF es la alternativa estándar, pero muchas lo traen apagado de fábrica y hay
que habilitarlo desde la app.

Referencias de los comandos PTZ:
  https://github.com/OpenIPC/python-dvr
  https://github.com/dbuezas/icsee-ptz
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Literal

import structlog
from dvrip import DVRIPCam

from .config import Camera

log = structlog.get_logger()

Direction = Literal["left", "right", "up", "down", "zoom_in", "zoom_out"]

# Nombres que espera DVRIP para cada movimiento.
_PTZ_COMMANDS: dict[Direction, str] = {
    "left": "DirectionLeft",
    "right": "DirectionRight",
    "up": "DirectionUp",
    "down": "DirectionDown",
    "zoom_in": "ZoomTile",
    "zoom_out": "ZoomWide",
}


@contextmanager
def connect(cam: Camera) -> Iterator[DVRIPCam]:
    client = DVRIPCam(cam.ip, port=cam.dvrip_port, user=cam.usuario, password=cam.password)
    if not client.login():
        raise RuntimeError(f"No pude loguearme a {cam.id} ({cam.ip}:{cam.dvrip_port})")
    try:
        yield client
    finally:
        client.close()


def move(cam: Camera, direction: Direction, duration: float = 0.5, speed: int = 4) -> None:
    """Mueve la cámara y la frena.

    DVRIP no tiene movimiento por tiempo: se manda start, se espera y se manda
    stop. Si el proceso muere entre los dos, la cámara sigue girando, así que el
    stop va en un finally.
    """
    if not cam.ptz:
        raise RuntimeError(f"{cam.id} no tiene PTZ")

    command = _PTZ_COMMANDS[direction]
    with connect(cam) as client:
        try:
            client.ptz(command, step=speed, preset=-1)
            _sleep(duration)
        finally:
            client.ptz(command, step=0, preset=-1)
    log.info("ptz", cam=cam.id, direction=direction, duration=duration)


def goto_preset(cam: Camera, preset: int) -> None:
    with connect(cam) as client:
        client.ptz("GotoPreset", preset=preset)
    log.info("preset", cam=cam.id, preset=preset)


def save_preset(cam: Camera, preset: int) -> None:
    """Guarda la posición actual. El nombre lo maneja el brain en la base."""
    with connect(cam) as client:
        client.ptz("SetPreset", preset=preset)
    log.info("preset guardado", cam=cam.id, preset=preset)


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
