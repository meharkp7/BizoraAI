"""Muse Voice Transcribe through the Meta Model API.

The provider posts WAV audio to ``POST {base_url}/asr/transcribe`` as
multipart form data: a ``request`` JSON part naming the model, the mode,
and the audio encoding, plus the ``audio`` file part. Authentication is
a Bearer [REDACTED] ``MUSE_API_KEY`` environment variable. The response
carries ``transcript``, ``audioDurationMs``, and ``sessionId``.

Only whole utterances are transcribed here: the browser captures and
endpoints speech, encodes one mono 16-bit WAV clip per utterance, and
uploads it. Live streaming stays on the realtime WebSocket, which this
client deliberately does not speak.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from bizora.providers.muse import DEFAULT_BASE_URL, MUSE_API_KEY_ENV_VAR

DEFAULT_VOICE_MODEL = "muse-voice-transcribe-1.0"

#: PUSH_TO_TALK: the caller delimits the turn by uploading a whole clip.
DEFAULT_VOICE_MODE = "PUSH_TO_TALK"

#: WAV container: the API reads no other upload encoding.
VOICE_AUDIO_ENCODING = "WAV"

#: Upload cap: the server allows 32 MB / 10 minutes, but utterances are
#: seconds long — anything larger is a wrong file, not a turn.
MAX_VOICE_BYTES = 8 * 1024 * 1024

#: RIFF header plus the WAVE marker: enough to reject non-WAV uploads
#: before the bytes leave the building.
_WAV_PREFIX = 12


class VoiceProviderError(RuntimeError):
    """Raised when the voice provider cannot return a transcript."""


@dataclass(frozen=True)
class VoiceTranscription:
    """One transcribed utterance."""

    transcript: str
    audio_duration_ms: int | None = None
    session_id: str | None = None


def is_wav_audio(data: bytes) -> bool:
    """Whether bytes start with a RIFF/WAVE header."""
    return len(data) >= _WAV_PREFIX and data[:4] == b"RIFF" and data[8:_WAV_PREFIX] == b"WAVE"


class MuseVoiceProvider:
    """Transcribe utterances using Muse Voice Transcribe."""

    provider_name = "muse-voice"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = DEFAULT_VOICE_MODEL,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.getenv(MUSE_API_KEY_ENV_VAR)
        if resolved_key is None or not resolved_key.strip():
            raise ValueError(
                "A Muse API key is required: pass api_key or set "
                f"{MUSE_API_KEY_ENV_VAR} in the environment."
            )
        if not model_name.strip():
            raise ValueError("Muse voice model name must not be empty.")
        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        self._api_key = resolved_key
        self._model_name = model_name
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._client = client

    async def transcribe_wav(
        self,
        audio: bytes,
        *,
        filename: str = "utterance.wav",
        language_bias: Sequence[str] | None = None,
    ) -> VoiceTranscription:
        """Transcribe one mono WAV clip, returning its transcript."""
        if not audio:
            raise VoiceProviderError("There is no audio to transcribe.")
        if len(audio) > MAX_VOICE_BYTES:
            raise VoiceProviderError(
                f"The clip is {len(audio) / 1024 / 1024:.1f} MB; "
                f"the limit is {MAX_VOICE_BYTES // 1024 // 1024} MB."
            )
        if not is_wav_audio(audio):
            raise VoiceProviderError("The clip must be WAV audio.")

        request_part: dict[str, Any] = {
            "mode": DEFAULT_VOICE_MODE,
            "model": self._model_name,
            "audioEncoding": VOICE_AUDIO_ENCODING,
        }
        if language_bias:
            request_part["languageBias"] = list(language_bias)
        try:
            response = await self._post(
                files={
                    "request": (None, json.dumps(request_part), "application/json"),
                    "audio": (filename, audio, "audio/wav"),
                }
            )
        except VoiceProviderError:
            raise
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise VoiceProviderError("Muse returned an unreadable response.") from exc
        transcript = data.get("transcript")
        if not isinstance(transcript, str):
            raise VoiceProviderError("Muse returned no transcript.")
        duration = data.get("audioDurationMs")
        session_id = data.get("sessionId")
        return VoiceTranscription(
            transcript=transcript,
            audio_duration_ms=duration if isinstance(duration, int) else None,
            session_id=session_id if isinstance(session_id, str) else None,
        )

    async def _post(
        self, *, files: dict[str, tuple[str | None, Any] | tuple[str | None, Any, str]]
    ) -> httpx.Response:
        """POST one multipart payload to the transcribe endpoint."""
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}/asr/transcribe",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files=files,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/asr/transcribe",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        files=files,
                    )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            hint = {
                400: "audio longer than the 10-minute cap, or a malformed request",
                401: "the credential was not accepted",
                404: "endpoint not found",
                413: "body over 32 MB",
                429: "rate limited; back off and retry",
                500: "the server exceeded its processing budget",
            }.get(exc.response.status_code, "unexpected response")
            raise VoiceProviderError(
                f"Muse returned HTTP {exc.response.status_code} ({hint}): {exc.response.text[:300]}"
            ) from exc
        except httpx.RequestError as exc:
            raise VoiceProviderError("Could not connect to the Muse API.") from exc
        return response
