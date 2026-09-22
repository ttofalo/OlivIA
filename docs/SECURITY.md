# Seguridad

Esto controla las cámaras y los cercos eléctricos de la casa de tu familia. Un bug acá no es un 500 en un endpoint.

## Principios

**Nada de puertos abiertos en el router de casa.** Toda conexión sale desde adentro hacia el VPS. Si algún día aparece la tentación de hacer port forwarding al NVR para "probar rápido", no. Los NVR XiongMai tienen historial de vulnerabilidades sin parche y se indexan en Shodan en horas.

**Whitelist de números, no blacklist.** El gateway descarta cualquier mensaje de un número que no esté en la lista, antes de procesar nada. Un desconocido que escriba al número del bot no debe llegar ni al router de intents.

**Credencial por dispositivo con ACLs.** Cada cámara, cada ESP32 y el agente tienen su usuario de MQTT y solo pueden publicar y suscribirse a sus propios topics. Si alguien se hace de un ESP32 del campo, no puede mover cámaras.

**Confirmación para acciones físicas.** Cortar un boyero pide confirmación explícita por WhatsApp. Jev marca la acción como física y el brain no ejecuta sin el sí.

**Auditoría de todo.** Cada comando queda en postgres con quién lo pidió, cuándo, qué decidió Jev y qué pasó. Si un boyero aparece apagado, hay registro.

## Riesgos concretos

| Riesgo | Mitigación |
|---|---|
| Ban de la cuenta de WhatsApp | Número aparte y descartable. Sin envíos masivos ni respuestas a desconocidos |
| Alguien se mete al VPS y llega a las cámaras | Claves SSH sin password, firewall que solo deja 22 y 8883, fail2ban, sin panel web expuesto |
| Credenciales en el repo | Todo por variables de entorno. `.env` y `config/devices.yaml` están en `.gitignore` |
| Fotos de la casa en el disco del VPS | Retención por tiempo y borrado automático. Disco cifrado si el proveedor lo permite |
| Prompt injection por WhatsApp | Jev no puede devolver algo fuera del enum, así que el nivel 1 es inmune. El nivel 2 con Claude valida los parámetros contra el inventario antes de ejecutar |
| Un familiar corta un boyero por accidente | Confirmación obligatoria y permisos por persona en la fase 6 |
| El agente de casa queda expuesto | Sin puertos de escucha. Solo cliente MQTT saliente |

## Antes de la fase 1

- [ ] Cambiar las contraseñas de fábrica de las cámaras y el NVR
- [ ] Sacar las cámaras de internet si alguna está expuesta hoy (P2P de iCSee cuenta)
- [ ] Firewall del VPS con lo mínimo abierto
- [ ] Certificado TLS del broker MQTT
- [ ] Confirmar que `.gitignore` cubre credenciales antes del primer push
