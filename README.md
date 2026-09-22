# OlivIA

Asistente de casa para la familia, por WhatsApp.

Le escribís o le mandás un audio y resuelve: una foto del portón, mover la cámara de la cabaña al camino, el estado de los boyeros. Sin abrir una app, sin VPN, sin acordarse de ninguna IP.

## A dónde va

El objetivo es un Jarvis de casa: que OlivIA sepa qué está pasando, que hable en lenguaje natural y que avise sin que le preguntes.

Eso se construye por capas, y cada una funciona sola:

1. **Responde lo que le pedís.** Fotos, movimiento de cámaras, estado de dispositivos.
2. **Entiende cómo hablás.** Audios, frases sueltas, referencias a medias ("la de la cabañita").
3. **Sabe qué pasó.** Memoria de eventos, búsqueda en grabaciones, contexto de la conversación.
4. **Avisa sin que le preguntes.** Triage de detecciones, resúmenes de la mañana, alertas cuando un boyero se cae.
5. **Controla más cosas.** Portón, luces, tanques de agua, lo que vaya entrando.

La [fase 1](docs/ROADMAP.md) es una foto por WhatsApp. Lo demás se apoya sobre eso.

## Cómo está partido

| Componente | Dónde corre | Lenguaje | Qué hace |
|---|---|---|---|
| `services/gateway` | VPS | TypeScript | Habla WhatsApp con Baileys. Recibe mensajes y audios, manda fotos y respuestas. |
| `services/brain` | VPS | Python | Decide qué hacer con cada mensaje. Jev para los reflejos, Claude para lo que necesita razonar. |
| `services/agent` | Raspberry en casa | Python | Habla con las cámaras y el NVR en la LAN. Se conecta hacia afuera, no recibe conexiones. |
| `firmware/boyero` | ESP32 | C++ / ESPHome | Mide y controla los boyeros. Publica por MQTT al VPS. |

El bus entre todo es MQTT sobre TLS, con el broker en el VPS.

```
         WhatsApp
            │
      ┌─────▼─────┐
      │  gateway  │  VPS
      │   brain   │  + mosquitto + postgres
      └─────▲─────┘
            │ MQTT/TLS (siempre saliente desde casa)
     ┌──────┴──────┐
     │             │
  ┌──▼───┐    ┌────▼────┐
  │ agent│    │  ESP32  │
  │ (Pi) │    │ boyeros │
  └──┬───┘    └─────────┘
     │ LAN
  cámaras + NVR (DVRIP 34567, RTSP 554, ONVIF 8899)
```

Ningún puerto abierto en el router de casa. Todo sale desde adentro hacia el VPS.

## Los dos cerebros

El nivel 1 es [Jev](docs/JEV.md), un modelo que devuelve decisiones tipadas con probabilidades calibradas en menos de medio segundo. Clasifica cada mensaje contra el inventario real de la casa, así que no puede inventar una cámara que no existe. Resuelve la mayoría de los pedidos sin llamar a un LLM.

El nivel 2 es Claude, y entra cuando Jev duda, cuando la pregunta es abierta o cuando hay que combinar varias acciones.

## Documentación

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — cómo viaja un mensaje de punta a punta
- [docs/HARDWARE.md](docs/HARDWARE.md) — inventario, qué falta comprar, puertos y protocolos
- [docs/JEV.md](docs/JEV.md) — por qué Jev y dónde va cada decisión
- [docs/ROADMAP.md](docs/ROADMAP.md) — fases, empezando por la foto
- [docs/SECURITY.md](docs/SECURITY.md) — es la casa de tu familia, leer antes de exponer nada
- [docs/PRIOR_ART.md](docs/PRIOR_ART.md) — qué reutilizamos de otros proyectos y de dónde
- [docs/DECISIONS.md](docs/DECISIONS.md) — decisiones tomadas y por qué

## Estado

Fase 0. Nada corre todavía. El primer paso es el inventario de red con `scripts/discover.py`.

## Arranque rápido (cuando haya hardware)

```bash
cp .env.example .env          # completar credenciales
make up                       # levanta gateway, brain, mosquitto y postgres en el VPS
make qr                       # escanear el QR con el número del bot, una sola vez
python scripts/discover.py    # correr en la Pi, adentro de la LAN
```
