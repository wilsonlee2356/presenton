import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from models.sql.video_project import VideoProjectModel
from models.sql.video_render_job import VideoRenderJobModel
from services.database import async_session_maker
from services.html_video_renderer import render_html_to_video
from services.tts_service import TTSConfig, generate_speaker_note_clips, generate_srt_entry_clips
from services.video_export_service import (
    _build_srt_audio_track,
    _build_speaker_note_audio_track,
    _exec_ffmpeg,
)
from utils.filename_utils import safe_export_basename
from utils.get_env import get_app_data_directory_env
from utils.srt_utils import parse_srt

LOGGER = logging.getLogger(__name__)

DEFAULT_VIDEO_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 100vw;
    height: 100vh;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #ffffff;
    overflow: hidden;
  }
  .scene {
    text-align: center;
    padding: 2rem;
    animation: fadeIn 1s ease-out;
  }
  h1 {
    font-size: 4rem;
    margin-bottom: 1rem;
    animation: slideUp 1.2s ease-out 0.3s both;
  }
  p {
    font-size: 1.8rem;
    opacity: 0.9;
    animation: slideUp 1.2s ease-out 0.8s both;
  }
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  @keyframes slideUp {
    from { opacity: 0; transform: translateY(40px); }
    to { opacity: 1; transform: translateY(0); }
  }
</style>
</head>
<body>
  <div class="scene">
    <h1>{{title}}</h1>
    <p>{{description}}</p>
  </div>
</body>
</html>
"""


def _ensure_video_studio_directory() -> str:
    app_data = get_app_data_directory_env() or "/tmp/presenton"
    exports_dir = os.path.join(app_data, "exports", "video-studio")
    os.makedirs(exports_dir, exist_ok=True)
    return exports_dir


async def _update_job(
    job_id: uuid.UUID,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    error: dict[str, Any] | None = None,
    output_path: str | None = None,
    youtube_video_id: str | None = None,
    completed_at: bool = False,
) -> None:
    """Update a render job row in the database."""
    async with async_session_maker() as session:
        job = await session.get(VideoRenderJobModel, job_id)
        if not job:
            LOGGER.warning("[video_studio] job %s not found for update", job_id)
            return
        if status is not None:
            job.status = status
        if stage is not None:
            job.stage = stage
        if progress is not None:
            job.progress = progress
        if message is not None:
            job.message = message
        if error is not None:
            job.error = error
        if output_path is not None:
            job.output_path = output_path
        if youtube_video_id is not None:
            job.youtube_video_id = youtube_video_id
        if completed_at:
            job.completed_at = datetime.now()
        job.updated_at = datetime.now()
        await session.commit()


async def _update_project(
    project_id: uuid.UUID,
    *,
    status: str | None = None,
    output_path: str | None = None,
    youtube_video_id: str | None = None,
) -> None:
    async with async_session_maker() as session:
        project = await session.get(VideoProjectModel, project_id)
        if not project:
            return
        if status is not None:
            project.status = status
        if output_path is not None:
            project.output_path = output_path
        if youtube_video_id is not None:
            project.youtube_video_id = youtube_video_id
        project.updated_at = datetime.now()
        await session.commit()


def _parse_resolution(resolution: str | None) -> tuple[int, int]:
    if not resolution:
        return 1280, 720
    try:
        width, height = resolution.lower().split("x")
        return int(width), int(height)
    except ValueError:
        return 1280, 720


def _generate_html_content(project: VideoProjectModel) -> str:
    """Generate a self-contained HTML animation for the project."""
    title = (project.title or "Video").replace("<", "&lt;").replace(">", "&gt;")
    description = (project.description or "").replace("<", "&lt;").replace(">", "&gt;")

    # TODO: replace with LLM-driven scene generation once the prompt/schema is tuned.
    try:
        from utils.llm_provider import get_llm_client, get_model

        client = get_llm_client()
        if client:
            prompt = f"""Create a single self-contained HTML file that animates the following video concept.
Use only inline CSS and JavaScript. The animation should last approximately {project.duration_seconds or 10} seconds.
Title: {project.title}
Description: {project.description or project.prompt or ''}
Style: {project.style or 'modern, minimalist'}

Return ONLY the raw HTML code (no markdown code fences, no explanations)."""
            response = client.chat.completions.create(
                model=get_model(),
                messages=[
                    {"role": "system", "content": "You are an expert HTML/CSS animator."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            html = response.choices[0].message.content or ""
            # Strip markdown fences if the model ignored the instruction.
            html = html.strip()
            if html.startswith("```"):
                html = "\n".join(html.split("\n")[1:])
            if html.endswith("```"):
                html = html[:-3].strip()
            if "<html" in html.lower():
                return html
    except Exception:
        LOGGER.exception("[video_studio] LLM HTML generation failed; using fallback template")

    return DEFAULT_VIDEO_TEMPLATE.replace("{{title}}", title).replace("{{description}}", description)


async def _generate_audio_track(
    project: VideoProjectModel,
    tts_config: TTSConfig,
    video_duration_seconds: float,
) -> str | None:
    """Generate an AAC audio track for the project, or None if narration is unavailable."""
    narration_source = project.narration_source or "script"

    if narration_source == "srt" and project.srt_content:
        entries = parse_srt(project.srt_content)
        if not entries:
            return None
        clip_dir = tempfile.mkdtemp(prefix="presenton_vs_srt_clips_")
        try:
            clips = await generate_srt_entry_clips(entries, clip_dir, tts_config)
            last_end_ms = max(entry.get("end_ms", 0) for entry in entries)
            total_duration_ms = max(video_duration_seconds * 1000, last_end_ms)
            audio_path = await _build_srt_audio_track(entries, clips, total_duration_ms)
            return audio_path
        finally:
            await asyncio.to_thread(shutil.rmtree, clip_dir, ignore_errors=True)

    text = project.narration_text or project.prompt or project.description or ""
    if not text.strip():
        return None

    clip_dir = tempfile.mkdtemp(prefix="presenton_vs_script_clips_")
    try:
        clips = await generate_speaker_note_clips([text], clip_dir, tts_config)
        audio_path, _ = await _build_speaker_note_audio_track(
            [text], clips, pause_between_slides=0.0, min_seconds_per_slide=video_duration_seconds
        )
        return audio_path
    finally:
        await asyncio.to_thread(shutil.rmtree, clip_dir, ignore_errors=True)


async def _mux_video_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
) -> str:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-i",
        audio_path,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        output_path,
    ]
    await _exec_ffmpeg(cmd)
    return output_path


async def render_video_project(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
) -> None:
    """Render a video project end-to-end and update the job/project rows."""
    async with async_session_maker() as session:
        project = await session.get(VideoProjectModel, project_id)
        if not project:
            LOGGER.error("[video_studio] project %s not found; aborting render", project_id)
            await _update_job(
                job_id,
                status="failed",
                message="Video project not found",
                error={"detail": "Video project not found"},
                completed_at=True,
            )
            return

    await _update_job(job_id, status="running", stage="generating_html", progress=5)
    await _update_project(project_id, status="rendering")

    width, height = _parse_resolution(project.resolution)
    fps = project.fps or 30
    duration_seconds = project.duration_seconds or 10.0

    tts_config = TTSConfig(
        base_url=(project.chatterbox_config or {}).get("chatterbox_url", "http://127.0.0.1:8001"),
        voice_mode=(project.chatterbox_config or {}).get("voice_mode", "predefined"),
        predefined_voice_id=(project.chatterbox_config or {}).get("predefined_voice_id"),
        reference_audio_filename=(project.chatterbox_config or {}).get("reference_audio_filename"),
        output_format=(project.chatterbox_config or {}).get("output_format", "wav"),
        speed_factor=(project.chatterbox_config or {}).get("speed_factor"),
        language=(project.chatterbox_config or {}).get("language"),
    )

    html_temp_dir = tempfile.mkdtemp(prefix="presenton_vs_html_")
    video_temp_dir = tempfile.mkdtemp(prefix="presenton_vs_video_")
    audio_path: str | None = None
    audio_temp_dir: str | None = None

    try:
        html_content = _generate_html_content(project)
        html_path = os.path.join(html_temp_dir, "scene.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        await _update_job(job_id, stage="rendering_video", progress=30)
        raw_video_path = os.path.join(video_temp_dir, "raw_video.mp4")
        await render_html_to_video(
            html_path=html_path,
            output_path=raw_video_path,
            width=width,
            height=height,
            duration_seconds=duration_seconds,
            fps=fps,
        )

        await _update_job(job_id, stage="synthesizing_audio", progress=60)
        audio_path = await _generate_audio_track(project, tts_config, duration_seconds)
        if audio_path:
            audio_temp_dir = os.path.dirname(audio_path)

        await _update_job(job_id, stage="muxing", progress=85)
        exports_dir = _ensure_video_studio_directory()
        safe_title = safe_export_basename(project.title or str(project_id))
        output_path = os.path.join(exports_dir, f"{safe_title}.mp4")

        if audio_path:
            await _mux_video_audio(raw_video_path, audio_path, output_path)
        else:
            shutil.copy2(raw_video_path, output_path)

        await _update_project(
            project_id,
            status="rendered",
            output_path=output_path,
        )
        await _update_job(
            job_id,
            status="completed",
            stage="muxing",
            progress=100,
            output_path=output_path,
            completed_at=True,
        )
        LOGGER.info(
            "[video_studio] project %s rendered to %s (audio=%s)",
            project_id,
            output_path,
            bool(audio_path),
        )
    except Exception as exc:
        LOGGER.exception("[video_studio] render failed for project %s", project_id)
        await _update_project(project_id, status="failed")
        await _update_job(
            job_id,
            status="failed",
            message=str(exc),
            error={"detail": str(exc)},
            completed_at=True,
        )
    finally:
        await asyncio.to_thread(shutil.rmtree, html_temp_dir, ignore_errors=True)
        await asyncio.to_thread(shutil.rmtree, video_temp_dir, ignore_errors=True)
        if audio_temp_dir:
            await asyncio.to_thread(shutil.rmtree, audio_temp_dir, ignore_errors=True)


async def get_render_job(job_id: uuid.UUID) -> VideoRenderJobModel | None:
    async with async_session_maker() as session:
        return await session.get(VideoRenderJobModel, job_id)


async def list_video_projects(limit: int = 50) -> list[VideoProjectModel]:
    async with async_session_maker() as session:
        result = await session.scalars(
            select(VideoProjectModel).order_by(VideoProjectModel.created_at.desc()).limit(limit)
        )
        return list(result)
