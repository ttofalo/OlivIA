import sys
from pathlib import Path
from types import ModuleType

import pytest

# python-dvr no está disponible en todos los entornos de test.
dvrip_falso = ModuleType("dvrip")
dvrip_falso.DVRIPCam = object  # type: ignore[attr-defined]
sys.modules["dvrip"] = dvrip_falso

from agent.config import Camera


@pytest.fixture
def camara() -> Camera:
    return Camera(
        id="entrada",
        nombre="Entrada",
        ip="192.0.2.20",
        usuario="admin",
        password="secreto",
        canal=1,
        ptz=True,
        dvrip_port=34567,
        rtsp_port=554,
        onvif_port=None,
        presets={"porton": 2},
    )


@pytest.fixture
def archivo_camaras(tmp_path: Path) -> Path:
    archivo = tmp_path / "devices.yaml"
    archivo.write_text(
        """
camaras:
  entrada:
    nombre: Entrada
    ip: 192.0.2.20
  patio:
    ip: 192.0.2.21
    ptz: true
""".strip(),
        encoding="utf-8",
    )
    return archivo
