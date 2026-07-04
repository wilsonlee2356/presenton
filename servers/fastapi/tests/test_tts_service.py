import os
import tempfile
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from services.tts_service import (
    TTSConfig,
    generate_speaker_note_clips,
    generate_srt_entry_clips,
)


class _FakeResponse:
    def __init__(self, status: int = 200, body: bytes = b"fake audio"):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def read(self) -> bytes:
        return self._body

    @property
    def content(self):
        return self

    async def iter_chunked(self, _size: int):
        yield self._body


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url: str, **kwargs):
        return _FakeContext()

    def post(self, url: str, **kwargs):
        return _FakeContext(self._response)


class _FakeContext:
    def __init__(self, response: _FakeResponse | None = None):
        self._response = response

    async def __aenter__(self):
        if self._response is None:
            return _FakeResponse(status=200, body=b'["voice_1.wav"]')
        return self._response

    async def __aexit__(self, *args):
        return False


@pytest.mark.anyio
async def test_generate_speaker_note_clips_skips_empty_notes():
    with tempfile.TemporaryDirectory() as output_dir:
        notes = ["Hello world", "", "   ", "Second note"]
        config = TTSConfig(base_url="http://localhost:8001", predefined_voice_id="voice_1.wav")

        with patch("aiohttp.ClientSession", return_value=_FakeSession(_FakeResponse())):
            result = await generate_speaker_note_clips(notes, output_dir, config)

        assert len(result) == len(notes)
        assert result[0] is not None
        assert result[1] is None
        assert result[2] is None
        assert result[3] is not None
        assert os.path.isfile(result[0])
        assert os.path.isfile(result[3])


@pytest.mark.anyio
async def test_generate_speaker_note_clips_falls_back_when_no_voice():
    with tempfile.TemporaryDirectory() as output_dir:
        notes = ["Hello world"]
        config = TTSConfig(base_url="http://localhost:8001")

        # No predefined voices returned and no voice configured.
        with patch(
            "aiohttp.ClientSession", return_value=_FakeSession(_FakeResponse(status=200, body=b"[]"))
        ):
            result = await generate_speaker_note_clips(notes, output_dir, config)

        assert result == [None]


@pytest.mark.anyio
async def test_generate_srt_entry_clips_generates_per_entry():
    with tempfile.TemporaryDirectory() as output_dir:
        entries = [
            {"text": "First line", "duration_ms": 1000},
            {"text": "Second line", "duration_ms": 1500},
        ]
        config = TTSConfig(base_url="http://localhost:8001", predefined_voice_id="voice_1.wav")

        with patch("aiohttp.ClientSession", return_value=_FakeSession(_FakeResponse())):
            result = await generate_srt_entry_clips(entries, output_dir, config)

        assert len(result) == 2
        assert all(path is not None for path in result)
