#!/usr/bin/env python3
"""Puntúa con Jev los avisos de Mercado Libre que junta placas_ml.mjs.

Una búsqueda de "raspberry pi 4" en ML devuelve fuentes, cajas, disipadores,
kits de Arduino y alguna placa. Jev clasifica cada aviso contra opciones fijas
y la tabla sale ordenada por precio entre lo que de verdad sirve como agente.

    export TYPESAFE_API_KEY=apikey_...
    python scripts/rank_placas.py scripts/out/placas.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

NATIVO_URL = "https://api.typesafe.ai/v1/systemone"

NECESIDAD = (
    "Buscamos una computadora chica para correr el agente local de OlivIA en la "
    "casa: Linux, Python, ffmpeg, un cliente MQTT y el protocolo DVRIP de cámaras "
    "IP. Tiene que tener Ethernet o al menos WiFi, 1 GB de RAM o más, y quedar "
    "prendida las 24 horas. Un microcontrolador (ESP32, Arduino, Pico) no sirve. "
    "Un accesorio suelto (fuente, caja, disipador, microSD, cable) tampoco."
)

PREGUNTAS = {
    "tipo": {
        "type": "choice",
        "instructions": "Qué es lo que se vende en este aviso",
        "criteria": {
            "raspberry_pi_5": "Raspberry Pi 5",
            "raspberry_pi_4": "Raspberry Pi 4 (modelo B)",
            "raspberry_pi_3": "Raspberry Pi 3 (B o B+)",
            "raspberry_pi_zero_2": "Raspberry Pi Zero 2 W",
            "raspberry_pi_zero_1": "Raspberry Pi Zero o Zero W original, sin el 2",
            "orange_pi": "Orange Pi de cualquier modelo",
            "radxa": "Radxa Rock o Radxa Zero",
            "otra_sbc_arm": "Otra placa ARM con Linux: Banana Pi, Odroid, Le Potato, Rock Pi",
            "mini_pc_x86": "Mini PC x86 (N100, N95, J4125, Celeron) nuevo",
            "thin_client": "Thin client usado: Dell Wyse, HP T520/T530/T630, Lenovo, Fujitsu",
            "microcontrolador": "ESP32, ESP8266, Arduino, Raspberry Pi Pico o un kit de esos",
            "accesorio": "Fuente, caja, disipador, ventilador, microSD, cable, HAT, pantalla",
            "otro": "Otra cosa que no encaja arriba",
        },
    },
    "sirve": {
        "type": "choice",
        "instructions": "Sirve para correr el agente descripto en la necesidad",
        "criteria": {
            "sirve": "Es una computadora con Linux, con RAM y puertos suficientes",
            "justa": "Corre Linux pero va a andar apretada: poca RAM, sin Ethernet, o muy vieja",
            "no_sirve": "No es una computadora con Linux, o es un accesorio",
        },
    },
    "ram_gb": {
        "type": "choice",
        "instructions": "Cuánta RAM dice el aviso",
        "criteria": {
            "0.5": "512 MB",
            "1": "1 GB",
            "2": "2 GB",
            "4": "4 GB",
            "8": "8 GB o más",
            "desconocida": "El aviso no lo dice",
        },
    },
    "es_kit": {
        "type": "noul",
        "instructions": "Incluye fuente, caja o microSD además de la placa",
    },
    "es_usado": {
        "type": "noul",
        "instructions": "Es usado, reacondicionado o refurbished",
    },
}


def clasificar(aviso: dict, key: str, model: str) -> dict:
    payload = {
        "model": model,
        "state": {
            "necesidad": NECESIDAD,
            "titulo": aviso["titulo"][:200],
            "precio_ars": aviso["precio"],
            "vendedor": aviso.get("vendedor", "")[:60],
            "vendidos": aviso.get("vendidos", 0),
            "busqueda_que_lo_encontro": aviso["query"],
        },
        "questions": PREGUNTAS,
    }
    req = urllib.request.Request(
        NATIVO_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fila(aviso: dict, respuesta: dict) -> dict:
    a = respuesta["answers"]
    return {
        **aviso,
        "tipo": a["tipo"]["choice"],
        "tipo_conf": round(a["tipo"]["confidence"], 2),
        "sirve": a["sirve"]["choice"],
        "sirve_conf": round(a["sirve"]["confidence"], 2),
        "ram_gb": a["ram_gb"]["choice"],
        "es_kit": round(a["es_kit"]["noul"], 2),
        "es_usado": round(a["es_usado"]["noul"], 2),
        "model": respuesta.get("model"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo", help="JSON que dejó placas_ml.mjs")
    ap.add_argument("--model", default="jev-latest")
    ap.add_argument("--max-precio", type=int, default=0, help="en pesos, 0 = sin tope")
    ap.add_argument("--salida", default="scripts/out/placas-ranking.json")
    args = ap.parse_args()

    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key:
        raise SystemExit("Falta TYPESAFE_API_KEY")

    with open(args.archivo, encoding="utf-8") as fh:
        avisos = [a for a in json.load(fh) if a.get("precio")]
    if args.max_precio:
        avisos = [a for a in avisos if a["precio"] <= args.max_precio]
    print(f"{len(avisos)} avisos a clasificar", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=8) as pool:
        filas = list(
            pool.map(lambda a: fila(a, clasificar(a, key, args.model)), avisos)
        )

    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump(filas, fh, indent=1, ensure_ascii=False)

    utiles = [f for f in filas if f["sirve"] in ("sirve", "justa")]
    utiles.sort(key=lambda f: (f["sirve"] != "sirve", f["precio"]))

    print()
    print(
        f"{'precio':>10}  {'tipo':<20} {'ram':>4} {'kit':>4} {'usado':>5} {'vend':>5}  título"
    )
    for f in utiles[:40]:
        print(
            f"{f['precio']:>10,}  {f['tipo']:<20} {f['ram_gb']:>4} "
            f"{f['es_kit']:>4.1f} {f['es_usado']:>5.1f} {f['vendidos']:>5}  "
            f"{f['titulo'][:60]}" + ("  (justa)" if f["sirve"] == "justa" else "")
        )
    print()
    print(f"{len(utiles)} sirven de {len(filas)}. Detalle con URLs en {args.salida}")


if __name__ == "__main__":
    main()
