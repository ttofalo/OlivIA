"""El aviso por Telegram: sin credenciales no llama a la red, y un fallo no explota."""

from __future__ import annotations

from types import SimpleNamespace

from brain.telegram import escuchar, notificar


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


def _fake_get(actualizaciones_por_llamada):
    """Devuelve un `httpx.get` falso que va sirviendo listas de updates."""
    llamadas = iter(actualizaciones_por_llamada)

    def get(url, params, timeout):
        result = next(llamadas, [])
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"result": result})

    return get


def _msg(update_id, chat_id, texto):
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": texto}}


def test_solo_responde_al_chat_autorizado(monkeypatch):
    updates = [_msg(1, 555, "cuánto gastamos?"), _msg(2, 999, "espiando")]
    monkeypatch.setattr("brain.telegram.httpx.get", _fake_get([updates]))
    enviados = []
    monkeypatch.setattr(
        "brain.telegram.httpx.post",
        lambda url, json, timeout: (
            enviados.append(json),
            SimpleNamespace(raise_for_status=lambda: None),
        )[1],
    )

    escuchar("un-token", "555", lambda _texto: "el gasto es X", limite_iteraciones=1)

    assert len(enviados) == 1
    assert enviados[0] == {"chat_id": "555", "text": "el gasto es X"}


def test_si_responder_no_devuelve_nada_no_manda_mensaje(monkeypatch):
    monkeypatch.setattr("brain.telegram.httpx.get", _fake_get([[_msg(1, 555, "hola")]]))
    enviados = []
    monkeypatch.setattr(
        "brain.telegram.httpx.post",
        lambda url, json, timeout: (
            enviados.append(json),
            SimpleNamespace(raise_for_status=lambda: None),
        )[1],
    )

    escuchar("un-token", "555", lambda _texto: None, limite_iteraciones=1)

    assert enviados == []


def test_un_fallo_de_polling_no_corta_el_loop(monkeypatch):
    def get(url, params, timeout):
        raise ConnectionError("sin red")

    monkeypatch.setattr("brain.telegram.httpx.get", get)
    monkeypatch.setattr("brain.telegram.time.sleep", lambda _s: None)

    # No debe explotar, solo loguear y seguir hasta agotar las iteraciones.
    escuchar("un-token", "555", lambda _texto: "no debería llamarse", limite_iteraciones=2)
