"""El reporte diario: arma el mensaje con el gasto y el saldo, y lo manda por Telegram."""

from __future__ import annotations

import brain.reporte_diario as reporte_module


def _setear_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "jev")
    monkeypatch.setenv("MQTT_HOST", "localhost")
    monkeypatch.setenv("MQTT_USER_BRAIN", "brain")
    monkeypatch.setenv("MQTT_PASS_BRAIN", "secreto")
    monkeypatch.setenv("COSTS_PATH", str(tmp_path / "costos.jsonl"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "un-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "555")


def test_arma_el_mensaje_con_gasto_y_saldo_y_lo_manda(monkeypatch, tmp_path):
    _setear_env(monkeypatch, tmp_path)
    monkeypatch.setattr(reporte_module.costos, "resumen_texto", lambda: "Hoy: nada gastado.")
    monkeypatch.setattr(reporte_module.costos, "saldo_deepseek", lambda base_url, api_key: "1.50")
    enviados = []
    monkeypatch.setattr(
        reporte_module,
        "notificar",
        lambda texto, token, chat_id: enviados.append((texto, token, chat_id)) or True,
    )

    reporte_module.main()

    assert len(enviados) == 1
    texto, token, chat_id = enviados[0]
    assert texto == "Gasto de hoy en OlivIA. Hoy: nada gastado. En DeepSeek quedan USD 1.50."
    assert token == "un-token"
    assert chat_id == "555"


def test_sin_saldo_manda_solo_el_gasto(monkeypatch, tmp_path):
    _setear_env(monkeypatch, tmp_path)
    monkeypatch.setattr(reporte_module.costos, "resumen_texto", lambda: "Hoy: nada gastado.")
    monkeypatch.setattr(reporte_module.costos, "saldo_deepseek", lambda base_url, api_key: None)
    enviados = []
    monkeypatch.setattr(
        reporte_module,
        "notificar",
        lambda texto, token, chat_id: enviados.append(texto) or True,
    )

    reporte_module.main()

    assert enviados == ["Gasto de hoy en OlivIA. Hoy: nada gastado."]
