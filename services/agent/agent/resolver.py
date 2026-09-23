"""Encontrar la IP de una cámara por su MAC.

Las IPs las reparte el router por DHCP. Aunque estén reservadas, un reset del
router o un cambio de modo puede repartirlas de nuevo. Si el agente confía en la
IP del YAML y la cámara aparece en otra, se rompe sin motivo aparente.

La MAC no cambia. Este módulo traduce MAC a IP mirando la tabla ARP del sistema,
y si no está, refresca la tabla haciendo ping. Sin dependencias: la misma
familia de trucos que usa scripts/discover.py.

Si la cámara no declara `mac` en devices.yaml, se usa la IP tal cual y este
módulo no hace nada.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import structlog

from .config import Camera

log = structlog.get_logger()

# MAC normalizada -> (ip, timestamp). Evita rastrear ARP en cada comando.
_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 300.0  # segundos


def _norm(mac: str) -> str:
    """aa-bb-CC:d:... -> aa:bb:cc:0d:..., siempre en minúsculas y con dos dígitos."""
    partes = re.split(r"[:-]", mac.strip())
    return ":".join(p.lower().zfill(2) for p in partes)


def current_ip(cam: Camera, force: bool = False) -> str:
    """IP a la que hablarle a la cámara ahora.

    Sin MAC declarada, devuelve la IP del YAML. Con MAC, la resuelve por ARP y
    cae a la IP del YAML si no la encuentra. `force` saltea el cache.
    """
    if not cam.mac:
        return cam.ip

    mac = _norm(cam.mac)
    if not force:
        # Camino optimista: la última IP conocida sirve aunque el cache esté
        # vencido; si falla, quien llama reintenta con force=True. Sin cache,
        # solo se mira la tabla ARP (milisegundos), nunca ping ni barrido.
        hit = _cache.get(mac)
        if hit:
            return hit[0]
        ip_arp = _tabla_arp().get(mac)
        if ip_arp:
            _cache[mac] = (ip_arp, time.monotonic())
            return ip_arp
        return cam.ip

    ip = _resolver_por_mac(mac, pista=cam.ip)
    if ip:
        if ip != cam.ip:
            log.info("ip cambiada", cam=cam.id, yaml=cam.ip, actual=ip)
        _cache[mac] = (ip, time.monotonic())
        return ip

    log.warning("no encontré la mac, uso la ip del yaml", cam=cam.id, mac=mac, ip=cam.ip)
    return cam.ip


def invalidate(cam: Camera) -> None:
    """Borra el cache de esta cámara. Se llama cuando una conexión falló."""
    if cam.mac:
        _cache.pop(_norm(cam.mac), None)


def _tabla_arp() -> dict[str, str]:
    """MAC normalizada -> IP, leyendo lo que el sistema ya sabe.

    Prueba /proc/net/arp (Linux, la Pi) y `arp -an` (sirve en Linux y en macOS).
    """
    salida: dict[str, str] = {}

    proc = Path("/proc/net/arp")
    if proc.exists():
        for linea in proc.read_text().splitlines()[1:]:
            campos = linea.split()
            if len(campos) >= 4 and campos[3] != "00:00:00:00:00:00":
                salida[_norm(campos[3])] = campos[0]
        if salida:
            return salida

    try:
        texto = subprocess.run(
            ["arp", "-an"], capture_output=True, text=True, timeout=5
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return salida

    for ip, mac in re.findall(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)", texto):
        if mac.lower() != "ff:ff:ff:ff:ff:ff":
            salida[_norm(mac)] = ip
    return salida


def _resolver_por_mac(mac: str, pista: str | None) -> str | None:
    """Busca la MAC en ARP. Si no está, refresca la tabla y reintenta."""
    tabla = _tabla_arp()
    if mac in tabla:
        return tabla[mac]

    # La MAC no está en la tabla, quizás porque nadie le habló todavía. Un ping
    # a la última IP conocida suele bastar para que el equipo conteste y quede
    # en ARP. Si eso no la trae, se barre la subred de esa IP.
    if pista:
        _ping(pista)
        tabla = _tabla_arp()
        if mac in tabla:
            return tabla[mac]
        _barrer(pista)
        tabla = _tabla_arp()
        if mac in tabla:
            return tabla[mac]

    return None


def _ping(ip: str) -> None:
    try:
        subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            capture_output=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def _barrer(ip_pista: str) -> None:
    """Hace ping a toda la /24 de la IP pista para poblar la tabla ARP."""
    try:
        red = ipaddress.ip_network(f"{ip_pista}/24", strict=False)
    except ValueError:
        return
    with ThreadPoolExecutor(max_workers=64) as pool:
        pool.map(_ping, (str(h) for h in red.hosts()))
