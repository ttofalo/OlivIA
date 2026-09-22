# Roadmap

Cada fase deja algo que funciona y se puede usar. Nada de construir seis meses para probar al final.

## Fase 0: inventario

Sin esto no se puede escribir el agente.

- [ ] Comprar la Pi y ponerla en la LAN con IP fija
- [ ] Correr `scripts/discover.py` desde la Pi
- [ ] Confirmar si el repetidor de la cabaña hace bridge o NAT
- [ ] Anotar IP, puertos y credenciales de cada cámara y del NVR
- [ ] Probar un PTZ corto en la cámara de la cabaña y verificar que se mueve
- [ ] Llenar `config/devices.yaml` con lo que salga
- [ ] Reservar IPs por DHCP en el router
- [ ] Cambiar las contraseñas de fábrica

Salida: `config/devices.yaml` con el inventario real.

## Fase 1: la foto

El objetivo mínimo y lo que pediste primero.

- [ ] VPS con Docker, mosquitto con TLS y postgres
- [ ] Número aparte con WhatsApp activado
- [ ] `gateway` con Baileys, sesión persistida y whitelist de números
- [ ] Warm-up de `baileys-antiban` en el número nuevo, siete días antes de usarlo en serio
- [ ] `agent` en la Pi: conexión MQTT saliente, heartbeat, snapshot por RTSP con ffmpeg
- [ ] Medir snapshot por DVRIP contra snapshot por ffmpeg y quedarse con el que ande
- [ ] Subida de la foto al VPS y envío al chat
- [ ] Comandos fijos: `foto cabania`, `foto frente`

Salida: mandás "foto cabania" y te llega la imagen.

## Fase 2: entender lo que le decís

- [ ] `brain` con el router de Jev construido desde `devices.yaml`
- [ ] Umbral de confianza y escalado a Claude cuando Jev duda
- [ ] Transcripción de audios
- [ ] Registro de cada decisión con confianza y resultado, para calibrar después

Salida: mandás un audio diciendo "mostrame cómo está el portón" y funciona.

## Fase 3: mover la cámara de la cabaña

La que más usás y la que más justifica el proyecto.

- [ ] PTZ por DVRIP desde el agente
- [ ] Presets con nombre en la base: portón, camino, galpón
- [ ] Guardar la posición actual como preset desde WhatsApp
- [ ] Movimiento relativo: "un poco a la izquierda"
- [ ] Foto automática después de cada movimiento, para ver dónde quedó

Salida: "poné la cámara de la cabaña en el portón" y la mueve y te muestra.

## Fase 4: boyeros

El backend ya existe: [ttofalo/automatizacion-boyeros-backend](https://github.com/ttofalo/automatizacion-boyeros-backend), con FastAPI, WebSockets y los ESP32 del campo andando contra él. La fase es integrarlo, no reescribirlo. Detalle en [PRIOR_ART.md](PRIOR_ART.md).

- [ ] Leer el backend y mapear qué endpoints expone
- [ ] Credencial de servicio para OlivIA, aparte del PIN del frontend
- [ ] Decidir dónde vive el backend: el mismo VPS o donde está hoy
- [ ] Cliente HTTP en el brain contra `/boyeros`
- [ ] Consulta de estado desde WhatsApp
- [ ] Corte y encendido con confirmación obligatoria
- [ ] Alerta cuando un boyero deja de reportar

Salida: preguntás "cómo están los boyeros" y te contesta con el estado de cada uno.

## Fase 5: que te avise sin preguntarle

- [ ] Suscripción a eventos de movimiento del NVR
- [ ] Triage con Jev: avisar ahora, anotar, descartar
- [ ] Alerta con foto adjunta
- [ ] Resumen de la mañana con lo que no ameritó despertarte
- [ ] Modo silencio por horario

Salida: entra alguien de noche y te llega la foto antes de que golpee la puerta.

## Fase 6: memoria y conversación

Acá deja de ser un ejecutor de comandos.

- [ ] Claude con tool use sobre todas las capacidades del agente
- [ ] Contexto por conversación, para que "y ahora la de al lado" tenga sentido
- [ ] Preguntas sobre el pasado: "¿pasó algo anoche en la cabaña?"
- [ ] Búsqueda de grabaciones en el NVR por fecha y hora
- [ ] Permisos por persona: quién puede cortar un boyero y quién solo mirar
- [ ] Responder con audio, no solo texto

Salida: le preguntás algo abierto y te contesta con lo que sabe de la casa.

## Fase 7: que se adelante

Lo que separa un bot de comandos de un asistente.

- [ ] Presencia: quién está en casa, para decidir si una detección importa
- [ ] Rutinas por horario y por evento, sin que nadie las dispare
- [ ] Anomalías: el boyero que consume distinto, la cámara que dejó de reportar
- [ ] Resumen diario en el grupo familiar
- [ ] Más dominios: portón, luces, tanques de agua

## Ideas para después

Sin orden ni compromiso:

- Tanques de agua con sensor de nivel y alerta por nivel bajo
- Portón con apertura desde WhatsApp
- Detección de personas y vehículos en la Pi, para filtrar antes de alertar
- Clima local con estación propia
- Timelapse diario de la cabaña
- Dashboard web para ver todo junto
