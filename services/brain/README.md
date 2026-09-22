# brain

Decide qué hacer con cada mensaje que llega por WhatsApp.

Dos niveles:

1. **Jev** clasifica el mensaje contra el inventario de `config/devices.yaml`. Si la confianza pasa `JEV_CONFIDENCE_THRESHOLD`, ejecuta directo. Tarda menos de medio segundo y cuesta casi nada.
2. **Claude** entra cuando Jev duda, cuando la pregunta es abierta o cuando hay que combinar varias acciones.

Lo importante del nivel 1: las opciones de cada pregunta salen del inventario real, así que Jev no puede devolver una cámara que no existe.

Detalle del diseño en [../../docs/JEV.md](../../docs/JEV.md).
