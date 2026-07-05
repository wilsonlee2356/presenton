import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from models.sql.video_project import VideoProjectModel
from models.sql.video_render_job import VideoRenderJobModel
from services.database import async_session_maker
from utils.youtube_config import (
    get_youtube_credentials,
    is_youtube_token_expired,
    set_youtube_access_token,
    set_youtube_token_expires_ms,
)

LOGGER = logging.getLogger(__name__)


async def _get_fresh_credentials() -> Credentials:
    """Load stored YouTube credentials and refresh if necessary."""
    async with async_session_maker() as session:
        creds_dict = await get_youtube_credentials(session)
        if not creds_dict.get("token"):
            raise RuntimeError("YouTube account is not connected")

        creds = Credentials.from_authorized_user_info(creds_dict)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                await asyncio.to_thread(creds.refresh, Request())
                await set_youtube_access_token(session, creds.token)
                if creds.expiry:
                    expires_ms = int(creds.expiry.timestamp() * 1000)
                    await set_youtube_token_expires_ms(session, expires_ms)
            else:
                raise RuntimeError("YouTube token expired and cannot be refreshed")
        return creds


def _upload_sync(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str,
    privacy_status: str,
    credentials: Credentials,
) -> dict[str, Any]:
    """Synchronous YouTube upload using the Data API v3."""
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
    )

    request = youtube.videos().insert(
        part=",".join(["snippet", "status"]),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            LOGGER.info("[youtube_upload] uploaded %d%%", int(status.progress() * 100))

    return response


async def _update_job(
    job_id: Any,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    error: dict[str, Any] | None = None,
    youtube_video_id: str | None = None,
    completed_at: bool = False,
) -> None:
    async with async_session_maker() as session:
        job = await session.get(VideoRenderJobModel, job_id)
        if not job:
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
        if youtube_video_id is not None:
            job.youtube_video_id = youtube_video_id
        if completed_at:
            job.completed_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        await session.commit()


async def _update_project(
    project_id: Any,
    *,
    status: str | None = None,
    youtube_video_id: str | None = None,
) -> None:
    async with async_session_maker() as session:
        project = await session.get(VideoProjectModel, project_id)
        if not project:
            return
        if status is not None:
            project.status = status
        if youtube_video_id is not None:
            project.youtube_video_id = youtube_video_id
        project.updated_at = datetime.now(timezone.utc)
        await session.commit()


async def upload_video_project_to_youtube(
    project_id: Any,
    job_id: Any,
) -> None:
    """Upload a rendered video project's MP4 to YouTube."""
    await _update_job(job_id, status="running", stage="uploading", progress=0)
    await _update_project(project_id, status="uploading")

    async with async_session_maker() as session:
        project = await session.get(VideoProjectModel, project_id)
        if not project:
            await _update_job(job_id, status="failed", message="Project not found", completed_at=True)
            return

        video_path = project.output_path
        if not video_path or not os.path.isfile(video_path):
            await _update_job(
                job_id,
                status="failed",
                message="Rendered video file not found",
                completed_at=True,
            )
            await _update_project(project_id, status="failed")
            return

        youtube_config = project.youtube_config or {}
        title = youtube_config.get("title") or project.title or "Presenton Video"
        description = youtube_config.get("description") or project.description or ""
        tags = youtube_config.get("tags") or []
        category_id = youtube_config.get("category_id") or "22"
        privacy_status = youtube_config.get("privacy_status") or "private"

    try:
        credentials = await _get_fresh_credentials()
        await _update_job(job_id, progress=30)

        response = await asyncio.to_thread(
            _upload_sync,
            video_path,
            title,
            description,
            tags,
            category_id,
            privacy_status,
            credentials,
        )

        video_id = response.get("id")
        await _update_job(
            job_id,
            status="completed",
            progress=100,
            youtube_video_id=video_id,
            completed_at=True,
        )
        await _update_project(
            project_id,
            status="uploaded",
            youtube_video_id=video_id,
        )
        LOGGER.info(
            "[youtube_upload] project %s uploaded as https://youtu.be/%s",
            project_id,
            video_id,
        )
    except HttpError as exc:
        LOGGER.exception("[youtube_upload] YouTube API error")
        await _update_job(
            job_id,
            status="failed",
            message=str(exc),
            error={"detail": str(exc), "status": exc.resp.status if exc.resp else None},
            completed_at=True,
        )
        await _update_project(project_id, status="failed")
    except Exception as exc:
        LOGGER.exception("[youtube_upload] upload failed")
        await _update_job(
            job_id,
            status="failed",
            message=str(exc),
            error={"detail": str(exc)},
            completed_at=True,
        )
        await _update_project(project_id, status="failed")
