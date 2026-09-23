"""Tokens y USD por llamada: tarifas pico y fuera de pico, registro y resumen."""

from datetime import UTC, datetime
from types import SimpleNamespace

from brain import costos
from brain.costos import Registro, costo_usd, es_pico


def test_pico_solo_entre_semana_en_las_horas_de_deepseek():
    assert es_pico(datetime(2026, 9, 23, 7, 0, tzinfo=UTC))  # miércoles 07 UTC
    assert not es_pico(datetime(2026, 9, 23, 15, 0, tzinfo=UTC))  # miércoles 15 UTC
    assert not es_pico(datetime(2026, 9, 26, 7, 0, tzinfo=UTC))  # sábado


def test_costo_v4_pro_fuera_de_pico_y_en_pico():
    fuera = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)
    pico = datetime(2026, 9, 23, 7, 0, tzinfo=UTC)
    # 1000 de entrada sin caché y 100 de salida.
    assert costo_usd("deepseek", "deepseek-v4-pro", 1000, 100, cuando=fuera) == 0.000858
    assert costo_usd("deepseek", "deepseek-v4-pro", 1000, 100, cuando=pico) == 0.001716


def test_cache_se_cobra_a_la_tarifa_de_cache():
    fuera = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)
    con_cache = costo_usd("deepseek", "deepseek-flash", 1000, 0, cache=1000, cuando=fuera)
    sin_cache = costo_usd("deepseek", "deepseek-flash", 1000, 0, cuando=fuera)
    assert con_cache == 0.000003
    assert sin_cache == 0.00015


def test_jev_cobra_entrada_y_la_salida_es_gratis():
    assert costo_usd("jev", "jev-1", 1_000_000, 500) == 0.042


def test_modelo_desconocido_vale_cero():
    assert costo_usd("deepseek", "otro-modelo", 1000, 1000) == 0.0


def test_registro_anota_y_resume(tmp_path):
    reg = Registro(tmp_path / "costos.jsonl")
    reg.anotar("jev", "jev-1", SimpleNamespace(input_tokens=300, output_tokens=10), "router")
    reg.anotar(
        "deepseek",
        "deepseek-v4-pro",
        SimpleNamespace(prompt_tokens=1500, completion_tokens=40, prompt_cache_hit_tokens=1200),
        "chat",
    )

    resumen = reg.resumen()
    assert resumen["jev"]["llamadas"] == 1
    assert resumen["jev"]["entrada"] == 300
    assert resumen["deepseek"]["entrada"] == 1500
    assert resumen["deepseek"]["salida"] == 40
    assert resumen["deepseek"]["usd"] > 0
    texto = reg.texto()
    assert texto.startswith("Hoy: ")
    assert "Jev 1 llamada (310 tokens, USD 0.0000)" in texto
    assert "DeepSeek 1 llamada (1.5k tokens, USD 0.0003)" in texto
    assert "total USD 0.0003." in texto
    assert "En el mes" not in texto  # hoy y el mes coinciden: no se repite


def test_registro_sin_usage_no_rompe(tmp_path):
    reg = Registro(tmp_path / "costos.jsonl")
    assert reg.anotar("deepseek", "deepseek-flash", None, "vision") == 0.0
    assert reg.resumen()["deepseek"]["llamadas"] == 1


def test_sin_archivo_el_resumen_dice_nada(tmp_path):
    assert Registro(None).texto() == "Hoy no gastamos nada. En el mes van USD 0.0000."


def test_saldo_sin_api_key_es_none():
    assert costos.saldo_deepseek("https://api.deepseek.com", "") is None
