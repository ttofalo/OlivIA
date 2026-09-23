"""Tests de la resolución de IP por MAC."""

from __future__ import annotations

import pytest

from agent import resolver
from agent.config import Camera


def _cam(mac: str | None, ip: str = "192.168.1.50") -> Camera:
    return Camera(
        id="cabania",
        nombre="Cabaña",
        ip=ip,
        usuario="admin",
        password="x",
        canal=1,
        ptz=True,
        dvrip_port=34567,
        rtsp_port=554,
        onvif_port=None,
        presets={},
        mac=mac,
    )


@pytest.fixture(autouse=True)
def _limpiar_cache():
    resolver._cache.clear()
    yield
    resolver._cache.clear()


def test_sin_mac_devuelve_la_ip_del_yaml(monkeypatch):
    # No debe siquiera tocar ARP si la cámara no declara MAC.
    def boom():
        raise AssertionError("no debería mirar ARP")

    monkeypatch.setattr(resolver, "_tabla_arp", boom)
    assert resolver.current_ip(_cam(None, ip="10.0.0.9")) == "10.0.0.9"


def test_mac_en_arp_devuelve_la_ip_actual(monkeypatch):
    monkeypatch.setattr(resolver, "_tabla_arp", lambda: {"c0:8a:60:8c:7d:6c": "192.168.1.42"})
    ip = resolver.current_ip(_cam("C0-8A-60-8C-7D-6C", ip="192.168.1.50"))
    assert ip == "192.168.1.42"  # la real, no la del YAML


def test_normaliza_formato_de_mac(monkeypatch):
    # ARP la trae con un solo dígito y en minúscula; el YAML con dos y mayúscula.
    monkeypatch.setattr(resolver, "_tabla_arp", lambda: {"a4:ef:15:d4:7c:c3": "192.168.1.11"})
    ip = resolver.current_ip(_cam("A4-EF-15-D4-7C-C3"))
    assert ip == "192.168.1.11"


def test_cae_a_la_ip_del_yaml_si_no_encuentra_la_mac(monkeypatch):
    monkeypatch.setattr(resolver, "_tabla_arp", lambda: {})
    monkeypatch.setattr(resolver, "_ping", lambda ip: None)
    monkeypatch.setattr(resolver, "_barrer", lambda ip: None)
    ip = resolver.current_ip(_cam("00-11-22-33-44-55", ip="192.168.1.50"))
    assert ip == "192.168.1.50"


def test_usa_el_cache_y_lo_invalida(monkeypatch):
    llamadas = {"n": 0}

    def tabla():
        llamadas["n"] += 1
        return {"c0:8a:60:8c:7d:6c": "192.168.1.42"}

    monkeypatch.setattr(resolver, "_tabla_arp", tabla)
    cam = _cam("C0-8A-60-8C-7D-6C")

    resolver.current_ip(cam)
    resolver.current_ip(cam)
    assert llamadas["n"] == 1  # la segunda salió del cache

    resolver.invalidate(cam)
    resolver.current_ip(cam)
    assert llamadas["n"] == 2  # tras invalidar, vuelve a mirar ARP


def test_barre_la_subred_cuando_el_ping_no_alcanza(monkeypatch):
    estado = {"barrido": False}
    tablas = [{}, {}, {"c0:8a:60:8c:7d:6c": "192.168.1.77"}]

    monkeypatch.setattr(resolver, "_tabla_arp", lambda: tablas.pop(0) if tablas else {})
    monkeypatch.setattr(resolver, "_ping", lambda ip: None)

    def barrer(ip):
        estado["barrido"] = True

    monkeypatch.setattr(resolver, "_barrer", barrer)

    # El barrido es caro: solo corre con force=True (reintento tras un fallo).
    ip = resolver.current_ip(_cam("C0-8A-60-8C-7D-6C", ip="192.168.1.50"), force=True)
    assert estado["barrido"] is True
    assert ip == "192.168.1.77"
