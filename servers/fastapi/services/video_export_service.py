import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from typing import Literal

from fastapi import HTTPException
from pathvalidate import sanitize_filename

from models.presentation_and_path import PresentationAndPath
from services.export_task_service import EXPORT_TASK_SERVICE
from services.tts_service import generate_speaker_note_clips
from templates.fonts_and_slides_preview import render_pptx_slides_to_images
from utils.filename_utils import safe_export_basename
from utils.get_env import get_app_data_directory_env, get_openai_api_key_env

LOGGER = logging.getLogger(__name__)

VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_FPS = 30
DEFAULT_SECONDS_PER_SLIDE = 5


class _SimpleLogger:
    """Adapter so render_pptx_slides_to_images can log through our logger."""

    def info(self, message: str):
        LOGGER.info("[video_export] %s", message)


async def _which_ffmpeg() -> str:
    """Return the path to the FFmpeg binary or raise a clear HTTP error."""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise HTTPException(
            status_code=500,
            detail="FFmpeg is required for MP4 export but is not installed on the server.",
        )
    return ffmpeg_path


async def _which_ffprobe() -> str | None:
    """Return the path to the FFprobe binary, if available."""
    return shutil.which("ffprobe")


def _ensure_exports_directory() -> str:
    app_data = get_app_data_directory_env() or "/tmp/presenton"
    exports_dir = os.path.join(app_data, "exports")
    os.makedirs(exports_dir, exist_ok=True)
    return exports_dir


def _ensure_output_readable(output_path: str) -> None:
    """Match the permissions used by the bundled export runtime."""
    try:
        os.chmod(os.path.dirname(output_path), 0o755)
        os.chmod(output_path, 0o644)
    except OSError:
        LOGGER.warning("Could not set permissions on %s", output_path)


async def _exec_ffmpeg(cmd: list[str]) -> None:
    """Run an FFmpeg command and raise a descriptive HTTPException on failure."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        stderr_text = stderr.decode("utf-8", errors="replace")[-2000:]
        LOGGER.error("[video_export] FFmpeg failed: %s", stderr_text)
        raise HTTPException(
            status_code=500,
            detail=f"FFmpeg failed: {stderr_text}",
        )


async def _get_audio_duration(audio_path: str) -> float | None:
    """Return the duration of an audio file in seconds, or None if unknown."""
    ffprobe = await _which_ffprobe()
    if not ffprobe:
        return None

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()

    if process.returncode != 0:
        return None
    try:
        return float(stdout.decode("utf-8", errors="replace").strip())
    except ValueError:
        return None


async def _generate_silent_audio_segment(output_path: str, duration: float) -> None:
    """Generate a silent MP3 of exactly ``duration`` seconds."""
    ffmpeg = await _which_ffmpeg()
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=24000:cl=mono",
        "-t",
        str(duration),
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        output_path,
    ]
    await _exec_ffmpeg(cmd)


async def _normalize_audio_segment(
    input_path: str | None,
    output_path: str,
    duration: float,
) -> None:
    """
    Pad or truncate an audio clip so it lasts exactly ``duration`` seconds.

    If ``input_path`` is None/missing, a silent segment is produced instead.
    """
    if not input_path or not os.path.isfile(input_path):
        await _generate_silent_audio_segment(output_path, duration)
        return

    actual_duration = await _get_audio_duration(input_path)
    if actual_duration is None:
        await _generate_silent_audio_segment(output_path, duration)
        return

    ffmpeg = await _which_ffmpeg()
    pad = max(0.0, duration - actual_duration)

    if pad > 0:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            input_path,
            "-af",
            f"apad=pad_dur={pad}",
            "-t",
            str(duration),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            output_path,
        ]
    else:
        # Audio is already as long as (or longer than) the slide; just truncate.
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            input_path,
            "-t",
            str(duration),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            output_path,
        ]

    await _exec_ffmpeg(cmd)


async def _concatenate_audio_segments(
    segment_paths: list[str],
    output_path: str,
) -> None:
    """Concatenate normalized audio segments into a single AAC track."""
    if not segment_paths:
        raise HTTPException(status_code=500, detail="No audio segments to concatenate")

    ffmpeg = await _which_ffmpeg()
    cmd = [ffmpeg, "-y"]
    for segment_path in segment_paths:
        cmd += ["-i", segment_path]

    inputs = "".join(f"[{i}:a]" for i in range(len(segment_paths)))
    filter_complex = f"{inputs}concat=n={len(segment_paths)}:v=0:a=1[outa]"

    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[outa]",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        output_path,
    ]
    await _exec_ffmpeg(cmd)


async def _build_narration_audio_track(
    speaker_notes: list[str],
    voice: str,
    seconds_per_slide: float,
) -> str | None:
    """
    Build a single AAC audio track from speaker notes.

    Returns the path to the audio file, or None if narration cannot be built.
    The caller is responsible for deleting the parent temporary directory.
    """
    if not speaker_notes:
        return None

    audio_temp_dir = tempfile.mkdtemp(prefix="presenton_audio_")
    try:
        tts_clips = await generate_speaker_note_clips(
            speaker_notes, audio_temp_dir, voice=voice
        )

        segment_paths: list[str] = []
        for i, _ in enumerate(speaker_notes):
            segment_path = os.path.join(audio_temp_dir, f"segment_{i:04d}.mp3")
            await _normalize_audio_segment(tts_clips[i], segment_path, seconds_per_slide)
            segment_paths.append(segment_path)

        audio_track_path = os.path.join(audio_temp_dir, "audio_track.aac")
        await _concatenate_audio_segments(segment_paths, audio_track_path)
        return audio_track_path
    except Exception:
        LOGGER.exception("[video_export] failed to build narration audio track")
        await asyncio.to_thread(shutil.rmtree, audio_temp_dir, ignore_errors=True)
        return None


async def _run_ffmpeg(
    image_paths: list[str],
    output_path: str,
    seconds_per_slide: float,
    fps: int = VIDEO_FPS,
    audio_path: str | None = None,
) -> None:
    """Concatenate sequential PNGs into an H.264 MP4 using FFmpeg."""
    if not image_paths:
        raise HTTPException(status_code=400, detail="No slide images to encode")

    ffmpeg = await _which_ffmpeg()
    temp_dir = tempfile.mkdtemp(prefix="presenton_video_")

    try:
        for idx, src_path in enumerate(image_paths, start=1):
            dest_path = os.path.join(temp_dir, f"slide_{idx:04d}.png")
            await asyncio.to_thread(shutil.copy2, src_path, dest_path)

        input_pattern = os.path.join(temp_dir, "slide_%04d.png")
        frame_rate = f"1/{seconds_per_slide}"

        cmd = [
            ffmpeg,
            "-y",
            "-framerate",
            frame_rate,
            "-i",
            input_pattern,
        ]

        if audio_path:
            cmd += ["-i", audio_path]

        cmd += [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-s",
            f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
        ]

        if audio_path:
            cmd += [
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
            ]

        cmd += [output_path]

        LOGGER.info(
            "[video_export] encoding %s slides to %s (%.1fs each, audio=%s)",
            len(image_paths),
            output_path,
            seconds_per_slide,
            bool(audio_path),
        )
        await _exec_ffmpeg(cmd)
        LOGGER.info("[video_export] FFmpeg finished successfully")
    finally:
        await asyncio.to_thread(shutil.rmtree, temp_dir, ignore_errors=True)


async def export_presentation_to_mp4(
    presentation_id: uuid.UUID,
    title: str,
    cookie_header: str | None = None,
    seconds_per_slide: float = DEFAULT_SECONDS_PER_SLIDE,
    include_narration: bool = True,
    voice: str = "alloy",
    speaker_notes: list[str] | None = None,
) -> PresentationAndPath:
    """
    Export a presentation as an MP4 slideshow, optionally with TTS narration.

    Pipeline:
      1. Generate a PPTX using the existing bundled export runtime.
      2. Convert the PPTX to per-slide HTML and render each slide to a PNG.
      3. Optionally build an AAC narration track from speaker notes.
      4. Run FFmpeg to combine the PNGs (and audio) into an MP4.
    """
    # Local import to avoid a circular dependency with utils.export_utils.
    from utils.export_utils import _build_presentation_export_url

    export_url, fastapi_url = _build_presentation_export_url(
        presentation_id, cookie_header
    )
    name = (title or "").strip() or str(presentation_id)
    safe_name = safe_export_basename(sanitize_filename(name))

    LOGGER.info(
        "[video_export] starting mp4 export presentation_id=%s title=%s narration=%s",
        presentation_id,
        safe_name,
        include_narration,
    )

    # 1. Produce a PPTX so we can reuse the same rendering path as PDF/PPTX export.
    pptx_result = await EXPORT_TASK_SERVICE.export_from_url(
        url=export_url,
        title=safe_name,
        export_as="pptx",
        fastapi_url=fastapi_url,
        cookie_header=cookie_header,
    )
    if not os.path.isfile(pptx_result.path):
        raise HTTPException(
            status_code=500, detail="PPTX export did not produce a file"
        )

    # 2. Render each slide to a PNG.
    logger = _SimpleLogger()
    try:
        image_paths = await render_pptx_slides_to_images(
            modified_pptx_path=pptx_result.path,
            font_paths_for_install=[],
            max_slides=None,
            logger=logger,
        )
    except Exception as exc:
        LOGGER.exception("[video_export] failed to render slide images")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to render slide images: {exc}",
        ) from exc

    if not image_paths:
        raise HTTPException(status_code=500, detail="No slide images were rendered")

    # 3. Optionally build a narration audio track.
    audio_path: str | None = None
    audio_temp_dir: str | None = None
    if include_narration and speaker_notes:
        if not get_openai_api_key_env():
            LOGGER.warning(
                "[video_export] narration requested but OpenAI API key is not configured; "
                "producing silent MP4"
            )
        else:
            audio_path = await _build_narration_audio_track(
                speaker_notes,
                voice=voice,
                seconds_per_slide=seconds_per_slide,
            )
            if audio_path:
                audio_temp_dir = os.path.dirname(audio_path)

    # 4. Encode the PNG sequence (and optional audio) into an MP4.
    exports_dir = _ensure_exports_directory()
    output_path = os.path.join(exports_dir, f"{safe_name}.mp4")
    try:
        await _run_ffmpeg(
            image_paths, output_path, seconds_per_slide, audio_path=audio_path
        )
    finally:
        if audio_temp_dir:
            await asyncio.to_thread(shutil.rmtree, audio_temp_dir, ignore_errors=True)

    _ensure_output_readable(output_path)

    LOGGER.info(
        "[video_export] finished mp4 export presentation_id=%s path=%s audio=%s",
        presentation_id,
        output_path,
        bool(audio_path),
    )
    return PresentationAndPath(presentation_id=presentation_id, path=output_path)
