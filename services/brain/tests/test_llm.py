from types import SimpleNamespace

from brain.config import Inventory, Settings
from brain.llm import FALLBACK_TEXT, NOT_CONFIGURED_TEXT, Assistant


class FakeCompletions:
    def __init__(self, message=None, error=None):
        self.message = message
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(choices=[SimpleNamespace(message=self.message)])


def make_client(message=None, error=None):
    completions = FakeCompletions(message=message, error=error)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def make_message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def make_tool(name, arguments):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


def settings(api_key="secreto"):
    return Settings(
        typesafe_api_key="jev",
        jev_model="jev-latest",
        jev_threshold=0.8,
        llm_base_url="https://api.deepseek.com",
        llm_api_key=api_key,
        llm_model="deepseek-flash",
        llm_timeout=20,
        transcribe_backend="local",
        transcribe_model="base",
        transcribe_api_base_url="",
        transcribe_api_key="",
        mqtt_host="localhost",
        mqtt_port=8883,
        mqtt_tls=True,
        mqtt_user="brain",
        mqtt_pass="secreto",
        mqtt_ca="",
        devices_path="devices.yaml",
        media_dir="/media",
        costs_path=None,
    )


def inventory():
    return Inventory(
        camaras={
            "cabania": {
                "descripcion": "Mira al portón",
                "presets": {"porton": 1, "camino": 2},
            }
        },
        boyeros={"fondo": {"descripcion": "Potrero de atrás"}},
        nvr={},
    )


def test_texto_simple_sin_tools():
    client, completions = make_client(make_message(content="Todo tranquilo."))

    reply = Assistant(settings(), inventory(), client=client).answer("¿Cómo viene todo?")

    assert reply.text == "Todo tranquilo."
    assert reply.actions == []
    assert completions.calls[0]["tool_choice"] == "auto"


def test_sacar_foto_de_camara_valida():
    tool = make_tool("sacar_foto", '{"camara": "cabania"}')
    client, _ = make_client(make_message(tool_calls=[tool]))

    reply = Assistant(settings(), inventory(), client=client).answer("Mostrame el portón")

    assert reply.text is None
    assert reply.actions == [{"kind": "snapshot", "camara": "cabania", "preset": None}]


def test_descarta_camara_inventada_y_conserva_texto():
    tool = make_tool("sacar_foto", '{"camara": "sotano"}')
    client, _ = make_client(make_message(content="No encuentro esa cámara.", tool_calls=[tool]))

    reply = Assistant(settings(), inventory(), client=client).answer("Foto del sótano")

    assert reply.text == "No encuentro esa cámara."
    assert reply.actions == []


def test_error_del_proveedor_devuelve_fallback():
    client, _ = make_client(error=TimeoutError("tardó demasiado"))

    reply = Assistant(settings(), inventory(), client=client).answer("Hola")

    assert reply.text == FALLBACK_TEXT
    assert reply.actions == []


def test_sin_api_key_avisa_que_no_esta_configurado():
    reply = Assistant(settings(api_key=""), inventory()).answer("Hola")

    assert reply.text == NOT_CONFIGURED_TEXT
    assert reply.actions == []
