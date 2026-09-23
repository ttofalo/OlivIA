# Jev: la capa de decisión rápida

## Qué es

Jev es el primer modelo "System One" de [TypeSafe AI](https://typesafe.ai/blog/introducing-system-one-models-and-jev), publicado en septiembre de 2026. En vez de generar texto token por token, devuelve valores tipados con probabilidades calibradas. Le pasás estado y preguntas, te devuelve decisiones.

Los números que importan acá:

| | |
|---|---|
| Latencia | 70 a 500 ms punta a punta |
| Precio | USD 0.042 por millón de tokens de entrada, salida gratis |
| Ventana de contexto | 32.000 tokens |
| Límite de opciones | 255 por pregunta |
| Rate limit | 1.200 requests por minuto |

No puede generar strings libres y no sirve para conversar. Tampoco puede romper el schema ni devolver una opción que no declaraste, que es la propiedad que lo hace útil acá.

## Por qué encaja en este proyecto

Un LLM que enruta comandos de casa tiene dos problemas. Cuesta y tarda en cada mensaje trivial, y puede alucinar un dispositivo que no existe. Si le pedís "foto del galpón" y no tenés cámara en el galpón, un LLM con tool use puede inventar un ID de cámara y el agente va a fallar en la LAN.

Con Jev las opciones son las claves de `config/devices.yaml`. La respuesta pertenece al inventario real por construcción. Y la confianza calibrada da un umbral para decidir cuándo escalar en vez de adivinar.

## Los tres tipos de pregunta

```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

client = TypeSafeClient()  # lee TYPESAFE_API_KEY del entorno

response = client.system_one(
    state={"mensaje": "sacame una foto del portón de la cabaña"},
    questions={
        "intent": Choice(
            instructions="Qué está pidiendo el usuario",
            criteria={
                "snapshot": "Ver una cámara ahora, pedir una foto o imagen",
                "ptz": "Mover, girar o apuntar una cámara a otro lado",
                "estado": "Preguntar cómo está algo sin pedir acción",
                "boyero": "Prender, apagar o consultar un boyero eléctrico",
                "otro": "Cualquier otra cosa, charla o pregunta abierta",
            },
        ),
        "camara": Choice(
            instructions="A qué cámara se refiere",
            criteria={  # generado desde devices.yaml
                "cabania": "Cámara de la cabaña, apunta al portón y al camino",
                "frente": "Cámara del frente de la casa",
                "patio": "Cámara del patio",
                "galpon": "Cámara del galpón",
                "ninguna": "El mensaje no menciona ninguna cámara",
            },
        ),
        "urgencia": Score(
            instructions="Qué tan urgente suena",
            criteria=["Curiosidad, puede esperar", "Quiere ver ahora", "Algo está pasando"],
        ),
        "es_accion_fisica": Noul(
            instructions="El pedido implica accionar algo en el mundo real, como cortar un boyero",
        ),
    },
)

response.answers["intent"].choice           # "snapshot"
response.answers["intent"].confidence       # 0.94
response.answers["camara"].probabilities    # {"cabania": 0.91, "frente": 0.04, ...}
response.answers["es_accion_fisica"].noul   # 0.02
```

`Choice` devuelve una opción con confianza y probabilidades por opción. `Score` ubica algo en una escala ordenada de 2 a 10 niveles y puede caer entre dos. `Noul` devuelve una probabilidad de 0 a 1.

## Dónde lo usamos

**Router de intents.** El caso principal. Cada mensaje de WhatsApp pasa por Jev antes que por cualquier otra cosa. Umbral en 0.80 para ejecutar directo, y por debajo va al LLM de nivel 2.

**Triage de alertas.** El NVR detecta movimiento a cualquier hora y la mayoría es un perro. Jev recibe la hora, la cámara, si hay alguien en casa y el historial reciente, y decide entre avisar ahora, anotar para el resumen de la mañana o descartar. Con 40 eventos por noche, un LLM en ese loop es plata tirada.

**Guarda de acciones físicas.** Antes de cortar un boyero, `es_accion_fisica` y la confianza deciden si el bot ejecuta o pide confirmación por WhatsApp.

**Desambiguación de audios.** Las transcripciones vienen sucias. Jev con las opciones acotadas al inventario aguanta mejor un "la cámara de la cabañita" que un matcher de strings.

## Dónde no

Redactar la respuesta al usuario, resumir qué pasó anoche, contestar preguntas abiertas, cualquier cosa que necesite memoria de la conversación. Eso es el LLM de nivel 2 (DeepSeek por defecto, ver [DECISIONS.md](DECISIONS.md), decisión 010).

## Costo

Un router de intents con el inventario completo pesa unos 300 tokens de entrada. Mil mensajes por mes son 300.000 tokens: USD 0.013. La salida no se cobra. El gasto del proyecto va a estar en el LLM de nivel 2 y en almacenamiento, no acá.

## Calibración

La confianza es calibrada, así que el umbral se puede ajustar con datos. El plan: registrar cada decisión de Jev con su confianza y el resultado real, y después mover el umbral con evidencia en vez de a ojo. Guardar también el campo `model` de la respuesta (`jev-1.13.0` y sucesores), porque un umbral afinado contra una versión no necesariamente vale para la siguiente.
