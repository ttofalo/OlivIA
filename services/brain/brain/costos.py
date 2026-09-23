"""Cuánto gastamos en IA: tokens y USD por cada llamada a Jev y a DeepSeek.

Ni Typesafe ni DeepSeek exponen el consumo por API. DeepSeek da solo el saldo
y Typesafe solo los tokens de cada respuesta. Así que el brain anota cada
llamada en un JSONL (una línea por llamada) y de ahí salen los resúmenes.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

log = structlog.get_logger()

# USD por millón de tokens: (fuera de pico, pico). DeepSeek cobra pico de lunes
# a viernes de 01 a 04 y de 06 a 10 UTC (22 a 01 y 03 a 07 en Córdoba); el
# resto, incluidos fines de semana, es la mitad. Jev tiene precio fijo y no
# cobra la salida.
PRECIOS: dict[str, dict[str, tuple[float, float]]] = {
    "deepseek-v4-pro": {"entrada": (0.66, 1.32), "cache": (0.022, 0.044), "salida": (1.98, 3.96)},
    "deepseek-flash": {"entrada": (0.15, 0.30), "cache": (0.003, 0.006), "salida": (0.60, 1.20)},
    "jev": {"entrada": (0.042, 0.042), "cache": (0.0, 0.0), "salida": (0.0, 0.0)},
}

HORAS_PICO_UTC = {1, 2, 3, 6, 7, 8, 9}


def es_pico(cuando: datetime) -> bool:
    if cuando.weekday() >= 5:
        return False
    return cuando.hour in HORAS_PICO_UTC


def _tarifa(proveedor: str, modelo: str | None) -> dict[str, tuple[float, float]] | None:
    if proveedor == "jev":
        return PRECIOS["jev"]
    nombre = (modelo or "").lower()
    if "pro" in nombre:
        return PRECIOS["deepseek-v4-pro"]
    if "flash" in nombre:
        return PRECIOS["deepseek-flash"]
    return None


def costo_usd(
    proveedor: str,
    modelo: str | None,
    entrada: int,
    salida: int,
    cache: int = 0,
    cuando: datetime | None = None,
) -> float:
    """USD de una llamada. `cache` son tokens de entrada que pegaron en caché."""
    tarifa = _tarifa(proveedor, modelo)
    if tarifa is None:
        log.warning("modelo sin precio conocido", proveedor=proveedor, modelo=modelo)
        return 0.0
    i = 1 if es_pico(cuando or datetime.now(UTC)) else 0
    sin_cache = max(entrada - cache, 0)
    return (
        sin_cache * tarifa["entrada"][i] + cache * tarifa["cache"][i] + salida * tarifa["salida"][i]
    ) / 1_000_000


def _tokens_de(usage: Any) -> tuple[int, int, int]:
    """(entrada, salida, cache) desde el objeto usage de OpenAI o de Typesafe."""
    if usage is None:
        return 0, 0, 0
    entrada = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None) or 0
    salida = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None) or 0
    # DeepSeek informa el caché en prompt_cache_hit_tokens; OpenAI en
    # prompt_tokens_details.cached_tokens.
    cache = getattr(usage, "prompt_cache_hit_tokens", None)
    if cache is None:
        detalles = getattr(usage, "prompt_tokens_details", None)
        cache = getattr(detalles, "cached_tokens", None)
    return int(entrada), int(salida), int(cache or 0)


class Registro:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._lock = threading.Lock()

    def anotar(
        self,
        proveedor: str,
        modelo: str | None,
        usage: Any,
        motivo: str = "",
    ) -> float:
        entrada, salida, cache = _tokens_de(usage)
        ahora = datetime.now(UTC)
        usd = costo_usd(proveedor, modelo, entrada, salida, cache, ahora)
        fila = {
            "t": ahora.isoformat(timespec="seconds"),
            "proveedor": proveedor,
            "modelo": modelo,
            "motivo": motivo,
            "entrada": entrada,
            "salida": salida,
            "cache": cache,
            "usd": round(usd, 8),
        }
        log.info("costo", **fila)
        if self._path is not None:
            try:
                with self._lock:
                    self._path.parent.mkdir(parents=True, exist_ok=True)
                    with self._path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            except OSError:
                log.exception("no pude anotar el costo", path=str(self._path))
        return usd

    def filas(self) -> list[dict[str, Any]]:
        if self._path is None or not self._path.exists():
            return []
        out = []
        for linea in self._path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
        return out

    def resumen(self, desde: datetime | None = None) -> dict[str, dict[str, float]]:
        """Totales por proveedor desde `desde`: llamadas, entrada, salida, usd."""
        corte = desde.isoformat(timespec="seconds") if desde else ""
        totales: dict[str, dict[str, float]] = {}
        for fila in self.filas():
            if fila.get("t", "") < corte:
                continue
            t = totales.setdefault(
                fila["proveedor"], {"llamadas": 0, "entrada": 0, "salida": 0, "usd": 0.0}
            )
            t["llamadas"] += 1
            t["entrada"] += fila.get("entrada", 0)
            t["salida"] += fila.get("salida", 0)
            t["usd"] += fila.get("usd", 0.0)
        return totales

    def texto(self, ahora: datetime | None = None) -> str:
        """Resumen corto para el chat: hoy por proveedor, y el total del mes."""
        ahora = ahora or datetime.now(UTC)
        hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        mes = hoy.replace(day=1)
        de_hoy = self.resumen(hoy)
        total_mes = sum(t["usd"] for t in self.resumen(mes).values())
        if not de_hoy:
            return f"Hoy no gastamos nada. En el mes van {_usd(total_mes)}."
        detalle = " y ".join(
            f"{_nombre(p)} {_llamadas(t['llamadas'])} ({_k(t['entrada'] + t['salida'])} tokens, "
            f"{_usd(t['usd'])})"
            for p, t in de_hoy.items()
        )
        total_hoy = sum(t["usd"] for t in de_hoy.values())
        texto = f"Hoy: {detalle}, total {_usd(total_hoy)}."
        if total_mes > total_hoy + 1e-9:
            texto += f" En el mes van {_usd(total_mes)}."
        return texto


def _llamadas(n: float) -> str:
    n = int(n)
    return "1 llamada" if n == 1 else f"{n} llamadas"


def _nombre(proveedor: str) -> str:
    return {"jev": "Jev", "deepseek": "DeepSeek"}.get(proveedor, proveedor)


def _k(tokens: float) -> str:
    return f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(int(tokens))


def _usd(usd: float) -> str:
    return f"USD {usd:.4f}" if usd < 1 else f"USD {usd:.2f}"


def saldo_deepseek(base_url: str, api_key: str, timeout: float = 5.0) -> str | None:
    """Saldo en USD que queda en la cuenta de DeepSeek, o None si no se pudo."""
    if not api_key:
        return None
    try:
        r = httpx.get(
            base_url.rstrip("/") + "/user/balance",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        r.raise_for_status()
        for info in r.json().get("balance_infos", []):
            if info.get("currency") == "USD":
                return str(info.get("total_balance"))
    except Exception:
        log.exception("no pude leer el saldo de DeepSeek")
    return None


# Registro único del proceso. Los tests y el arranque lo configuran.
_registro = Registro(None)


def configurar(path: Path | None) -> None:
    global _registro
    _registro = Registro(path)


def anotar(proveedor: str, modelo: str | None, usage: Any, motivo: str = "") -> float:
    return _registro.anotar(proveedor, modelo, usage, motivo)


def resumen_texto() -> str:
    return _registro.texto()


__all__ = [
    "PRECIOS",
    "Registro",
    "anotar",
    "configurar",
    "costo_usd",
    "es_pico",
    "resumen_texto",
    "saldo_deepseek",
]
