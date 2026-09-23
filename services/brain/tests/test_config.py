from pathlib import Path

from brain.config import Inventory


def test_carga_inventario_desde_yaml(tmp_path: Path) -> None:
    archivo = tmp_path / "devices.yaml"
    archivo.write_text(
        """
camaras:
  entrada:
    nombre: Entrada
boyeros:
  norte:
    nombre: Norte
nvr:
  principal:
    ip: 192.0.2.10
""".strip(),
        encoding="utf-8",
    )

    inventario = Inventory.load(archivo)

    assert inventario.camaras == {"entrada": {"nombre": "Entrada"}}
    assert inventario.boyeros == {"norte": {"nombre": "Norte"}}
    assert inventario.nvr == {"principal": {"ip": "192.0.2.10"}}


def test_criteria_de_camara_prioriza_descripcion_nombre_e_id() -> None:
    inventario = Inventory(
        camaras={
            "entrada": {"descripcion": "Puerta principal", "nombre": "Entrada"},
            "patio": {"nombre": "Patio"},
            "galpon": {},
        },
        boyeros={},
        nvr={},
    )

    assert inventario.camara_criteria() == {
        "entrada": "Puerta principal",
        "patio": "Patio",
        "galpon": "galpon",
        "ninguna": "El mensaje no menciona ninguna cámara",
    }


def test_criteria_de_boyero_incluye_ninguno(inventario: Inventory) -> None:
    assert inventario.boyero_criteria()["ninguno"] == "El mensaje no menciona ningún boyero"


def test_camaras_con_ptz(inventario: Inventory) -> None:
    assert inventario.camaras_con_ptz() == ["entrada"]
