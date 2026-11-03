"""Tests for the Muse Voice Transcribe provider (all API traffic is faked)."""

import asyncio
import json

import httpx
import pytest

from bizora.providers.muse_voice import (
    DEFAULT_VOICE_MODEL,
    MAX_VOICE_BYTES,
    MuseVoiceProvider,
    VoiceProviderError,
    is_wav_audio,
)

FAKE_API_KEY = "test-muse-key"


def make_wav(*, body: bytes = b"\x00\x01" * 8000) -> bytes:
    """Minimal RIFF/WAVE bytes (only the header matters to the client)."""
    size = (36 + len(body)).to_bytes(4, "little")
    return (
        b"RIFF"
        + size
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + bytes(16)
        + b"data"
        + len(body).to_bytes(4, "little")
        + body
    )


def make_provider(handler: object) -> MuseVoiceProvider:
    assert callable(handler)
    return MuseVoiceProvider(
        api_key=FAKE_API_KEY,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
    )


def request_part_of(request: httpx.Request) -> object:
    """Parse the multipart ``request`` JSON part of a fake request."""
    body = request.read().decode("latin1")
    assert 'name="audio"; filename="utterance.wav"' in body
    blob = body.split('name="request"', 1)[1].split("\r\n\r\n", 1)[1]
    return json.loads(blob.split("\r\n--", 1)[0])


def test_wav_detection_reads_the_riff_header() -> None:
    assert is_wav_audio(make_wav())
    assert not is_wav_audio(b"")
    assert not is_wav_audio(b"RIFF")
    assert not is_wav_audio(b"RIFF\x00\x00\x00\x00OGG ")
    assert not is_wav_audio(b"\x1a\x45\xdf\xa3" + bytes(40))


def test_missing_key_and_bad_config_fail_fast() -> None:
    with pytest.raises(ValueError, match="MUSE_API_KEY"):
        MuseVoiceProvider(api_key="")
    with pytest.raises(ValueError, match="model name"):
        MuseVoiceProvider(api_key=FAKE_API_KEY, model_name="  ")
    with pytest.raises(ValueError, match="Timeout"):
        MuseVoiceProvider(api_key=FAKE_API_KEY, timeout=0)


def test_transcribe_posts_multipart_and_reads_the_transcript() -> None:
    seen: dict[str, object] = {}

    def fake_handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["request_part"] = request_part_of(request)
        return httpx.Response(
            200,
            json={
                "sessionId": "session-1",
                "transcript": "tilt the supply rails",
                "audioDurationMs": 1800,
            },
        )

    async def run_test() -> None:
        result = await make_provider(fake_handler).transcribe_wav(make_wav())

        assert seen["url"] == "https://api.meta.ai/v1/asr/transcribe"
        assert seen["auth"] == f"Bearer {FAKE_API_KEY}"
        assert seen["request_part"] == {
            "mode": "PUSH_TO_TALK",
            "model": DEFAULT_VOICE_MODEL,
            "audioEncoding": "WAV",
        }
        assert result.transcript == "tilt the supply rails"
        assert result.audio_duration_ms == 1800
        assert result.session_id == "session-1"

    asyncio.run(run_test())


def test_transcribe_tolerates_missing_optional_fields() -> None:
    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"transcript": "hello"})

    async def run_test() -> None:
        result = await make_provider(fake_handler).transcribe_wav(make_wav())

        assert result.transcript == "hello"
        assert result.audio_duration_ms is None
        assert result.session_id is None

    asyncio.run(run_test())


def test_transcribe_sends_language_bias_when_given() -> None:
    seen: dict[str, object] = {}

    def fake_handler(request: httpx.Request) -> httpx.Response:
        seen["request_part"] = request_part_of(request)
        return httpx.Response(200, json={"transcript": "x"})

    async def run_test() -> None:
        await make_provider(fake_handler).transcribe_wav(make_wav(), language_bias=["en"])

        part = seen["request_part"]
        assert isinstance(part, dict)
        assert part["languageBias"] == ["en"]

    asyncio.run(run_test())


def test_transcribe_rejects_bad_clips_before_posting() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be posted")

    async def run_test() -> None:
        provider = make_provider(boom)
        with pytest.raises(VoiceProviderError, match="no audio"):
            await provider.transcribe_wav(b"")
        with pytest.raises(VoiceProviderError, match="must be WAV"):
            await provider.transcribe_wav(b"RIFF\x00\x00\x00\x00OGG " + bytes(100))
        with pytest.raises(VoiceProviderError, match="limit is 8 MB"):
            await provider.transcribe_wav(b"RIFF....WAVE" + bytes(MAX_VOICE_BYTES))

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("status", "hint"),
    [
        (400, "10-minute cap"),
        (401, "credential was not accepted"),
        (404, "endpoint not found"),
        (413, "over 32 MB"),
        (429, "rate limited"),
        (500, "processing budget"),
        (502, "unexpected response"),
    ],
)
def test_transcribe_maps_statuses_to_hints(status: int, hint: str) -> None:
    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="nope")

    async def run_test() -> None:
        with pytest.raises(VoiceProviderError, match=hint):
            await make_provider(fake_handler).transcribe_wav(make_wav())

    asyncio.run(run_test())


def test_transcribe_maps_bad_payloads_and_outages() -> None:
    def no_transcript(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sessionId": "s-1"})

    def outage(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async def run_test() -> None:
        with pytest.raises(VoiceProviderError, match="no transcript"):
            await make_provider(no_transcript).transcribe_wav(make_wav())
        with pytest.raises(VoiceProviderError, match="Could not connect"):
            await make_provider(outage).transcribe_wav(make_wav())

    asyncio.run(run_test())
