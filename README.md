# camaritas

Asistente de WhatsApp para controlar la casa: cámaras, boyeros eléctricos y lo que vayamos sumando.

La familia le escribe o le manda un audio, el bot entiende qué le piden y ejecuta. Pedir una foto del portón, mover la cámara de la cabaña a un preset, ver si el boyero del fondo está prendido.

## Cómo está partido

Tres servicios y un firmware:

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

## Documentación

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — cómo viaja un mensaje de punta a punta
- [docs/HARDWARE.md](docs/HARDWARE.md) — inventario, qué falta comprar, puertos y protocolos
- [docs/JEV.md](docs/JEV.md) — por qué Jev y dónde va cada decisión
- [docs/ROADMAP.md](docs/ROADMAP.md) — fases, empezando por la foto
- [docs/SECURITY.md](docs/SECURITY.md) — es la casa de tu familia, leer antes de exponer nada
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
