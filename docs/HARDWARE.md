# Hardware

## Lo que ya hay

| Qué | Cantidad | Dónde | Notas |
|---|---|---|---|
| Cámaras IP XiongMai (iCSee) | 3 | Casa | Conectadas al NVR, que guarda las grabaciones |
| Cámara IP XiongMai (iCSee) | 1 | Cabaña | Graba en su propio SSD. Es la que más movemos de posición |
| NVR | 1 | Casa | Recibe las 3 cámaras de la casa |
| ESP32 | varios | Campo | Controlan boyeros eléctricos |
| Router principal | 1 | Casa | De acá sale el cable a la cabaña |
| AP / repetidor | 1 | Cabaña | SSID distinto, toma internet por cable desde el router principal |

## Lo que falta comprar

**Una Raspberry Pi para el agente local.** Un ESP32 no sirve para esto: no puede hacer de proxy RTSP, no corre ffmpeg y no implementa DVRIP. Necesita un Linux.

| Opción | Sirve para | Contra |
|---|---|---|
| Pi 5 (4 GB) | Todo, con margen para detección de movimiento local | La más cara |
| **Pi 4 (2 GB)** | Snapshots, PTZ, MQTT, varios streams a la vez | Recomendada. Precio y capacidad equilibrados |
| Pi Zero 2 W | Snapshots y PTZ de a uno | Justa para ffmpeg. Sin ethernet, y acá conviene cable |
| Mini PC usado (N100, thin client) | Todo, con lugar para grabar clips | Consume más, ocupa más |

Con la Pi hace falta una fuente decente, una microSD de 32 GB clase A2 y un cable de red al router. WiFi también anda, pero si el agente se cae cuando llueve la culpa va a ser del WiFi.

**Un número de WhatsApp aparte.** Un chip prepago barato o un número virtual. Baileys usa la API de WhatsApp Web sin autorización de Meta, así que existe riesgo de ban. Que el riesgo caiga sobre un número descartable y no sobre tu WhatsApp personal.

## Puertos y protocolos de las cámaras

Las XiongMai se venden bajo muchas marcas (iCSee, XMEye, Sofia, NetSurveillance) y todas hablan lo mismo:

| Puerto | Protocolo | Para qué |
|---|---|---|
| 34567 | DVRIP / Sofia | PTZ, presets, config, búsqueda de grabaciones. Es lo que usa la app iCSee |
| 554 | RTSP | Stream de video. URL típica `rtsp://user:pass@ip:554/user=admin&password=&channel=1&stream=0.sdp` |
| 8899 | ONVIF | PTZ y eventos estándar, si está habilitado |
| 80 | HTTP | Interfaz web, a veces con snapshot directo |

Librerías y documentación del protocolo, con el veredicto de cada una en [PRIOR_ART.md](PRIOR_ART.md):

- [OpenIPC/python-dvr](https://github.com/OpenIPC/python-dvr) — DVRIP en Python, incluye PTZ y presets. La dependencia que usamos
- [Códigos de DVRIP](https://gist.github.com/ekwoodrich/a6d7b8db8f82adf107c3c366e61fd36f) — tabla de respuestas y comandos del protocolo. Sin esto, un error de cámara es un número suelto
- [TheJenos/xmeye-control](https://github.com/TheJenos/xmeye-control) — snapshots por DVRIP sin ffmpeg, y TTS por el parlante del NVR
- [dbuezas/icsee-ptz](https://github.com/dbuezas/icsee-ptz) — referencia de los comandos PTZ. Sin licencia, así que se lee y no se copia
- [kinsi55/node_dvripclient](https://github.com/kinsi55/node_dvripclient) — el parser de paquetes de video más legible, en JavaScript
- [janglapuk/xiongmai-cam-api](https://github.com/janglapuk/xiongmai-cam-api) — cuatro archivos, para entender el handshake antes de debuggear

### Qué significan los códigos que devuelve una cámara

Los más frecuentes, del gist de arriba:

| Código | Qué pasó |
|---|---|
| 100 | Éxito |
| 101 | Error desconocido |
| 106 | Usuario o contraseña incorrectos |
| 107 | Permisos insuficientes |
| 108 | Timeout |
| 109 | No encontró el archivo |
| 117 | El mensaje está mal formado |
| 118 | La cámara no tiene protocolo PTZ configurado |
| 121 | El canal digital no está habilitado |

El 118 es el que importa para la cabaña: si aparece, la cámara acepta comandos PTZ pero no tiene el protocolo seteado, y eso se arregla desde iCSee.

## Lo que hay que verificar en casa

Esto lo resuelve `scripts/discover.py` corriendo desde la Pi. Antes de escribir código del agente hay que saber:

1. **IP de cada cámara y del NVR.** Fijarlas por DHCP reservation en el router, o el agente se va a romper solo.
2. **Si el repetidor de la cabaña hace bridge o NAT.** Si hace bridge, la cámara de la cabaña está en la misma subred que todo lo demás y un solo agente alcanza. Si hace NAT, queda en una subred aparte y hay que pasarlo a modo AP. El script lo detecta comparando subredes.
3. **Qué puertos responde cada cámara.** Si alguna no tiene ONVIF prendido, hay que habilitarlo desde iCSee o ir por DVRIP.
4. **Si el PTZ de la cabaña es real.** Algunas cámaras de esa familia exponen comandos PTZ aunque no tengan motor. El script intenta un movimiento corto y vos mirás si se mueve.
5. **Credenciales.** Usuario y contraseña de cada cámara y del NVR. Cambiar la contraseña de fábrica ahora, no después.
6. **Si conviene ir a la cámara o al NVR.** Sacar el stream del NVR descarga a la cámara, pero mete un intermediario. Probar las dos.

## ESP32 de los boyeros

Preguntas abiertas para cuando lleguemos a esa fase:

- Qué mide cada uno hoy: presencia de pulso, voltaje, nada.
- Si cortan el boyero con relé o solo reportan.
- Qué firmware tienen: Arduino a mano, ESPHome, Tasmota.
- Cómo llegan a internet desde el campo.

Si el firmware actual es código propio, se le suma un cliente MQTT. Si está vacío, ESPHome resuelve el 90% con un YAML.
