# Qué reutilizamos y de dónde

Barrido de GitHub del 2026-09-21: 36 búsquedas por dominio más lookup directo, 149 repos únicos en [prior-art/candidatos.json](prior-art/candidatos.json).

El ranking con Jev está en [../scripts/rank_repos.py](../scripts/rank_repos.py) y todavía no corrió: el AI Gateway devuelve 403 hasta que la cuenta de Vercel tenga tarjeta. Los veredictos de acá abajo salen de leer los repos, no del modelo.

## Dos hallazgos que cambian el plan

### El backend de boyeros ya existe

[ttofalo/automatizacion-boyeros-backend](https://github.com/ttofalo/automatizacion-boyeros-backend) es tuyo, de enero a abril de 2026. FastAPI con SQLAlchemy y SQLite, routers para `/boyeros`, `/esp` y `/auth`, login por PIN con JWT, WebSockets con un `websocket_manager` y un `state_service`, y scripts de deploy.

Los ESP32 del campo ya le hablan por HTTP y WebSocket, y ya funcionan. La fase 4 del roadmap decía escribir firmware con MQTT desde cero, y eso ahora es trabajo de más.

**Lo que conviene:** OlivIA consume ese backend por HTTP en vez de reimplementar el canal. El `brain` le pega a `/boyeros` para leer estado y a su endpoint de control para cortar, y los ESP32 siguen hablando con lo que ya conocen. Dos cosas a resolver: el backend usa JWT con PIN, así que OlivIA necesita su propia credencial de servicio, y hay que decidir si se levanta en el mismo VPS o queda donde está.

Queda una asimetría: cámaras por MQTT, boyeros por HTTP. Vale la pena igual, porque el hardware del campo ya está andando y tocarlo es el riesgo más caro del proyecto.

### Las cámaras pueden hablar

[LucaCraft89/xm-cam-talk](https://github.com/LucaCraft89/xm-cam-talk) implementa el canal `OPTalk` de DVRIP, que es el que usa el botón de hablar de iCSee. Expone un bridge Docker con API HTTP y WebSocket, además de la integración de Home Assistant.

Eso significa que OlivIA puede contestar por el parlante de una cámara, no solo por WhatsApp. Para el objetivo de que termine siendo un Jarvis, es la diferencia entre un bot que manda fotos y algo que está presente en la casa.

[TheJenos/xmeye-control](https://github.com/TheJenos/xmeye-control) llega al mismo lugar por otro lado: convierte el NVR en un `media_player` de Home Assistant y le manda TTS.

Riesgo de xm-cam-talk: todos los commits son del 29 de agosto de 2026, un solo día, y tiene cero estrellas. El valor está en el protocolo resuelto, así que lo trataría como código a leer y portar, no como dependencia.

## Por capa

### Cámaras XiongMai (DVRIP, puerto 34567)

| Repo | Stars | Último push | Licencia | Veredicto |
|---|---|---|---|---|
| [OpenIPC/python-dvr](https://github.com/OpenIPC/python-dvr) | 77 | 2026-09 | MIT | **Dependencia.** La librería base, activa. Ya está en `services/agent/pyproject.toml` |
| [TheJenos/xmeye-control](https://github.com/TheJenos/xmeye-control) | 0 | 2026-09 | MIT | **Referencia fuerte.** Tiene tests, CI y snapshots por DVRIP. El código más nuevo del rubro |
| [equake/hass-xmeye](https://github.com/equake/hass-xmeye) | 7 | 2026-08 | MIT | **Referencia.** Integra go2rtc, docs largos sobre el protocolo |
| [dbuezas/icsee-ptz](https://github.com/dbuezas/icsee-ptz) | 126 | 2026-01 | sin licencia | **Referencia de comandos PTZ.** 28 issues abiertos y poco movimiento. Sin licencia, así que no se copia código |
| [LucaCraft89/xm-cam-talk](https://github.com/LucaCraft89/xm-cam-talk) | 0 | 2026-08 | MIT | **Portar.** Audio bidireccional por OPTalk |
| [alexshpilkin/dvrip](https://github.com/alexshpilkin/dvrip) | 75 | 2022 | CC0 | **Referencia de protocolo.** Archivado, pero la documentación del framing sirve |
| [KostasEreksonas/DVRIP_analysis](https://github.com/KostasEreksonas/DVRIP_analysis) | 2 | 2026-07 | GPL-3.0 | **Herramienta.** Disector de Wireshark para DVRIP. Para cuando un comando no responda y haya que ver el cable |
| [bsergei/DvrMqtt](https://github.com/bsergei/DvrMqtt) | 8 | 2025-12 | GPL-3.0 | **Referencia.** DVRIP a MQTT, que es exactamente nuestro puente, pero en C# |

Un cambio de diseño que sale de leer estos: **xmeye-control saca snapshots por DVRIP, sin RTSP ni ffmpeg.** El agente hoy levanta un proceso de ffmpeg por foto, que en una Pi cuesta y tarda entre 1 y 3 segundos. Si el snapshot sale del mismo socket DVRIP que ya usamos para PTZ, se va todo el ffmpeg y baja la latencia. Vale probar las dos vías en la fase 1 y medir.

### Streaming y snapshots

| Repo | Stars | Veredicto |
|---|---|---|
| [AlexxIT/go2rtc](https://github.com/AlexxIT/go2rtc) | 14230 | **Dependencia, si el snapshot por DVRIP no alcanza.** Un binario en la Pi, API HTTP para snapshots, maneja RTSP roto mejor que ffmpeg suelto |
| [bluenviron/mediamtx](https://github.com/bluenviron/mediamtx) | 20220 | Alternativa a go2rtc, más orientada a servidor de streams que a cámaras |
| [kiwimato/dvrbridge](https://github.com/kiwimato/dvrbridge) | 0 | **Referencia.** Servidor RTSP en Python puro sin ffmpeg, y una idea buena: conecta al DVR solo cuando alguien mira, para no castigar hardware frágil |

### Eventos de movimiento

| Repo | Stars | Veredicto |
|---|---|---|
| [toxuin/alarmserver](https://github.com/toxuin/alarmserver) | 175 | **Referencia.** Alarmas de cámaras IP a MQTT, pero apunta a Hikvision y Dahua y no se toca desde 2024 |
| [blakeblackshear/frigate](https://github.com/blakeblackshear/frigate) | 36039 | **No por ahora.** Detección local de objetos, el estándar del rubro. Pide más máquina que una Pi 4, con acelerador tipo Coral. Evaluarlo en la fase 5 si querés distinguir una persona de un perro, y ahí con un mini PC |

Para la fase 5, las integraciones de DVRIP ya suscriben el canal de alarmas del NVR. Eso es más barato que meter detección propia.

### WhatsApp

| Repo | Stars | Veredicto |
|---|---|---|
| [WhiskeySockets/Baileys](https://github.com/WhiskeySockets/Baileys) | 11116 | **Dependencia.** Ya decidido en [DECISIONS.md](DECISIONS.md) 002 |
| [tulir/whatsmeow](https://github.com/tulir/whatsmeow) | 7386 | **Plan B.** Go, MPL-2.0, y lo usa `mautrix/whatsapp` en producción desde años. Si Baileys se rompe seguido, este es el reemplazo |
| [wwebjs/whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js) | 22608 | **Descartado.** Levanta un Chromium headless. Sobra para un VPS chico |
| [raulpetruta/ha-wa-bridge](https://github.com/raulpetruta/ha-wa-bridge) | 134 | **Referencia.** WhatsApp dentro de Home Assistant, útil para ver cómo separan la sesión del resto |

### Voz

| Repo | Stars | Veredicto |
|---|---|---|
| [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) | 53845 | **Dependencia.** Activo, corre en CPU del VPS con el modelo `base` |
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 25507 | Alternativa en Python, sin push desde 2025-11 |

Con la key del AI Gateway que ya tenés hay una tercera vía: transcribir contra el gateway y usar la misma credencial para Jev y para el audio. Menos que instalar en el VPS, y cuesta por minuto.

### Jev

| Repo | Stars | Veredicto |
|---|---|---|
| [typesafe-ai/typesafe-sdk-python](https://github.com/typesafe-ai/typesafe-sdk-python) | 186 | **Dependencia.** El SDK oficial, ya está en `services/brain/pyproject.toml` |
| [moritzkremb/jev-voice-browser](https://github.com/moritzkremb/jev-voice-browser) | 209 | **Referencia, la más cercana a lo nuestro.** Voz a intent con Jev y después la acción |
| [dbreunig/building-with-jev-skill](https://github.com/dbreunig/building-with-jev-skill) | 128 | **Referencia.** Patrones para escribir las preguntas |
| [Anil-matcha/awesome-jev-by-typesafe](https://github.com/Anil-matcha/awesome-jev-by-typesafe) | 765 | **Referencia.** Starter code y casos con evidencia |
| [wfzyx/von](https://github.com/wfzyx/von) | 367 | **Escape hatch.** System One open source, Apache-2.0, sub-15ms. Si Jev sube de precio o querés correrlo en el VPS |
| [ikermoel/open-alternative-jev](https://github.com/ikermoel/open-alternative-jev) | 47 | Otra alternativa abierta, más chica |

Hay nueve listas "awesome-jev" con estrellas infladas y contenido repetido. Las descarto salvo las dos de arriba.

### Boyeros y ESP32

| Repo | Veredicto |
|---|---|
| [ttofalo/automatizacion-boyeros-backend](https://github.com/ttofalo/automatizacion-boyeros-backend) | **Reutilizar.** Ver arriba |
| [esphome/esphome](https://github.com/esphome/esphome) | **Dependencia para hardware nuevo.** Los ESP32 que ya andan no se tocan. Para el próximo sensor, un YAML de veinte líneas |
| [knolleary/pubsubclient](https://github.com/knolleary/pubsubclient) | Si algún ESP32 tiene que hablar MQTT a mano |

Para la idea de los tanques de agua hay varios proyectos chicos con ESP32 y MQTT: [tank-buddy](https://github.com/tank-buddy/tank-buddy) en MicroPython y [fluidwire/esp32-hcsr04-tank-level](https://github.com/fluidwire/esp32-hcsr04-tank-level) con HC-SR04. Ninguno tiene tracción, pero el problema es chico y el código se lee en una tarde.

### Home Assistant

No lo adoptamos, y conviene dejar escrito por qué. Casi todo el prior art de cámaras XiongMai vive como integración de Home Assistant, así que hay que portar código en vez de instalarlo.

La alternativa sería montar Home Assistant y que OlivIA le hable por su API. Ganás las integraciones hechas y perdés el control del camino crítico: cada foto pasaría por HA, y HA en una Pi con cuatro cámaras es una pieza más que se puede caer. Para la fase 7, cuando entren luces y portón, vale reconsiderarlo.

Dos que sirven de referencia para cuando lleguemos a la fase 6: [hoornet/nives](https://github.com/hoornet/nives), un asistente con memoria persistente para HA, y [rusty4444/hermes-voice-ha-integration](https://github.com/rusty4444/hermes-voice-ha-integration), voz on-device.

## Un dato de seguridad que apareció buscando

[d3fudd/Xiongmai-Net-Surveillance-Authentication](https://github.com/d3fudd/Xiongmai-Net-Surveillance-Authentication) es un exploit público que saltea la autenticación de las cámaras XiongMai, de octubre de 2025. Y [KostasEreksonas/Besder-6024PB-XMA501-ip-camera](https://github.com/KostasEreksonas/Besder-6024PB-XMA501-ip-camera) es una investigación de seguridad sobre una cámara de la misma familia.

O sea: la contraseña de tus cámaras no es una defensa. Cualquiera que llegue al puerto 34567 entra. Eso no cambia el plan, lo confirma: el agente local no expone nada, el router no abre puertos, y el P2P de iCSee conviene apagarlo. Está en [SECURITY.md](SECURITY.md), y ahora con un motivo concreto en vez de una precaución general.

## Cómo repetir esto

```bash
# el barrido está en el historial de esta sesión; el resultado, en prior-art/candidatos.json
export AI_GATEWAY_API_KEY=vck_...
python scripts/rank_repos.py docs/prior-art/candidatos.json
```

El script pregunta a Jev, por cada repo, qué rol puede cumplir, cuánto cuesta aprovecharlo, si resuelve algo difícil de escribir de cero y si está atado a Home Assistant. La licencia y los meses sin actividad se calculan sin modelo, que para eso no hace falta.
