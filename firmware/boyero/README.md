# firmware/boyero

Fase 4. Todavía sin código.

Los ESP32 se conectan al broker MQTT del VPS por su cuenta, con TLS y una credencial por dispositivo. No necesitan al agente de la Pi.

## Topics

```
casa/cmd/boyero/<id>/set        {"state": "on"}  o  {"state": "off"}
casa/evt/boyero/<id>/state      {"on": true, "voltaje": 7400, "ts": 1758...}
```

El brain pide confirmación por WhatsApp antes de mandar un `set`. Cortar un alambrado es una acción física.

## Qué relevar antes de escribir esto

- Qué mide cada ESP32 hoy: pulso, voltaje, nada.
- Si tiene relé para cortar o solo reporta.
- Qué firmware corre: Arduino a mano, ESPHome, Tasmota.
- Cómo llega a internet desde el campo.

## Dos caminos

**ESPHome.** Si los ESP32 están vacíos o el firmware actual es descartable, un YAML de veinte líneas resuelve MQTT, OTA y la telemetría. Menos código para mantener.

**Arduino/PlatformIO.** Si ya hay lógica propia que funciona, se le suma `PubSubClient` sobre `WiFiClientSecure` y listo.

## Cuidado con la medición

Un boyero tira pulsos de varios kilovoltios. La medición va con divisor resistivo y optoacoplador, nunca directo al ADC del ESP32. Si el firmware actual ya mide, copiar ese circuito antes de inventar otro.
