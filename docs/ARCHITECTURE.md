# Arquitectura

## El problema de red

El bot corre en un VPS. Las cámaras están en la LAN de casa. Desde la nube no se llega a una IP privada, y abrir puertos en el router para exponer un NVR chino es la peor idea posible: esos equipos aparecen en Shodan a las horas y arrastran vulnerabilidades sin parche.

La solución es invertir la dirección. Un agente en casa abre la conexión hacia el VPS y la mantiene viva. El VPS nunca inicia nada. Esto además esquiva el CGNAT: si tu ISP no te da IP pública, igual funciona.

Los ESP32 hacen lo mismo por su cuenta. Se conectan al broker MQTT del VPS con TLS y publican telemetría.

## Los cuatro componentes

### gateway (VPS, TypeScript)

Baileys es una librería TypeScript, así que este servicio es TS. Su trabajo termina en la mensajería:

- Mantiene la sesión de WhatsApp y persiste las credenciales en disco.
- Filtra por whitelist de números antes de tocar nada.
- Descarga los audios que llegan y los pasa a transcribir.
- Publica cada mensaje entrante en `wsp/in` y consume las respuestas de `wsp/out`.
- Manda fotos, texto y estados.

No decide nada. Si mañana cambiamos a Telegram, se reescribe este servicio y el resto queda igual.

### brain (VPS, Python)

Recibe el mensaje ya normalizado y decide. Dos niveles:

**Nivel 1, Jev.** Clasifica el mensaje contra el inventario real de dispositivos. Devuelve intent, dispositivo y confianza en 70 a 500 ms. No puede inventar una cámara que no existe porque las opciones son las claves de tu `devices.yaml`. Si la confianza pasa el umbral, ejecuta directo y nunca llama al LLM.

**Nivel 2, Claude.** Entra cuando Jev duda, cuando la pregunta es abierta ("¿pasó algo anoche?") o cuando hay que combinar varias acciones. Acá sí hay tool use y contexto de conversación.

El brain traduce la decisión a comandos MQTT y espera el resultado.

### agent (Raspberry en casa, Python)

Lo único que vive en la LAN. Habla tres protocolos con las cámaras:

- **DVRIP, puerto 34567.** El protocolo propietario de XiongMai, lo que usa la app iCSee. Sirve para PTZ, presets y configuración. Lo implementa `python-dvr` de OpenIPC.
- **RTSP, puerto 554.** El stream. Para un snapshot alcanza con pedirle un frame a ffmpeg y cortar.
- **ONVIF, puerto 8899.** Si la cámara lo trae habilitado, es el camino estándar para PTZ y eventos. Muchas XiongMai lo tienen apagado de fábrica y hay que prenderlo desde iCSee.

El agente también consulta el NVR para buscar grabaciones por fecha y hora.

### firmware (ESP32)

Cada boyero reporta estado y acepta comandos por MQTT. Un boyero eléctrico es un actuador físico en el campo, así que los comandos de apagado pasan por confirmación en el brain antes de salir.

## Un mensaje de punta a punta

Tobias manda un audio: "sacame una foto del portón de la cabaña".

1. El gateway recibe el audio, verifica que el número esté en la whitelist y lo descarga.
2. Transcribe. Publica en `wsp/in` el texto junto con el chat de origen.
3. El brain arma el estado y le pregunta a Jev: qué intent, qué cámara, hace falta confirmar.
4. Jev responde `intent=snapshot`, `camara=cabania`, confianza 0.94. Pasa el umbral.
5. El brain publica `casa/cmd/cam/cabania/snapshot` y espera.
6. El agente en la Pi levanta el comando, le pide un frame al RTSP de esa cámara con ffmpeg, lo comprime y lo sube al VPS.
7. El brain publica en `wsp/out` la respuesta con la foto adjunta.
8. El gateway la manda al chat.

Sin LLM en el camino. Latencia dominada por el tiempo que tarda la cámara en dar el primer frame, entre 1 y 3 segundos.

## Topics MQTT

```
wsp/in                                  mensajes entrantes normalizados
wsp/out                                 respuestas a enviar

casa/cmd/cam/<id>/snapshot              pedir foto
casa/cmd/cam/<id>/ptz                   mover: {pan, tilt, zoom} o {preset}
casa/cmd/cam/<id>/preset/save           guardar posición actual como preset
casa/cmd/boyero/<id>/set                {on|off}

casa/evt/cam/<id>/snapshot              resultado con la referencia al archivo
casa/evt/cam/<id>/motion                detección del NVR o la cámara
casa/evt/boyero/<id>/state              estado y medición
casa/evt/agent/heartbeat                el agente vive
```

Cada dispositivo tiene su credencial y sus ACLs. El ESP32 del boyero no puede publicar en topics de cámaras.

## Persistencia

Postgres en el VPS guarda presets con nombre, historial de comandos con quién los pidió, eventos de movimiento y el estado conocido de cada dispositivo. El historial es auditoría: si alguien apagó un boyero a las 3 de la mañana, queda registrado.

Las fotos y clips van al disco del VPS con retención por tiempo, no a la base.

## Por qué dos lenguajes

Baileys es TypeScript y reimplementarlo no tiene sentido. Las librerías de DVRIP, ONVIF y visión son Python. Cada servicio usa lo que ya existe y el bus MQTT los desacopla.
