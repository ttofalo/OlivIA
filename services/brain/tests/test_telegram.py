"""El aviso por Telegram: sin credenciales no llama a la red, y un fallo no explota."""

from __future__ import annotations

from types import SimpleNamespace

from brain.telegram import notificar


def test_sin_token_no_llama_a_la_red(monkeypatch):
    def explota(*_a, **_k):
        raise AssertionError("no debería llamar a httpx.post sin token")

    monkeypatch.setattr("brain.telegram.httpx.post", explota)

    assert notificar("hola", "", "123") is False
    assert notificar("hola", "un-token", "") is False


def test_manda_el_mensaje_al_chat_correcto(monkeypatch):
    llamadas = []

    def fake_post(url, json, timeout):
        llamadas.append((url, json, timeout))
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr("brain.telegram.httpx.post", fake_post)

    assert notificar("se cayó la sesión", "un-token", "555") is True
    assert len(llamadas) == 1
    url, payload, _ = llamadas[0]
    assert url == "https://api.telegram.org/botun-token/sendMessage"
    assert payload == {"chat_id": "555", "text": "se cayó la sesión"}


def test_si_falla_el_envio_devuelve_false_sin_explotar(monkeypatch):
    def falla(*_a, **_k):
        raise ConnectionError("sin red")

    monkeypatch.setattr("brain.telegram.httpx.post", falla)

    assert notificar("hola", "un-token", "555") is False
