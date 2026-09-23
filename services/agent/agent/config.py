"""Configuración del agente local."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Settings:
    mqtt_host: str
    mqtt_port: int
    mqtt_tls: bool
    mqtt_user: str
    mqtt_pass: str
    mqtt_ca: str
    devices_path: Path
    snapshot_dir: Path
    heartbeat_seconds: int

    @classmethod
    def from_env(cls) -> Settings:
        def need(name: str) -> str:
            v = os.environ.get(name)
            if not v:
                raise RuntimeError(f"Falta la variable de entorno {name}")
            return v

        return cls(
            # El agente apunta al host público del VPS, no al nombre del contenedor.
            mqtt_host=need("VPS_MQTT_HOST"),
            mqtt_port=int(os.environ.get("MQTT_PORT", "8883")),
            mqtt_tls=os.environ.get("MQTT_TLS", "true") != "false",
            mqtt_user=need("MQTT_USER_AGENT"),
            mqtt_pass=need("MQTT_PASS_AGENT"),
            # ca.crt del broker: se copia del VPS a la Pi. Sin esto, la
            # verificación TLS contra la CA propia del broker falla.
            mqtt_ca=os.environ.get("MQTT_CA_CERT", ""),
            devices_path=Path(os.environ.get("DEVICES_PATH", "../../config/devices.yaml")),
            snapshot_dir=Path(os.environ.get("SNAPSHOT_DIR", "/tmp/olivia")),
            heartbeat_seconds=int(os.environ.get("HEARTBEAT_SECONDS", "30")),
        )


@dataclass(frozen=True)
class Camera:
    id: str
    nombre: str
    ip: str
    usuario: str
    password: str
    canal: int
    ptz: bool
    dvrip_port: int
    rtsp_port: int
    onvif_port: int | None
    presets: dict[str, int]
    # La IP la reparte el router y puede cambiar. La MAC no. Si está, el agente
    # resuelve la IP actual por ARP (ver agent/resolver.py) y `ip` queda como
    # respaldo. Sin MAC, se usa `ip` tal cual.
    mac: str | None = None

    @classmethod
    def from_yaml(cls, cam_id: str, d: dict[str, Any]) -> Camera:
        puertos = d.get("puertos", {})
        pass_env = d.get("password_env", "")
        return cls(
            id=cam_id,
            nombre=d.get("nombre", cam_id),
            ip=d["ip"],
            usuario=d.get("usuario", "admin"),
            # Las contraseñas de las cámaras nunca van al YAML, solo el nombre
            # de la variable de entorno que las tiene.
            password=os.environ.get(pass_env, "") if pass_env else "",
            canal=int(d.get("canal", 1)),
            ptz=bool(d.get("ptz", False)),
            dvrip_port=int(puertos.get("dvrip", 34567)),
            rtsp_port=int(puertos.get("rtsp", 554)),
            onvif_port=int(puertos["onvif"]) if "onvif" in puertos else None,
            presets=d.get("presets", {}),
            mac=d.get("mac"),
        )

    def rtsp_url(self, ip: str | None = None) -> str:
        """URL RTSP del formato que usan las XiongMai.

        stream=0 es el principal, stream=1 el secundario. Para un snapshot el
        secundario alcanza y llega más rápido, pero da menos resolución.

        `ip` sobrescribe la del YAML: quien llama pasa la que resolvió por MAC.
        """
        return (
            f"rtsp://{ip or self.ip}:{self.rtsp_port}/user={self.usuario}"
            f"&password={self.password}&channel={self.canal}&stream=0.sdp"
        )


def load_cameras(path: Path) -> dict[str, Camera]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {cid: Camera.from_yaml(cid, d) for cid, d in (data.get("camaras") or {}).items()}
