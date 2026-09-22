# Decisiones

Registro corto de lo decidido y por qué. Si algo cambia, se agrega una entrada nueva en vez de editar la vieja.

## 001: agente local en vez de exponer la LAN

**2026-09-21.** El bot corre en un VPS y las cámaras están en la LAN de casa. Elegimos un agente en la Pi que abre la conexión hacia el VPS.

Alternativas descartadas: port forwarding al NVR (expone equipos con vulnerabilidades sin parche), Tailscale con subnet router (necesita igual un equipo en casa, y si ya hay uno, que corra el agente y hable los protocolos), correr todo en la Pi sin VPS (queda atado a la conexión de casa y al CGNAT).

Ventaja extra: funciona con CGNAT y sin IP pública.

## 002: Baileys con número aparte

**2026-09-21.** Baileys usa la API de WhatsApp Web sin autorización de Meta. Riesgo de ban real. La Cloud API oficial obliga a plantillas aprobadas para iniciar conversación, lo que rompe el caso de alertar a la familia.

Elegimos Baileys sobre un número descartable. El gateway queda aislado del resto para poder cambiar de canal sin tocar la lógica.

## 003: Jev para el nivel 1, Claude para el nivel 2

**2026-09-21.** Los mensajes de casa son repetitivos y la mayoría se resuelve con una clasificación. Jev devuelve decisiones tipadas con confianza calibrada en menos de medio segundo y no puede salirse del inventario.

Un LLM en cada mensaje cuesta más, tarda más y puede alucinar un dispositivo. Claude entra cuando Jev duda o cuando hay que razonar.

Detalle en [JEV.md](JEV.md).

## 004: TypeScript en el gateway, Python en el resto

**2026-09-21.** Baileys es TypeScript. Las librerías de DVRIP, ONVIF y visión son Python. Cada servicio usa el ecosistema donde está lo que necesita, y MQTT los desacopla.

## 005: MQTT como bus

**2026-09-21.** Los dispositivos ya hablan MQTT o lo pueden hablar con poco. Funciona sobre conexiones que se cortan, tiene QoS, ACLs por topic y credenciales por dispositivo. Una API HTTP obligaría a que el VPS inicie conexiones hacia casa, que es lo que estamos evitando.

## 006: OlivIA responde por nombre en los grupos

**2026-09-21.** El bot vive en un grupo con la familia. Si contesta cada mensaje, el grupo queda inservible.

En chat directo responde siempre. En grupo responde cuando la nombran ("olivia, sacá una foto"), cuando la mencionan con arroba o cuando alguien le cita un mensaje suyo. El nombre sale de `WSP_BOT_NAME`, así que si alguien le dice de otra forma se cambia por entorno.
