#!/usr/bin/env python3
"""Puntúa candidatos de GitHub con Jev.

Un barrido de GitHub devuelve cien repos y la mayoría no sirve. Leerlos todos a
mano es caro; pasarlos por un LLM es lento y cuesta. Jev devuelve decisiones
tipadas con confianza calibrada en menos de medio segundo, y las opciones son
fijas, así que el resultado entra en una tabla sin parsear texto.

Entrada: el JSON que produce el barrido, una lista de
    {full_name, description, stars, lang, pushed, license, topics}

Uso:
    export AI_GATEWAY_API_KEY=vck_...        # Vercel AI Gateway
    python scripts/rank_repos.py candidatos.json

    export TYPESAFE_API_KEY=sk-...           # o la API nativa de TypeSafe
    python scripts/rank_repos.py candidatos.json --nativo

Lo que hace falta juzgar va a Jev. La licencia y la actividad se calculan acá,
que son determinísticas y no valen una llamada.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

GATEWAY_URL = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
NATIVO_URL = "https://api.typesafe.ai/v1/systemone"

OBJETIVO = (
    "OlivIA, un asistente de casa por WhatsApp. Controla cámaras XiongMai (iCSee, "
    "DVRIP en el puerto 34567) y un NVR, mueve una cámara PTZ, saca snapshots por "
    "RTSP, y controla boyeros eléctricos con ESP32. Corre en un VPS con un agente "
    "local en una Raspberry. Python y TypeScript."
)

PREGUNTAS = {
    "rol": {
        "type": "choice",
        "instructions": "Qué rol puede cumplir este repo en el proyecto",
        "criteria": {
            "dependencia": "Se instala y se usa como librería o servicio, sin tocarlo",
            "fork": "Conviene forkearlo y modificarlo para el caso nuestro",
            "referencia": "No se usa el código, pero sirve para entender un protocolo o copiar un enfoque",
            "descartar": "No aporta nada al proyecto",
        },
    },
    "esfuerzo": {
        "type": "score",
        "instructions": "Cuánto trabajo cuesta aprovecharlo",
        "criteria": [
            "Se instala y anda",
            "Un día de trabajo para integrarlo",
            "Una semana: hay que portar o reescribir partes",
            "Más barato escribirlo de cero",
        ],
    },
    "resuelve_lo_dificil": {
        "type": "noul",
        "instructions": (
            "Resuelve una parte del problema que sería difícil de escribir de cero, "
            "como un protocolo binario propietario, ingeniería inversa de hardware "
            "o streaming de video"
        ),
    },
    "atado_a_home_assistant": {
        "type": "noul",
        "instructions": (
            "Está escrito como integración de Home Assistant y su lógica sería difícil "
            "de usar fuera de Home Assistant"
        ),
    },
}


def clasificar(repo: dict, url: str, key: str, model: str) -> dict:
    payload = {
        "model": model,
        "state": {
            "objetivo_del_proyecto": OBJETIVO,
            "repo": repo["full_name"],
            "descripcion": repo.get("description") or "",
            "lenguaje": repo.get("lang"),
            "topics": repo.get("topics", []),
            "stars": repo.get("stars"),
            "ultimo_push": repo.get("pushed", "")[:10],
        },
        "questions": PREGUNTAS,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def meses_sin_tocar(pushed: str) -> float:
    d = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - d).days / 30.44


PERMISIVAS = {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "CC0-1.0", "Unlicense"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo", help="JSON con los candidatos")
    ap.add_argument("--nativo", action="store_true", help="usar api.typesafe.ai en vez del gateway")
    ap.add_argument("--model", default="jev-latest")
    ap.add_argument("--min-stars", type=int, default=0)
    args = ap.parse_args()

    if args.nativo:
        url, key = NATIVO_URL, os.environ.get("TYPESAFE_API_KEY", "")
        var = "TYPESAFE_API_KEY"
    else:
        url, key = GATEWAY_URL, os.environ.get("AI_GATEWAY_API_KEY", "")
        var = "AI_GATEWAY_API_KEY"
    if not key:
        raise SystemExit(f"Falta {var}")

    repos = [r for r in json.load(open(args.archivo)) if r.get("stars", 0) >= args.min_stars]
    print(f"{len(repos)} repos a clasificar", file=sys.stderr)

    filas = []
    for i, repo in enumerate(repos, 1):
        try:
            res = clasificar(repo, url, key, args.model)
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode()[:300]
            if e.code in (402, 403) and "credit" in cuerpo.lower():
                raise SystemExit(
                    "El gateway pide tarjeta en la cuenta de Vercel antes de servir "
                    "requests. Agregala y volvé a correr esto."
                )
            raise SystemExit(f"{repo['full_name']}: HTTP {e.code} {cuerpo}")

        a = res["answers"]
        filas.append({
            "repo": repo["full_name"],
            "rol": a["rol"]["choice"],
            "rol_conf": round(a["rol"]["confidence"], 3),
            "esfuerzo": round(a["esfuerzo"]["score"], 2),
            "resuelve_lo_dificil": round(a["resuelve_lo_dificil"]["noul"], 3),
            "atado_a_ha": round(a["atado_a_home_assistant"]["noul"], 3),
            "stars": repo.get("stars"),
            "meses_sin_tocar": round(meses_sin_tocar(repo["pushed"]), 1),
            "licencia_ok": repo.get("license") in PERMISIVAS,
            "url": repo.get("url"),
            "model": res.get("model"),
        })
        print(f"  [{i}/{len(repos)}] {repo['full_name']}: {a['rol']['choice']}", file=sys.stderr)

    orden = {"dependencia": 0, "fork": 1, "referencia": 2, "descartar": 3}
    filas.sort(key=lambda f: (orden[f["rol"]], f["esfuerzo"], -f["resuelve_lo_dificil"]))

    json.dump(filas, open("ranking.json", "w"), indent=1, ensure_ascii=False)
    print()
    print(f"{'repo':<46} {'rol':<12} {'esf':>4} {'dificil':>8} {'HA':>5} {'meses':>6}")
    print("-" * 88)
    for f in filas:
        if f["rol"] == "descartar":
            continue
        print(f"{f['repo'][:46]:<46} {f['rol']:<12} {f['esfuerzo']:>4} "
              f"{f['resuelve_lo_dificil']:>8} {f['atado_a_ha']:>5} {f['meses_sin_tocar']:>6}")
    print(f"\nranking.json escrito. {sum(1 for f in filas if f['rol'] == 'descartar')} descartados.")


if __name__ == "__main__":
    main()
