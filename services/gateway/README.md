# gateway

La capa de WhatsApp. Recibe mensajes, filtra por whitelist, publica en MQTT y manda las respuestas.

No decide nada: si mañana cambiamos a Telegram, se reescribe este servicio y el resto queda igual.

## Primer arranque

La primera vez imprime un QR en los logs. Escanearlo desde el WhatsApp del número del bot, en Dispositivos vinculados. Las credenciales quedan en `baileys_auth/` y no hace falta repetirlo.

```bash
docker compose logs -f gateway
```

## Cuidado con Baileys

Es la API de WhatsApp Web sin autorización de Meta. Reglas para no comerse un ban:

- Número aparte, nunca el personal.
- No responder a números fuera de la whitelist.
- Nada de envíos masivos.
- La versión 7.x todavía está en release candidate. Quedamos en la 6.7.x estable hasta que salga.
