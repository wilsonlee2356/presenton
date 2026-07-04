import asyncio
import logging
import os
from typing import Any

import aiohttp

LOGGER = logging.getLogger(__name__)

DEFAULT_CHATTERBOX_URL = "http://127.0.0.1:8001"
DEFAULT_VOICE_MODE = "predefined"
DEFAULT_OUTPUT_FORMAT = "wav"
MAX_CONCURRENT_TTS = 2
TTS_TIMEOUT_SECONDS = 300


class TTSConfig:
    """Lightweight container for Chatterbox TTS settings."""

    def __init__(
        self,
        base_url: str = DEFAULT_CHATTERBOX_URL,
        voice_mode: str = DEFAULT_VOICE_MODE,
        predefined_voice_id: str | None = None,
        reference_audio_filename: str | None = None,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        speed_factor: float | None = None,
        language: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.voice_mode = voice_mode
        self.predefined_voice_id = predefined_voice_id
        self.reference_audio_filename = reference_audio_filename
        self.output_format = output_format
        self.speed_factor = speed_factor
        self.language = language


def _chatterbox_error(message: str, status: int | None = None) -> str:
    prefix = f"Chatterbox TTS error (HTTP {status})" if status else "Chatterbox TTS error"
    return f"{prefix}: {message}"


async def _chatterbox_get_json(session: aiohttp.ClientSession, url: str) -> Any:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
        if response.status != 200:
            text = await response.text()
            raise RuntimeError(_chatterbox_error(text, response.status))
        return await response.json()


async def _resolve_predefined_voice(config: TTSConfig) -> str | None:
    """Return the configured voice, or the first available predefined voice."""
    if config.predefined_voice_id:
        return config.predefined_voice_id

    url = f"{config.base_url}/get_predefined_voices"
    try:
        async with aiohttp.ClientSession() as session:
            voices = await _chatterbox_get_json(session, url)
            if isinstance(voices, list) and voices:
                first = voices[0]
                if isinstance(first, dict):
                    return first.get("filename") or first.get("display_name")
                if isinstance(first, str):
                    return first
    except Exception:
        LOGGER.exception("[tts_service] failed to fetch predefined voices from %s", url)

    return None


async def _resolve_reference_audio(config: TTSConfig) -> str | None:
    if config.reference_audio_filename:
        return config.reference_audio_filename

    url = f"{config.base_url}/get_reference_files"
    try:
        async with aiohttp.ClientSession() as session:
            files = await _chatterbox_get_json(session, url)
            if isinstance(files, list) and files:
                first = files[0]
                return first.get("filename") if isinstance(first, dict) else first
    except Exception:
        LOGGER.exception("[tts_service] failed to fetch reference files from %s", url)

    return None


async def _generate_chatterbox_tts_clip(
    text: str,
    output_path: str,
    config: TTSConfig,
    semaphore: asyncio.Semaphore,
) -> bool:
    """Generate one audio clip via Chatterbox. Returns True on success."""
    if not text.strip():
        return False

    if config.voice_mode == "predefined":
        voice_id = await _resolve_predefined_voice(config)
        if not voice_id:
            LOGGER.warning(
                "[tts_service] no predefined voice available at %s", config.base_url
            )
            return False
        payload: dict[str, Any] = {
            "text": text,
            "voice_mode": "predefined",
            "predefined_voice_id": voice_id,
        }
    elif config.voice_mode == "clone":
        ref = await _resolve_reference_audio(config)
        if not ref:
            LOGGER.warning(
                "[tts_service] no reference audio available at %s", config.base_url
            )
            return False
        payload = {
            "text": text,
            "voice_mode": "clone",
            "reference_audio_filename": ref,
        }
    else:
        LOGGER.warning("[tts_service] unsupported voice_mode: %s", config.voice_mode)
        return False

    payload["output_format"] = config.output_format
    payload["split_text"] = True
    payload["chunk_size"] = 120
    payload["stream"] = False
    if config.speed_factor is not None:
        payload["speed_factor"] = config.speed_factor
    if config.language is not None:
        payload["language"] = config.language

    url = f"{config.base_url}/tts"
    async with semaphore:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=TTS_TIMEOUT_SECONDS),
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        LOGGER.error(
                            "[tts_service] TTS request failed: %s", text[:500]
                        )
                        return False
                    with open(output_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                    return True
        except Exception:
            LOGGER.exception("[tts_service] TTS request to %s failed", url)
            return False


async def generate_speaker_note_clips(
    note_texts: list[str],
    output_dir: str,
    config: TTSConfig,
) -> list[str | None]:
    """
    Generate one audio clip per non-empty speaker note via Chatterbox.

    Returns a list aligned with ``note_texts``. Entries for empty notes or failed
    generations are ``None``; the caller should substitute a silent segment.
    """
    if config.voice_mode == "predefined" and not config.predefined_voice_id:
        config.predefined_voice_id = await _resolve_predefined_voice(config)
    elif config.voice_mode == "clone" and not config.reference_audio_filename:
        config.reference_audio_filename = await _resolve_reference_audio(config)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TTS)

    async def _generate_one(index: int, text: str) -> str | None:
        output_path = os.path.join(output_dir, f"tts_{index:04d}.{config.output_format}")
        success = await _generate_chatterbox_tts_clip(text, output_path, config, semaphore)
        return output_path if success else None

    return await asyncio.gather(
        *(_generate_one(i, text) for i, text in enumerate(note_texts))
    )


async def generate_srt_entry_clips(
    entries: list[dict[str, Any]],
    output_dir: str,
    config: TTSConfig,
) -> list[str | None]:
    """
    Generate one audio clip per SRT entry via Chatterbox.

    Each ``entry`` is expected to have ``text`` and ``duration_ms``. The returned
    paths are aligned with ``entries``; failed generations are ``None``.
    """
    if config.voice_mode == "predefined" and not config.predefined_voice_id:
        config.predefined_voice_id = await _resolve_predefined_voice(config)
    elif config.voice_mode == "clone" and not config.reference_audio_filename:
        config.reference_audio_filename = await _resolve_reference_audio(config)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TTS)

    async def _generate_one(index: int, entry: dict[str, Any]) -> str | None:
        output_path = os.path.join(output_dir, f"tts_{index:04d}.{config.output_format}")
        success = await _generate_chatterbox_tts_clip(
            entry.get("text", ""), output_path, config, semaphore
        )
        return output_path if success else None

    return await asyncio.gather(
        *(_generate_one(i, entry) for i, entry in enumerate(entries))
    )
