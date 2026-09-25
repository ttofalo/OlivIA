"""Transcripción de los audios que baja el gateway."""

from __future__ import annotations

import json
import time
import urllib.request
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

import structlog

log = structlog.get_logger()


class TranscribeError(RuntimeError):
    """Error esperado al transcribir un audio."""


_models: dict[str, Any] = {}
_models_lock = Lock()


def _local_model(model: str) -> Any:
    with _models_lock:
        if model not in _models:
            # Es opcional: el brain se puede importar sin instalar faster-whisper.
            from faster_whisper import WhisperModel

            _models[model] = WhisperModel(model, device="cpu", compute_type="int8")
        return _models[model]


def _transcribe_local(
    path: Path, model: str, language: str, prompt: str = ""
) -> tuple[str, float | None]:
    whisper = _local_model(model)
    segments, info = whisper.transcribe(
        str(path),
        language=language,
        initial_prompt=prompt or None,
        vad_filter=True,
        beam_size=1,
    )
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    return text.strip(), getattr(info, "duration", None)


def _multipart_request(
    path: Path, model: str, language: str, api_base_url: str, api_key: str, prompt: str = ""
) -> urllib.request.Request:
    boundary = f"----olivia-{uuid.uuid4().hex}"
    campos = (
        [
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="prompt"\r\n\r\n{prompt}\r\n'
            ).encode()
        ]
        if prompt
        else []
    )
    parts = campos + [
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{model}\r\n'
        ).encode(),
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\n{language}\r\n'
        ).encode(),
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: audio/ogg\r\n\r\n"
        ).encode()
        + path.read_bytes()
        + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return urllib.request.Request(
        f"{api_base_url.rstrip('/')}/audio/transcriptions",
        data=b"".join(parts),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            # Groq está detrás de Cloudflare, que rechaza con 403 el
            # User-Agent por defecto de urllib ("Python-urllib").
            "User-Agent": "olivia-brain/1.0",
        },
        method="POST",
    )


def _send_request(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _transcribe_api(
    path: Path, model: str, language: str, api_base_url: str, api_key: str, prompt: str = ""
) -> tuple[str, float | None]:
    if not api_base_url:
        raise TranscribeError("Falta la URL de la API de transcripción")
    if not api_key:
        raise TranscribeError("Falta la clave de la API de transcripción")

    request = _multipart_request(path, model, language, api_base_url, api_key, prompt)
    payload = json.loads(_send_request(request))
    text = payload.get("text")
    if not isinstance(text, str):
        raise TranscribeError("La API no devolvió una transcripción")
    duration = payload.get("duration")
    return text.strip(), duration if isinstance(duration, (int, float)) else None


def transcribe(
    path: Path,
    backend: str,
    model: str,
    api_base_url: str = "",
    api_key: str = "",
    language: str = "es",
    prompt: str = "",
) -> str:
    """Transcribe un audio con faster-whisper local o una API compatible.

    `prompt` le da vocabulario a Whisper (los nombres de las cámaras) para
    que no escriba "cabaña" como "campaña".
    """
    started = time.monotonic()
    duration: float | None = None

    try:
        if backend == "local":
            text, duration = _transcribe_local(path, model, language, prompt)
        elif backend == "api":
            text, duration = _transcribe_api(path, model, language, api_base_url, api_key, prompt)
        else:
            raise TranscribeError(f"Backend de transcripción inválido: {backend}")
    except TranscribeError:
        raise
    except Exception as exc:
        raise TranscribeError("No se pudo transcribir el audio") from exc

    fields: dict[str, Any] = {
        "backend": backend,
        "model": model,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }
    if duration is not None:
        fields["duration_seconds"] = round(duration, 3)
    log.info("audio transcripto", **fields)
    return text
