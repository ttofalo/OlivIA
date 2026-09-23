"""Chequeos baratos sobre la imagen, sin IA.

Dos preguntas que el agente necesita responder en milisegundos después de un
giro de cámara:

- ¿Se movió? Compara el cuadro de antes y el de después. Si son iguales, la
  cámara está en el tope mecánico y no dio más.
- ¿Se ve algo? Una pared o el tanque de agua dan una imagen casi lisa, sin
  bordes. Una escena real (cerco, pasto, árboles) tiene mucho detalle. El umbral
  salió de medir el barrido de las tres cámaras el 2026-09-23: las paredes dan
  entre 9 y 17, cualquier escena da 22 o más.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageChops, ImageFilter, ImageStat

# Diferencia media de píxel (0-255) por debajo de la cual el cuadro no cambió.
CHANGE_THRESHOLD = 3.0
# Energía de bordes por debajo de la cual la cámara mira una pared o nada.
VISIBLE_EDGE_THRESHOLD = 20.0

OPPOSITE = {
    "left": "right",
    "right": "left",
    "up": "down",
    "down": "up",
    "zoom_in": "zoom_out",
    "zoom_out": "zoom_in",
}


def _gray(data: bytes, size: tuple[int, int]) -> Image.Image:
    return Image.open(BytesIO(data)).convert("L").resize(size)


def changed(before: bytes, after: bytes) -> bool:
    """True si el cuadro cambió de forma apreciable entre las dos fotos."""
    hist = ImageChops.difference(_gray(before, (80, 60)), _gray(after, (80, 60))).histogram()
    mean = sum(i * hist[i] for i in range(256)) / max(sum(hist), 1)
    return mean > CHANGE_THRESHOLD


def is_visible(data: bytes) -> bool:
    """True si la imagen tiene detalle de escena; False si es pared o nada."""
    edges = _gray(data, (320, 180)).filter(ImageFilter.FIND_EDGES)
    return ImageStat.Stat(edges).mean[0] >= VISIBLE_EDGE_THRESHOLD
