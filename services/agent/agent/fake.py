"""Cámara falsa para desarrollar sin hardware."""

from __future__ import annotations

import struct
import time
import zlib
from pathlib import Path

from .config import Camera

WIDTH = 320
HEIGHT = 240


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def grab_fake(cam: Camera, out_dir: Path) -> Path:
    """Genera un PNG sólido cuyo color depende del id de la cámara."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{cam.id}-{int(time.time())}.png"
    seed = zlib.crc32(cam.id.encode("utf-8"))
    color = bytes(((seed >> 16) & 0xFF, (seed >> 8) & 0xFF, seed & 0xFF))
    rows = b"".join(b"\x00" + color * WIDTH for _ in range(HEIGHT))
    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
    png += _chunk(b"IDAT", zlib.compress(rows)) + _chunk(b"IEND", b"")
    path.write_bytes(png)
    return path
