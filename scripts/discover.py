#!/usr/bin/env python3
"""Inventario de la red de casa. Fase 0 del proyecto.

Correr desde la Raspberry, dentro de la LAN. Solo stdlib, así que no hace falta
instalar nada:

    python3 scripts/discover.py
    python3 scripts/discover.py --red 192.168.1.0/24
    python3 scripts/discover.py --yaml > config/devices.yaml

Escanea el rango buscando los puertos que usan las XiongMai (iCSee, XMEye,
Sofia) y reporta qué encontró. No toca las cámaras: solo abre y cierra sockets.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

PUERTOS = {
    34567: "dvrip",   # protocolo XiongMai, lo que usa la app iCSee
    554: "rtsp",      # stream
    8899: "onvif",    # ONVIF, si está habilitado
    80: "http",       # interfaz web
    8000: "http-alt",
    37777: "dahua",   # por si alguna es Dahua de verdad
}

TIMEOUT = 0.6


@dataclass
class Host:
    ip: str
    abiertos: list[str] = field(default_factory=list)
    mac: str = ""

    @property
    def tipo(self) -> str:
        """Adivina qué es, con lo poco que da un escaneo de puertos."""
        if "dvrip" in self.abiertos and "rtsp" in self.abiertos:
            return "camara o nvr xiongmai"
        if "dvrip" in self.abiertos:
            return "xiongmai sin rtsp visible"
        if "rtsp" in self.abiertos:
            return "camara de otra marca"
        if "dahua" in self.abiertos:
            return "dahua"
        return "otro equipo"


def subredes_locales() -> list[ipaddress.IPv4Network]:
    """Lee las subredes de las interfaces con `ip addr`.

    Si hay más de una, el repetidor de la cabaña puede estar haciendo NAT y su
    cámara queda en otra red.
    """
    try:
        salida = subprocess.run(
            ["ip", "-o", "-4", "addr", "show", "scope", "global"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return []

    redes = []
    for cidr in re.findall(r"inet (\d+\.\d+\.\d+\.\d+/\d+)", salida):
        red = ipaddress.ip_network(cidr, strict=False)
        if isinstance(red, ipaddress.IPv4Network) and red.prefixlen >= 16:
            redes.append(red)
    return redes


def escanear_puerto(ip: str, puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(TIMEOUT)
        return s.connect_ex((ip, puerto)) == 0


def escanear_host(ip: str) -> Host | None:
    host = Host(ip=ip)
    for puerto, nombre in PUERTOS.items():
        if escanear_puerto(ip, puerto):
            host.abiertos.append(nombre)
    return host if host.abiertos else None


def tabla_arp() -> dict[str, str]:
    """IP -> MAC, de lo que el sistema ya tiene en la tabla ARP.

    Sirve para anotar la MAC de cada cámara en el YAML. La MAC no cambia aunque
    el router reparta otra IP, así que el agente la usa para reencontrarla.
    """
    salida: dict[str, str] = {}
    try:
        texto = subprocess.run(
            ["arp", "-an"], capture_output=True, text=True, timeout=5
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return salida
    for ip, mac in re.findall(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)", texto):
        if mac.lower() != "ff:ff:ff:ff:ff:ff":
            salida[ip] = ":".join(p.zfill(2) for p in mac.lower().split(":"))
    return salida


def escanear_red(red: ipaddress.IPv4Network, workers: int = 64) -> list[Host]:
    ips = [str(ip) for ip in red.hosts()]
    print(f"Escaneando {red} ({len(ips)} direcciones)...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        resultados = pool.map(escanear_host, ips)
    hosts = sorted((h for h in resultados if h), key=lambda h: ipaddress.ip_address(h.ip))
    # Escanear un puerto ya dejó la MAC en la tabla ARP del sistema.
    arp = tabla_arp()
    for h in hosts:
        h.mac = arp.get(h.ip, "")
    return hosts


def imprimir_reporte(hosts: list[Host], redes: list[ipaddress.IPv4Network]) -> None:
    print()
    if not hosts:
        print("No encontré nada. Verificá que la Pi esté en la misma red que las cámaras.")
        return

    print(f"{'IP':<16} {'puertos':<34} qué parece ser")
    print("-" * 78)
    for h in hosts:
        print(f"{h.ip:<16} {','.join(h.abiertos):<34} {h.tipo}")

    print()
    print("Siguiente paso: abrir iCSee y cruzar cada IP con la cámara que corresponde.")
    print("Después reservar esas IPs por DHCP en el router, o el agente se va a romper solo.")

    if len(redes) > 1:
        print()
        print("Ojo: hay más de una subred local.")
        for r in redes:
            print(f"  {r}")
        print("Si la cámara de la cabaña no apareció en el escaneo, el repetidor está")
        print("haciendo NAT. Pasarlo a modo AP o bridge para que quede en la misma red.")

    faltan = [h for h in hosts if "dvrip" in h.abiertos and "onvif" not in h.abiertos]
    if faltan:
        print()
        print("Estas tienen DVRIP pero no ONVIF:")
        for h in faltan:
            print(f"  {h.ip}")
        print("Sirven igual para PTZ y snapshot por DVRIP. Si querés ONVIF, se habilita")
        print("desde iCSee en la configuración de la cámara.")


def emitir_yaml(hosts: list[Host]) -> None:
    """Borrador de devices.yaml para completar a mano."""
    print("# Generado por scripts/discover.py. Completar nombres, descripciones y canales.")
    print("# Las descripciones son parte del prompt de Jev: escribirlas como las diría")
    print("# alguien de la familia.")
    print("camaras:")
    for i, h in enumerate(hosts, start=1):
        if "rtsp" not in h.abiertos and "dvrip" not in h.abiertos:
            continue
        cid = f"camara{i}"
        print(f"  {cid}:")
        print(f"    nombre: TODO")
        print(f"    descripcion: TODO qué se ve desde esta cámara")
        if h.mac:
            print(f"    mac: {h.mac}")
        print(f"    ip: {h.ip}")
        print(f"    marca: xiongmai")
        print(f"    puertos:")
        for nombre, puerto in ((n, p) for p, n in PUERTOS.items() if n in h.abiertos):
            if nombre in ("dvrip", "rtsp", "onvif"):
                print(f"      {nombre}: {puerto}")
        print(f"    usuario: admin")
        print(f"    password_env: CAM_{cid.upper()}_PASS")
        print(f"    ptz: false   # TODO probar con --ptz-test {h.ip}")
        print(f"    canal: 1")
        print(f"    via: directa")


def probar_ptz(ip: str) -> None:
    """Intenta un movimiento corto para ver si la cámara tiene motor.

    Algunas cámaras de esta familia aceptan comandos PTZ sin tener motor, así
    que la única verificación real es mirar la cámara mientras corre esto.
    """
    try:
        from dvrip import DVRIPCam
    except ImportError:
        print("Falta python-dvr. Instalar con:")
        print("  pip install git+https://github.com/OpenIPC/python-dvr")
        return

    usuario = input("usuario [admin]: ") or "admin"
    password = input("password: ")

    cam = DVRIPCam(ip, port=34567, user=usuario, password=password)
    if not cam.login():
        print("No pude loguearme. Revisar usuario y contraseña.")
        return

    print("Mirá la cámara. Va a girar a la derecha un segundo.")
    try:
        cam.ptz("DirectionRight", step=4, preset=-1)
        import time

        time.sleep(1)
    finally:
        cam.ptz("DirectionRight", step=0, preset=-1)
        cam.close()
    print("¿Se movió? Si sí, poner ptz: true en devices.yaml.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--red", help="rango a escanear, ej 192.168.1.0/24")
    ap.add_argument("--yaml", action="store_true", help="emite un borrador de devices.yaml")
    ap.add_argument("--json", action="store_true", help="salida cruda en JSON")
    ap.add_argument("--ptz-test", metavar="IP", help="prueba un movimiento PTZ en esa cámara")
    args = ap.parse_args()

    if args.ptz_test:
        probar_ptz(args.ptz_test)
        return

    redes = subredes_locales()
    if args.red:
        objetivo = [ipaddress.ip_network(args.red, strict=False)]
    elif redes:
        objetivo = redes
    else:
        print("No pude detectar la red. Pasala con --red 192.168.1.0/24", file=sys.stderr)
        raise SystemExit(1)

    hosts: list[Host] = []
    for red in objetivo:
        hosts.extend(escanear_red(red))

    if args.json:
        print(json.dumps([{"ip": h.ip, "puertos": h.abiertos, "tipo": h.tipo} for h in hosts],
                         indent=2, ensure_ascii=False))
    elif args.yaml:
        emitir_yaml(hosts)
    else:
        imprimir_reporte(hosts, redes)


if __name__ == "__main__":
    main()
