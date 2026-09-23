from __future__ import annotations

import sys
import types
import urllib.request
from pathlib import Path

import pytest

from brain import transcribe as transcribe_module
from brain.transcribe import TranscribeError, transcribe


def test_local_carga_el_modelo_una_sola_vez(monkeypatch: pytest.MonkeyPatch) -> None:
    cargas: list[tuple[str, str, str]] = []

    class Segment:
        def __init__(self, text: str) -> None:
            self.text = text

    class WhisperModel:
        def __init__(self, model: str, device: str, compute_type: str) -> None:
            cargas.append((model, device, compute_type))

        def transcribe(self, path: str, **kwargs: object):
            assert path.endswith("audio.ogg")
            assert kwargs == {"language": "es", "vad_filter": True, "beam_size": 1}
            return [Segment("  hola "), Segment(" mundo  ")], types.SimpleNamespace(duration=1.5)

    fake_module = types.ModuleType("faster_whisper")
    fake_module.WhisperModel = WhisperModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    transcribe_module._models.clear()

    path = Path("audio.ogg")
    assert transcribe(path, "local", "small") == "hola mundo"
    assert transcribe(path, "local", "small") == "hola mundo"
    assert cargas == [("small", "cpu", "int8")]


def test_api_manda_multipart_y_devuelve_texto(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"opus")

    def fake_send(request: urllib.request.Request) -> bytes:
        assert request.full_url == "https://api.example/v1/audio/transcriptions"
        assert request.get_header("Authorization") == "Bearer secreta"
        assert request.get_method() == "POST"
        assert request.data is not None
        assert b'name="model"' in request.data
        assert b"whisper-large-v3-turbo" in request.data
        assert b'name="language"' in request.data
        assert b"opus" in request.data
        return b'{"text": "  buen dia  "}'

    monkeypatch.setattr(transcribe_module, "_send_request", fake_send)

    assert (
        transcribe(
            audio,
            "api",
            "whisper-large-v3-turbo",
            api_base_url="https://api.example/v1/",
            api_key="secreta",
        )
        == "buen dia"
    )


def test_error_de_api_se_normaliza(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"opus")

    def fail(_request: urllib.request.Request) -> bytes:
        raise OSError("sin red")

    monkeypatch.setattr(transcribe_module, "_send_request", fail)

    with pytest.raises(TranscribeError, match="No se pudo transcribir el audio"):
        transcribe(
            audio,
            "api",
            "whisper-large-v3-turbo",
            api_base_url="https://api.example/v1",
            api_key="secreta",
        )
