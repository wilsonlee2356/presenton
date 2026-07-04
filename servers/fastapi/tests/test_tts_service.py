import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest

from services.tts_service import generate_speaker_note_clips


@pytest.mark.anyio
async def test_generate_speaker_note_clips_skips_empty_notes():
    with tempfile.TemporaryDirectory() as output_dir:
        notes = ["Hello world", "", "   ", "Second note"]

        mock_response = AsyncMock()
        mock_response.stream_to_file = Mock(
            side_effect=lambda path: open(path, "wb").close()
        )

        mock_client = AsyncMock()
        mock_client.audio.speech.create = AsyncMock(return_value=mock_response)

        with patch(
            "services.tts_service._get_async_openai_client", return_value=mock_client
        ):
            result = await generate_speaker_note_clips(notes, output_dir)

        assert len(result) == len(notes)
        assert result[0] is not None
        assert result[1] is None
        assert result[2] is None
        assert result[3] is not None

        # Two non-empty notes should have triggered TTS generation.
        assert mock_client.audio.speech.create.await_count == 2

        # Verify the written file path matches the expected convention.
        assert os.path.isfile(result[0])
        assert os.path.isfile(result[3])


@pytest.mark.anyio
async def test_generate_speaker_note_clips_returns_none_without_api_key():
    with tempfile.TemporaryDirectory() as output_dir:
        notes = ["Hello world"]
        with patch("services.tts_service._get_async_openai_client", return_value=None):
            result = await generate_speaker_note_clips(notes, output_dir)

        assert result == [None]
