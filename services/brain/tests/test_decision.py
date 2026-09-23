import pytest

from brain.router import Decision


@pytest.fixture
def decision_base() -> Decision:
    return Decision(
        intent="otro",
        intent_confidence=0.9,
        camara=None,
        camara_confidence=0.0,
        boyero=None,
        urgencia=0.0,
        es_accion_fisica=0.0,
        model="jev-prueba",
        raw={},
    )


def test_intent_bajo_umbral_no_alcanza(decision_base: Decision) -> None:
    decision_base.intent_confidence = 0.79
    assert not decision_base.confident_enough(0.8)


def test_snapshot_con_camara_dudosa_no_alcanza(decision_base: Decision) -> None:
    decision_base.intent = "snapshot"
    decision_base.camara = "entrada"
    decision_base.camara_confidence = 0.79
    assert not decision_base.confident_enough(0.8)


def test_boyero_estado_sin_boyero_no_alcanza(decision_base: Decision) -> None:
    decision_base.intent = "boyero_estado"
    assert not decision_base.confident_enough(0.8)


def test_otro_con_intent_alto_alcanza(decision_base: Decision) -> None:
    assert decision_base.confident_enough(0.8)


def test_boyero_set_siempre_pide_confirmacion(decision_base: Decision) -> None:
    decision_base.intent = "boyero_set"
    assert decision_base.needs_confirmation()


def test_accion_fisica_mayor_a_medio_pide_confirmacion(decision_base: Decision) -> None:
    decision_base.es_accion_fisica = 0.51
    assert decision_base.needs_confirmation()
