"""Snapshots por RTSP con ffmpeg."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import structlog

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

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-i", cam.rtsp_url(),
        "-frames:v", "1",
        "-q:v", "3",
        "-y", str(path),
    ]

    started = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    elapsed = time.monotonic() - started

    if result.returncode != 0 or not path.exists():
        raise RuntimeError(f"ffmpeg falló en {cam.id}: {result.stderr.decode().strip()[:200]}")

    log.info("snapshot", cam=cam.id, ms=int(elapsed * 1000), kb=path.stat().st_size // 1024)
    return path
