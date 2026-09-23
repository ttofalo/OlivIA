"""Snapshots por RTSP con ffmpeg.

Hay una segunda vía más barata: pedir el frame por el mismo socket DVRIP que ya
usamos para PTZ, sin levantar ffmpeg. La implementa TheJenos/xmeye-control, y el
parser de paquetes de video más legible está en kinsi55/node_dvripclient. Ver
docs/PRIOR_ART.md.

El plan de la fase 1 es medir las dos en tus cámaras y quedarse con la que ande.
Esta anda en cualquier cámara con RTSP, así que arranca siendo el piso.
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import structlog

from . import resolver
from .config import Camera

log = structlog.get_logger()


def grab(cam: Camera, out_dir: Path, timeout: int = 15) -> Path:
    """Saca un frame del stream y lo guarda como JPEG.

    Las XiongMai tardan entre 1 y 3 segundos en entregar el primer frame. Con
    -frames:v 1 ffmpeg corta en cuanto lo tiene. El -rtsp_transport tcp evita
    los frames partidos que da UDP cuando el WiFi anda flojo, que es el caso de
    la cámara de la cabaña.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{cam.id}-{int(time.time())}.jpg"

    # La IP puede haber cambiado desde el YAML; se resuelve por MAC.
    ip = resolver.current_ip(cam)

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        cam.rtsp_url(ip),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        "-y",
        str(path),
    ]

    started = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    elapsed = time.monotonic() - started

    if result.returncode != 0 or not path.exists():
        raise RuntimeError(f"ffmpeg falló en {cam.id}: {result.stderr.decode().strip()[:200]}")

    log.info("snapshot", cam=cam.id, ms=int(elapsed * 1000), kb=path.stat().st_size // 1024)
    return path


def grab_dvrip(cam: Camera, out_dir: Path, timeout: int = 15) -> Path:
    """Snapshot por el socket DVRIP, sin ffmpeg.

    La cámara devuelve el JPEG ya armado. Es el camino barato para la Pi Zero:
    no decodifica video, solo reenvía. Ver docs/PRIOR_ART.md.
    """
    try:
        from dvrip import DVRIPCam
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("python-dvr no está instalado") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{cam.id}-{int(time.time())}.jpg"

    def intento(ip: str):
        # Sondeo TCP con timeout corto antes de crear el cliente: python-dvr
        # conecta sin timeout y con la cámara apagada colgaría ~2 minutos.
        try:
            socket.create_connection((ip, cam.dvrip_port), timeout=5).close()
        except OSError:
            return None
        client = DVRIPCam(ip, port=cam.dvrip_port, user=cam.usuario, password=cam.password)
        try:
            if not client.login():
                return None
            return client.snapshot()
        except Exception:  # incluye SomethingIsWrongWithCamera, que no es OSError
            return None
        finally:
            try:
                client.close()
            except Exception:
                pass

    started = time.monotonic()
    ip = resolver.current_ip(cam)
    data = intento(ip)

    # Si falló, quizás cambió de IP: se re-resuelve por MAC y se reintenta.
    if not data:
        resolver.invalidate(cam)
        ip2 = resolver.current_ip(cam, force=True)
        if ip2 != ip:
            log.info("reintento snapshot con ip nueva", cam=cam.id, vieja=ip, nueva=ip2)
            data = intento(ip2)

    if not data:
        raise RuntimeError(
            f"{cam.id}: no pude conectar con la cámara (¿apagada o fuera de la red?)"
        )
    if data[:2] != b"\xff\xd8":
        raise RuntimeError(f"{cam.id} no devolvió un JPEG por DVRIP")

    path.write_bytes(data)
    elapsed = time.monotonic() - started
    log.info("snapshot dvrip", cam=cam.id, ms=int(elapsed * 1000), kb=path.stat().st_size // 1024)
    return path
