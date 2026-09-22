"""Carga de configuración y del inventario de dispositivos."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Settings:
    typesafe_api_key: str
    jev_model: str
    jev_threshold: float
    anthropic_api_key: str
    anthropic_model: str
    mqtt_host: str
    mqtt_port: int
    mqtt_tls: bool
    mqtt_user: str
    mqtt_pass: str
    devices_path: Path
    media_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        def need(name: str) -> str:
            v = os.environ.get(name)
            if not v:
                raise RuntimeError(f"Falta la variable de entorno {name}")
            return v

        return cls(
            typesafe_api_key=need("TYPESAFE_API_KEY"),
            jev_model=os.environ.get("JEV_MODEL", "jev-latest"),
            jev_threshold=float(os.environ.get("JEV_CONFIDENCE_THRESHOLD", "0.80")),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5"),
            mqtt_host=need("MQTT_HOST"),
            mqtt_port=int(os.environ.get("MQTT_PORT", "8883")),
            mqtt_tls=os.environ.get("MQTT_TLS", "true") != "false",
            mqtt_user=need("MQTT_USER_BRAIN"),
            mqtt_pass=need("MQTT_PASS_BRAIN"),
            devices_path=Path(os.environ.get("DEVICES_PATH", "config/devices.yaml")),
            media_dir=Path(os.environ.get("MEDIA_DIR", "/media")),
        )


@dataclass(frozen=True)
class Inventory:
    """El inventario de la casa. Alimenta las opciones que ve Jev."""

    camaras: dict[str, dict[str, Any]]
    boyeros: dict[str, dict[str, Any]]
    nvr: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, path: Path) -> "Inventory":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            camaras=data.get("camaras", {}),
            boyeros=data.get("boyeros", {}),
            nvr=data.get("nvr", {}),
        )

    def camara_criteria(self) -> dict[str, str]:
        """Opciones de cámara para Jev, con 'ninguna' incluida."""
        out = {
            cid: (c.get("descripcion") or c.get("nombre") or cid).strip()
            for cid, c in self.camaras.items()
        }
        out["ninguna"] = "El mensaje no menciona ninguna cámara"
        return out

    def boyero_criteria(self) -> dict[str, str]:
        out = {
            bid: (b.get("descripcion") or b.get("nombre") or bid).strip()
            for bid, b in self.boyeros.items()
        }
        out["ninguno"] = "El mensaje no menciona ningún boyero"
        return out

    def camaras_con_ptz(self) -> list[str]:
        return [cid for cid, c in self.camaras.items() if c.get("ptz")]
