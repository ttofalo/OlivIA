from pathlib import Path

import pytest

from agent.config import Camera, load_cameras


def test_camara_desde_yaml_usa_defaults_password_y_presets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAMARA_PASSWORD", "clave")

    camara = Camera.from_yaml(
        "entrada",
        {
            "nombre": "Entrada",
            "ip": "192.0.2.20",
            "password_env": "CAMARA_PASSWORD",
            "presets": {"porton": 2},
        },
    )

    assert camara.dvrip_port == 34567
    assert camara.rtsp_port == 554
    assert camara.onvif_port is None
    assert camara.password == "clave"
    assert camara.presets == {"porton": 2}


def test_url_rtsp_xiongmai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAMARA_PASSWORD", "X")
    camara = Camera.from_yaml(
        "entrada",
        {"ip": "192.0.2.20", "password_env": "CAMARA_PASSWORD"},
    )

    assert camara.rtsp_url() == "rtsp://192.0.2.20:554/user=admin&password=X&channel=1&stream=0.sdp"


def test_carga_camaras_desde_yaml(archivo_camaras: Path) -> None:
    camaras = load_cameras(archivo_camaras)

    assert set(camaras) == {"entrada", "patio"}
    assert camaras["entrada"].nombre == "Entrada"
    assert camaras["patio"].ptz
