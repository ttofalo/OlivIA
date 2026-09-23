from pathlib import Path

import pytest

from brain.config import Inventory, Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        typesafe_api_key="clave-de-prueba",
        jev_model="jev-prueba",
        jev_threshold=0.8,
        llm_base_url="https://llm.invalid",
        llm_api_key="",
        llm_model="llm-prueba",
        llm_timeout=1.0,
        transcribe_backend="local",
        transcribe_model="base",
        transcribe_api_base_url="",
        transcribe_api_key="",
        mqtt_host="localhost",
        mqtt_port=1883,
        mqtt_tls=False,
        mqtt_user="brain",
        mqtt_pass="secreto",
        mqtt_ca="",
        devices_path=tmp_path / "devices.yaml",
        media_dir=tmp_path / "media",
        costs_path=tmp_path / "costos.jsonl",
    )


@pytest.fixture
def inventario() -> Inventory:
    return Inventory(
        camaras={
            "entrada": {
                "nombre": "Entrada",
                "descripcion": "La cámara de la entrada",
                "ptz": True,
            },
            "patio": {"nombre": "Patio", "ptz": False},
        },
        boyeros={"norte": {"nombre": "Boyero norte"}},
        nvr={},
    )
