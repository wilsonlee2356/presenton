import asyncio
import logging
import os

from openai import AsyncOpenAI

from utils.get_env import get_openai_api_key_env

LOGGER = logging.getLogger(__name__)

DEFAULT_TTS_MODEL = "tts-1"
DEFAULT_VOICE = "alloy"
MAX_CONCURRENT_TTS = 5


def _get_async_openai_client() -> AsyncOpenAI | None:
    """Return an async OpenAI client if an API key is configured."""
    api_key = get_openai_api_key_env()
    if not api_key:
        return None
    return AsyncOpenAI(api_key=api_key)


async def generate_speaker_note_clips(
    note_texts: list[str],
    output_dir: str,
    voice: str = DEFAULT_VOICE,
) -> list[str | None]:
    """
    Generate one MP3 TTS clip per non-empty speaker note.

    Returns a list aligned with `note_texts`. Entries for empty notes or failed
    generations are ``None``; the caller should substitute a silent segment.
    """
    client = _get_async_openai_client()
    if client is None:
        LOGGER.warning(
            "[tts_service] OpenAI API key is not configured; skipping narration"
        )
        return [None] * len(note_texts)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TTS)

    async def _generate_one(index: int, text: str) -> str | None:
        stripped = text.strip()
        if not stripped:
            return None

        output_path = os.path.join(output_dir, f"tts_{index:04d}.mp3")
        async with semaphore:
            try:
                response = await client.audio.speech.create(
                    model=DEFAULT_TTS_MODEL,
                    voice=voice,
                    input=stripped,
                    response_format="mp3",
                )
                await asyncio.to_thread(response.stream_to_file, output_path)
                return output_path
            except Exception:
                LOGGER.exception(
                    "[tts_service] TTS generation failed for slide %s", index
                )
                return None

    return await asyncio.gather(
        *(_generate_one(i, text) for i, text in enumerate(note_texts))
    )
