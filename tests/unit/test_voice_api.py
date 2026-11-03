"""API tests for the copilot voice transcription endpoint."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.unit.test_run_api import (  # noqa: F401
    client_with_db,
)

__all__ = ["client_with_db"]

from bizora import api
from bizora.main import app
from bizora.providers.muse_voice import VoiceProviderError, VoiceTranscription


def make_wav() -> bytes:
    """Minimal RIFF/WAVE bytes (only the header matters to the route)."""
    return b"RIFF\x24\x00\x00\x00WAVE" + bytes(40)


class FakeVoiceProvider:
    """Scripted stand-in for the Muse voice provider."""

    def __init__(self, result: VoiceTranscription | Exception) -> None:
        self._result = result
        self.seen: list[tuple[bytes, str]] = []

    async def transcribe_wav(self, audio: bytes, **kwargs: Any) -> VoiceTranscription:
        self.seen.append((audio, str(kwargs.get("filename"))))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_transcribe_returns_the_transcript(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _ = client_with_db
    fake = FakeVoiceProvider(
        VoiceTranscription(transcript="tilt the rails", audio_duration_ms=900, session_id="s-1")
    )
    app.dependency_overrides[api.get_voice_provider] = lambda: fake
    try:
        response = client.post(
            "/api/v1/graphs/project-1/graph-1/copilot/transcribe",
            files={"file": ("utterance.wav", make_wav(), "audio/wav")},
        )
    finally:
        app.dependency_overrides.pop(api.get_voice_provider, None)

    assert response.status_code == 200
    assert response.json() == {
        "transcript": "tilt the rails",
        "audio_duration_ms": 900,
        "session_id": "s-1",
    }
    assert len(fake.seen) == 1
    assert fake.seen[0][0] == make_wav()


def test_transcribe_rejects_non_wav_and_oversize_clips(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _ = client_with_db
    fake = FakeVoiceProvider(VoiceTranscription(transcript="never"))
    app.dependency_overrides[api.get_voice_provider] = lambda: fake
    try:
        bad_type = client.post(
            "/api/v1/graphs/project-1/graph-1/copilot/transcribe",
            files={"file": ("clip.webm", b"\x1a\x45\xdf\xa3" + bytes(100), "audio/webm")},
        )
        big = client.post(
            "/api/v1/graphs/project-1/graph-1/copilot/transcribe",
            files={"file": ("big.wav", make_wav() + bytes(9 * 1024 * 1024), "audio/wav")},
        )
    finally:
        app.dependency_overrides.pop(api.get_voice_provider, None)

    assert bad_type.status_code == 422
    assert "WAV" in bad_type.json()["error"]["message"]
    assert big.status_code == 422
    assert "8 MB" in big.json()["error"]["message"]
    assert fake.seen == []


def test_transcribe_maps_provider_failures_to_502(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    client, _ = client_with_db
    fake = FakeVoiceProvider(VoiceProviderError("down"))
    app.dependency_overrides[api.get_voice_provider] = lambda: fake
    try:
        response = client.post(
            "/api/v1/graphs/project-1/graph-1/copilot/transcribe",
            files={"file": ("utterance.wav", make_wav(), "audio/wav")},
        )
    finally:
        app.dependency_overrides.pop(api.get_voice_provider, None)

    assert response.status_code == 502
