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
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout: float
    transcribe_backend: str
    transcribe_model: str
    transcribe_api_base_url: str
    transcribe_api_key: str
    mqtt_host: str
    mqtt_port: int
    mqtt_tls: bool
    mqtt_user: str
    mqtt_pass: str
    mqtt_ca: str
    devices_path: Path
    media_dir: Path
    # Nivel de esfuerzo del LLM de nivel 2. Los DeepSeek V4 razonan por defecto;
    # con "low" contestan directo y bajan la latencia. Va por extra_body, así que
    # un proveedor que no lo entienda simplemente lo ignora.
    llm_effort: str = "low"
    llm_max_tokens: int = 512
    # Modelo con visión para describir las fotos. v4-pro es solo texto, así que
    # va flash, que acepta imágenes.
    llm_vision_model: str = "deepseek-flash"
    # Dónde se anota cada llamada a Jev y a DeepSeek con sus tokens y USD.
    costs_path: Path | None = Path("/media/costos.jsonl")
    # Bot de Telegram para avisos operativos y el reporte diario de gasto.
    # Sin estas dos variables, no se manda nada.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        def need(name: str) -> str:
            v = os.environ.get(name)
            if not v:
                raise RuntimeError(f"Falta la variable de entorno {name}")
            return v

        return cls(
            typesafe_api_key=need("TYPESAFE_API_KEY"),
            jev_model=os.environ.get("JEV_MODEL", "jev-latest"),
            jev_threshold=float(os.environ.get("JEV_CONFIDENCE_THRESHOLD", "0.80")),
            llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            llm_model=os.environ.get("LLM_MODEL", "deepseek-flash"),
            llm_timeout=float(os.environ.get("LLM_TIMEOUT", "20")),
            transcribe_backend=os.environ.get("TRANSCRIBE_BACKEND", "local"),
            transcribe_model=os.environ.get("TRANSCRIBE_MODEL", "base"),
            transcribe_api_base_url=os.environ.get("TRANSCRIBE_API_BASE_URL", ""),
            transcribe_api_key=os.environ.get("TRANSCRIBE_API_KEY", ""),
            mqtt_host=need("MQTT_HOST"),
            mqtt_port=int(os.environ.get("MQTT_PORT", "8883")),
            mqtt_tls=os.environ.get("MQTT_TLS", "true") != "false",
            mqtt_user=need("MQTT_USER_BRAIN"),
            mqtt_pass=need("MQTT_PASS_BRAIN"),
            # Ruta al ca.crt del broker. El broker usa una CA propia, así que sin
            # esto la verificación TLS falla contra el almacén del sistema.
            mqtt_ca=os.environ.get("MQTT_CA_CERT", ""),
            devices_path=Path(os.environ.get("DEVICES_PATH", "config/devices.yaml")),
            media_dir=Path(os.environ.get("MEDIA_DIR", "/media")),
            llm_effort=os.environ.get("LLM_EFFORT", "low"),
            llm_max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "512")),
            llm_vision_model=os.environ.get("LLM_VISION_MODEL", "deepseek-flash"),
            costs_path=Path(os.environ.get("COSTS_PATH", "/media/costos.jsonl")),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        )


@dataclass(frozen=True)
class Inventory:
    """El inventario de la casa. Alimenta las opciones que ve Jev."""

    camaras: dict[str, dict[str, Any]]
    boyeros: dict[str, dict[str, Any]]
    nvr: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, path: Path) -> Inventory:
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

    def nombre(self, cam_id: str) -> str:
        """Nombre para la gente (Cabaña). El id (cabania) es solo interno."""
        datos = self.camaras.get(cam_id) or {}
        return str(datos.get("nombre") or cam_id)
