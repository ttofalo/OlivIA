"""PTZ y presets por ONVIF.

En estas XiongMai el PTZ no responde por DVRIP; sí por ONVIF, en el puerto 8899.
El snapshot sigue yendo por RTSP con ffmpeg (ver snapshot.py); acá va solo el
movimiento.

Los puntos con nombre (porton, centro, camino) se guardan como presets EN la
cámara. "Mové al portón" es un GotoPreset: la cámara va sola a esa posición y
respeta sus propios límites, así que es lo más robusto y no puede trabar el
motor. Los movimientos relativos ("un poco a la derecha") llevan un tope duro de
duración, para nunca empujar contra el final del recorrido, que es lo que traba
estos motores.

Referencia de comandos PTZ:
  https://github.com/dbuezas/icsee-ptz
"""

from __future__ import annotations

import time
from typing import Literal

import structlog

try:
    from onvif import ONVIFCamera
except ImportError:  # onvif-zeep no está en el modo fake ni en algunos tests
    ONVIFCamera = None

from . import resolver
from .config import Camera

log = structlog.get_logger()

Direction = Literal["left", "right", "up", "down", "zoom_in", "zoom_out"]

# Tope duro de duración de un movimiento relativo. Un movimiento nunca dura más
# que esto, por más que el pedido diga otra cosa: evita clavar el motor contra
# el límite mecánico.
MAX_MOVE_SECONDS = 1.0

# Vector unitario por dirección: (pan, tilt, zoom).
_VECTORS: dict[Direction, tuple[float, float, float]] = {
    "left": (-1.0, 0.0, 0.0),
    "right": (1.0, 0.0, 0.0),
    "up": (0.0, 1.0, 0.0),
    "down": (0.0, -1.0, 0.0),
    "zoom_in": (0.0, 0.0, 1.0),
    "zoom_out": (0.0, 0.0, -1.0),
}


def _connect(cam: Camera):
    """Devuelve (servicio_ptz, profile_token) resolviendo la IP por MAC.

    Si el primer intento falla, quizás la cámara cambió de IP: se re-resuelve por
    MAC y se reintenta una vez.
    """
    if ONVIFCamera is None:
        raise RuntimeError("onvif-zeep no está instalado (pip install onvif-zeep)")

    port = cam.onvif_port or 8899

    def build(ip: str):
        client = ONVIFCamera(ip, port, cam.usuario, cam.password)
        token = client.create_media_service().GetProfiles()[0].token
        return client.create_ptz_service(), token

    ip = resolver.current_ip(cam)
    try:
        return build(ip)
    except Exception:
        resolver.invalidate(cam)
        ip2 = resolver.current_ip(cam, force=True)
        if ip2 == ip:
            raise
        log.info("reintento onvif con ip nueva", cam=cam.id, vieja=ip, nueva=ip2)
        return build(ip2)


def move(cam: Camera, direction: Direction, duration: float = 0.4, speed: float = 0.5) -> None:
    """Mueve la cámara un tramo corto y la frena.

    `duration` se recorta a MAX_MOVE_SECONDS y `speed` a [0.1, 1.0]. El stop va en
    un finally: si algo falla en el medio, la cámara igual frena.
    """
    if not cam.ptz:
        raise RuntimeError(f"{cam.id} no tiene PTZ")

    duration = min(max(duration, 0.0), MAX_MOVE_SECONDS)
    speed = min(max(speed, 0.1), 1.0)
    vx, vy, vz = _VECTORS[direction]

    ptz, token = _connect(cam)
    velocity = {"PanTilt": {"x": vx * speed, "y": vy * speed}, "Zoom": {"x": vz * speed}}
    try:
        ptz.ContinuousMove({"ProfileToken": token, "Velocity": velocity})
        _sleep(duration)
    finally:
        ptz.Stop({"ProfileToken": token})
    log.info("ptz", cam=cam.id, direction=direction, duration=duration, speed=speed)


def goto_preset(cam: Camera, preset: int) -> None:
    """Va a un punto guardado en la cámara. Ella respeta sus límites sola."""
    ptz, token = _connect(cam)
    ptz.GotoPreset({"ProfileToken": token, "PresetToken": str(preset)})
    log.info("preset", cam=cam.id, preset=preset)


def save_preset(cam: Camera, preset: int) -> None:
    """Guarda la posición actual en el slot de preset indicado."""
    ptz, token = _connect(cam)
    ptz.SetPreset({"ProfileToken": token, "PresetToken": str(preset)})
    log.info("preset guardado", cam=cam.id, preset=preset)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)
