# Qué reutilizamos y de dónde

Barrido de GitHub del 2026-09-21: 62 búsquedas por dominio más lookup directo, 159 repos únicos. Los clasificó Jev con [scripts/rank_repos.py](../scripts/rank_repos.py) en 2 minutos y 16 segundos, con `jev-1.13.0`, y descartó 46.

Los datos crudos: [prior-art/candidatos.json](prior-art/candidatos.json) y [prior-art/ranking.json](prior-art/ranking.json).

Cada repo se puntuó por rol (dependencia, fork, referencia, descartar), cuánto cuesta aprovecharlo, si resuelve algo difícil de escribir de cero y si está atado a Home Assistant. La licencia y los meses sin actividad se calculan sin modelo.

## Dónde está lo difícil

Ordenando los 159 por "resuelve algo que sería difícil de escribir de cero", los siete primeros son lo mismo: el protocolo DVRIP y el streaming de video.

| | Repo | Rol | Meses sin tocar |
|---|---|---|---|
| 0.87 | alexshpilkin/dvrip | dependencia | 48 |
| 0.85 | TGJ27/xm-camera-dvrip-cpp | dependencia | 2 |
| 0.83 | kinsi55/node_dvripclient | dependencia | 60 |
| 0.82 | sofia-netsurv/python-netsurv | dependencia | 65 |
| 0.82 | KostasEreksonas/DVRIP_analysis | referencia | 3 |
| 0.81 | janglapuk/xiongmai-cam-api | dependencia | 59 |
| 0.78 | bluenviron/mediamtx | dependencia | 0 |

Hay un patrón incómodo en esa columna de la derecha. Lo que resuelve el protocolo se escribió entre 2017 y 2021 y está frío. Lo que está caliente son integraciones de Home Assistant de 2026. El protocolo no cambió en ocho años, así que el código viejo sigue sirviendo, pero nadie lo mantiene.

Conclusión para el proyecto: el conocimiento de DVRIP se saca de los repos viejos y el código que se instala sale de los nuevos.

## Los mejores, y qué sacamos de cada uno

### 1. baileys-antiban

[kobie3717/baileys-antiban](https://github.com/kobie3717/baileys-antiban), 149 estrellas, MIT, 40 versiones publicadas en npm, última de junio de 2026.

**Qué sacamos: la dependencia entera.** Rate limiting con jitter gaussiano, simulación de tipeo, warm-up de siete días para números nuevos, monitor de salud que detecta señales de ban antes de que llegue, auto-pausa cuando el riesgo sube, y clasificador de desconexiones. Se envuelve el socket en una línea.

Esto ataca el riesgo más concreto del proyecto: que Meta banee el número. Ya está aplicado en `services/gateway`.

Cuidado con la versión: en npm va por la 4.10.0, y la copia que circula dentro de otros repos es la 1.0.0. Usar el paquete, no el vendorizado.

### 2. TheJenos/xmeye-control

Cero estrellas, MIT, con tests y CI, último commit de hace días.

**Qué sacamos: dos técnicas.** Los snapshots salen por DVRIP, sin RTSP ni ffmpeg, del mismo socket que ya usamos para PTZ. Y convierte el NVR en parlante: le manda TTS y el equipo habla.

Hoy `services/agent/agent/snapshot.py` levanta un proceso de ffmpeg por foto, que en una Pi cuesta y tarda entre 1 y 3 segundos. Si el frame sale del socket DVRIP, se va todo el ffmpeg de la fase 1.

Es una integración de Home Assistant (Jev le puso 0.71 de atado a HA), así que hay que portar la lógica, no instalarla.

### 3. El gist de códigos del protocolo

[ekwoodrich/a6d7b8db8f82adf107c3c366e61fd36f](https://gist.github.com/ekwoodrich/a6d7b8db8f82adf107c3c366e61fd36f), actualizado en junio de 2026.

**Qué sacamos: la tabla de códigos de respuesta y comandos de DVRIP.** Los 100 a 121 con su significado, del 100 que es éxito al 118 que avisa que la cámara no tiene protocolo PTZ configurado.

Sin esto, un error de DVRIP es un número sin contexto. Con esto, el agente puede distinguir "contraseña incorrecta" de "esta cámara no tiene PTZ" y contestarte algo útil en vez de un stack trace.

### 4. kinsi55/node_dvripclient

30 estrellas, MIT, sin tocar desde 2021.

**Qué sacamos: el parser de paquetes de video y las tablas de constantes.** Tiene `constants/Messages.js`, `ResponseCodes.js` y `VideopacketPayloads.js`, más un `dvripstreamclient.js` y ejemplos que graban 10 segundos a MP4 y relayean el stream.

Es JavaScript, el lenguaje del gateway, y es la implementación más legible del framing de video sobre DVRIP que encontré. Sirve para entender cómo sacar un frame sin RTSP.

### 5. AlexxIT/go2rtc

14230 estrellas, MIT, activo.

**Qué sacamos: el plan B del snapshot.** Un binario en la Pi con API HTTP para pedir una imagen, y maneja RTSP roto mejor que ffmpeg suelto. Si el snapshot por DVRIP falla en alguna de tus cámaras, esto lo cubre sin escribir nada.

### 6. LucaCraft89/xm-cam-talk

Cero estrellas, MIT, todos los commits del 29 de agosto de 2026.

**Qué sacamos: el canal `OPTalk` resuelto.** Es el que usa el botón de hablar de iCSee, y no es ONVIF ni un backchannel de RTSP, así que go2rtc y Frigate no lo pueden manejar. Trae un bridge Docker con API HTTP y WebSocket, o sea que se usa sin Home Assistant.

Con esto OlivIA contesta por el parlante de una cámara. Para el objetivo del Jarvis, es la diferencia entre mandar fotos y estar presente en la casa.

Un solo día de commits, así que lo trato como protocolo resuelto para portar, no como dependencia que va a tener mantenimiento.

### 7. janglapuk/xiongmai-cam-api

27 estrellas, MIT, 2021.

**Qué sacamos: la versión legible del protocolo.** Cuatro archivos: `xmcam.py`, `xmconst.py`, `sound.py` y un ejemplo. Portado de un script en Perl.

`OpenIPC/python-dvr` es la librería que vamos a usar, pero es grande. Este se lee en una tarde y deja entender qué hace el handshake antes de debuggear el otro.

### 8. kiwimato/dvrbridge

Cero estrellas, MIT, agosto de 2026, Python puro sin dependencias.

**Qué sacamos: una idea de diseño.** Conecta al DVR solo mientras alguien está mirando, con linger configurable, y reconecta con backoff. Lo llama ser cortés con hardware frágil.

Tus cámaras son las que son, y cuatro clientes DVRIP simultáneos las pueden marear. El agente debería abrir el socket cuando hay pedido y cerrarlo después, que es lo que ya hace `cameras.py` con su context manager, y esto confirma el criterio.

### 9. sofia-netsurv/python-netsurv

80 estrellas, MIT, 2021.

**Qué sacamos: el linaje y la documentación.** Es el ancestro de `python-dvr` y el que publica el gist de códigos. Tiene un virtualenv entero commiteado, así que no se instala, se lee.

### 10. ttofalo/automatizacion-boyeros-backend

Tuyo, de enero a abril de 2026. FastAPI con SQLAlchemy y SQLite, routers de `/boyeros`, `/esp` y `/auth`, login por PIN con JWT, WebSockets con manager de estado y scripts de deploy.

**Qué sacamos: todo, tal como está.** Los ESP32 del campo ya le hablan y ya funcionan. La fase 4 pasa de escribir firmware con MQTT a consumir esta API por HTTP. Quedó como decisión [007](DECISIONS.md).

## Lo que cambia en el plan

| Qué | Antes | Ahora |
|---|---|---|
| Snapshot | ffmpeg sobre RTSP | Probar DVRIP primero, ffmpeg o go2rtc como respaldo |
| Ban de WhatsApp | Reglas de uso escritas en un README | `baileys-antiban` envolviendo el socket |
| Errores de cámara | Un número sin contexto | Tabla de códigos del gist, traducida a mensajes |
| Boyeros | Firmware nuevo con MQTT | La API que ya existe, por HTTP |
| Audio | Solo WhatsApp | El parlante de las cámaras, portando OPTalk |

## Home Assistant

No lo adoptamos. Jev marcó como atados a HA a casi todos los repos frescos de XiongMai: `xmeye-control` 0.71, `equake/hass-xmeye` 0.74, `Noneawe/ha-xmeye-nvr` 0.75. Ahí está el costo de la decisión, y es real: hay que portar en vez de instalar.

La alternativa sería montar HA y que OlivIA le hable por su API. Ganás integraciones hechas y perdés el control del camino crítico: cada foto pasaría por HA, y HA en una Pi con cuatro cámaras es una pieza más entre el pedido y la respuesta. Queda como decisión [008](DECISIONS.md), a reconsiderar en la fase 7.

## Descartados

Jev tiró 46. Los grupos:

- **Bots de WhatsApp de spam.** DANUWA-BOT, silentwolf, DREADED-GPT-AI y parientes. Son bots de warez con cientos de comandos y cero arquitectura.
- **Listas awesome de Jev.** Encontré nueve, con estrellas infladas y el mismo contenido. Sobreviven dos: [Anil-matcha/awesome-jev-by-typesafe](https://github.com/Anil-matcha/awesome-jev-by-typesafe) por el starter code y [dbreunig/building-with-jev-skill](https://github.com/dbreunig/building-with-jev-skill) por los patrones de preguntas.
- **Wrappers de ChatGPT para WhatsApp por Twilio.** Resuelven el problema de otro: mandar mensajes a clientes, no controlar una casa.
- **Whisper y derivados como repo.** Se usan como paquete, no como código a leer.

Jev también se equivocó en algunos. Puso `sweetbbak/Neural-Amy-TTS` primero entre las dependencias con esfuerzo 1.03, y es una voz de TTS sin relación con el proyecto. En los casos así la confianza venía baja: de los 53 que marcó como dependencia o fork, 31 tienen confianza bajo 0.5. El ranking sirve para ordenar la lectura, no para decidir solo.

## Un dato de seguridad

[d3fudd/Xiongmai-Net-Surveillance-Authentication](https://github.com/d3fudd/Xiongmai-Net-Surveillance-Authentication) es un exploit público de octubre de 2025 que saltea la autenticación de las cámaras XiongMai. Y [KostasEreksonas/Besder-6024PB-XMA501-ip-camera](https://github.com/KostasEreksonas/Besder-6024PB-XMA501-ip-camera) es una investigación de seguridad sobre una cámara de la misma familia.

La contraseña de tus cámaras no es una defensa. Cualquiera que llegue al puerto 34567 entra. Eso no cambia el plan, lo confirma: el agente local no expone nada, el router no abre puertos, y el P2P de iCSee conviene apagarlo. Está en [SECURITY.md](SECURITY.md), ahora con un motivo concreto.

## Cómo repetir esto

```bash
export TYPESAFE_API_KEY=apikey_...
python scripts/rank_repos.py docs/prior-art/candidatos.json --nativo
```

Costó 159 requests con unos 300 tokens de entrada cada uno. A 0.042 dólares el millón y con la salida gratis, la corrida completa sale menos de un centavo.
