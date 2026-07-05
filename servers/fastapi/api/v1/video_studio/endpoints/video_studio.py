import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.sql.video_project import VideoProjectModel
from models.sql.video_render_job import VideoRenderJobModel
from services.database import get_async_session
from services.video_studio_service import render_video_project
from services.youtube_upload_service import upload_video_project_to_youtube
from utils.oauth.youtube import create_authorization_flow, exchange_authorization_code
from utils.youtube_config import clear_youtube_credentials, set_youtube_credentials

VIDEO_STUDIO_ROUTER = APIRouter(prefix="/video-studio", tags=["Video Studio"])

# In-memory short-lived OAuth sessions. In a multi-worker deployment these would
# need to move to Redis / the database, but for the MVP single-instance setup
# this is sufficient.
_sessions_by_id: dict[str, dict[str, Any]] = {}
_sessions_by_state: dict[str, dict[str, Any]] = {}


SUCCESS_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Presenton – YouTube connected</title>
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #eef2ff 0, #0f172a 55%, #020617 100%);
      color: #e5e7eb;
    }
    .card {
      background: rgba(15, 23, 42, 0.9);
      border-radius: 18px;
      padding: 28px 32px 26px;
      box-shadow: 0 18px 45px rgba(15, 23, 42, 0.75), 0 0 0 1px rgba(148, 163, 184, 0.2);
      max-width: 440px;
      width: 92vw;
      text-align: center;
    }
    h1 { font-size: 20px; margin: 4px 0 10px; }
    p { margin: 4px 0; font-size: 14px; color: #94a3b8; }
  </style>
</head>
<body>
  <main class="card">
    <h1>YouTube connected</h1>
    <p>You can close this window and return to Presenton.</p>
  </main>
</body>
</html>"""


ERROR_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Presenton – YouTube auth issue</title>
  <style>
    body {
      font-family: system-ui, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
      background: #0f172a;
      color: #fecaca;
    }
    .card { text-align: center; max-width: 440px; }
    h1 { font-size: 20px; }
    p { color: #cbd5e1; }
  </style>
</head>
<body>
  <main class="card">
    <h1>Could not connect YouTube</h1>
    <p>{detail}</p>
  </main>
</body>
</html>"""


class ChatterboxConfigInput(BaseModel):
    chatterbox_url: str = Field(default="http://127.0.0.1:8001")
    voice_mode: str = Field(default="predefined")
    predefined_voice_id: Optional[str] = None
    reference_audio_filename: Optional[str] = None
    output_format: str = Field(default="wav")
    speed_factor: Optional[float] = None
    language: Optional[str] = None


class YouTubeConfigInput(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    category_id: Optional[str] = "22"
    privacy_status: Optional[str] = "private"


class CreateVideoProjectRequest(BaseModel):
    title: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    template: Optional[str] = "default"
    style: Optional[str] = None
    resolution: Optional[str] = "1280x720"
    fps: int = 30
    duration_seconds: float = Field(default=10.0, ge=1.0, le=300.0)
    narration_source: Optional[str] = "script"
    narration_text: Optional[str] = None
    srt_content: Optional[str] = None
    chatterbox_config: ChatterboxConfigInput = Field(default_factory=ChatterboxConfigInput)
    youtube_config: YouTubeConfigInput = Field(default_factory=YouTubeConfigInput)


class VideoProjectResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    status: str
    output_path: Optional[str]
    youtube_video_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class VideoRenderJobResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    job_type: str
    status: str
    stage: Optional[str]
    progress: int
    message: Optional[str]
    error: Optional[dict]
    output_path: Optional[str]
    youtube_video_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


class InitiateYouTubeAuthRequest(BaseModel):
    client_id: str
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None


class InitiateYouTubeAuthResponse(BaseModel):
    session_id: str
    url: str
    redirect_uri: str
    instructions: str


class ExchangeYouTubeAuthRequest(BaseModel):
    session_id: str
    code: str


class YouTubeAuthStatusResponse(BaseModel):
    status: str
    detail: Optional[str] = None


def _project_response(project: VideoProjectModel) -> VideoProjectResponse:
    return VideoProjectResponse(
        id=project.id,
        title=project.title,
        description=project.description,
        status=project.status,
        output_path=project.output_path,
        youtube_video_id=project.youtube_video_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _job_response(job: VideoRenderJobModel) -> VideoRenderJobResponse:
    return VideoRenderJobResponse(
        id=job.id,
        project_id=job.project_id,
        job_type=job.job_type,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        message=job.message,
        error=job.error,
        output_path=job.output_path,
        youtube_video_id=job.youtube_video_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


@VIDEO_STUDIO_ROUTER.post("/projects", response_model=VideoProjectResponse)
async def create_video_project(
    request: CreateVideoProjectRequest,
    sql_session: AsyncSession = Depends(get_async_session),
):
    project = VideoProjectModel(
        title=request.title,
        description=request.description,
        prompt=request.prompt,
        template=request.template,
        style=request.style,
        resolution=request.resolution,
        fps=request.fps,
        duration_seconds=request.duration_seconds,
        narration_source=request.narration_source,
        narration_text=request.narration_text,
        srt_content=request.srt_content,
        chatterbox_config=request.chatterbox_config.model_dump(),
        youtube_config=request.youtube_config.model_dump(),
        status="draft",
    )
    sql_session.add(project)
    await sql_session.commit()
    await sql_session.refresh(project)
    return _project_response(project)


@VIDEO_STUDIO_ROUTER.get("/projects", response_model=list[VideoProjectResponse])
async def get_video_projects(
    sql_session: AsyncSession = Depends(get_async_session),
    limit: int = 50,
):
    result = await sql_session.scalars(
        select(VideoProjectModel).order_by(VideoProjectModel.created_at.desc()).limit(limit)
    )
    projects = list(result)
    return [_project_response(p) for p in projects]


@VIDEO_STUDIO_ROUTER.get("/projects/{project_id}", response_model=VideoProjectResponse)
async def get_video_project(
    project_id: uuid.UUID,
    sql_session: AsyncSession = Depends(get_async_session),
):
    project = await sql_session.get(VideoProjectModel, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Video project not found")
    return _project_response(project)


@VIDEO_STUDIO_ROUTER.post("/projects/{project_id}/render", response_model=VideoRenderJobResponse)
async def render_project(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    sql_session: AsyncSession = Depends(get_async_session),
):
    project = await sql_session.get(VideoProjectModel, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Video project not found")

    job = VideoRenderJobModel(
        project_id=project_id,
        job_type="render",
        status="pending",
        progress=0,
    )
    sql_session.add(job)
    await sql_session.commit()
    await sql_session.refresh(job)

    background_tasks.add_task(render_video_project, project_id, job.id)
    return _job_response(job)


@VIDEO_STUDIO_ROUTER.get("/render-jobs/{job_id}", response_model=VideoRenderJobResponse)
async def get_render_job(
    job_id: uuid.UUID,
    sql_session: AsyncSession = Depends(get_async_session),
):
    job = await sql_session.get(VideoRenderJobModel, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")
    return _job_response(job)


@VIDEO_STUDIO_ROUTER.post("/projects/{project_id}/upload-youtube", response_model=VideoRenderJobResponse)
async def upload_project_to_youtube(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    sql_session: AsyncSession = Depends(get_async_session),
):
    project = await sql_session.get(VideoProjectModel, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Video project not found")
    if not project.output_path:
        raise HTTPException(status_code=400, detail="Project has not been rendered yet")

    job = VideoRenderJobModel(
        project_id=project_id,
        job_type="upload",
        status="pending",
        progress=0,
    )
    sql_session.add(job)
    await sql_session.commit()
    await sql_session.refresh(job)

    background_tasks.add_task(upload_video_project_to_youtube, project_id, job.id)
    return _job_response(job)


@VIDEO_STUDIO_ROUTER.post("/youtube/auth/initiate", response_model=InitiateYouTubeAuthResponse)
async def initiate_youtube_auth(
    body: InitiateYouTubeAuthRequest,
):
    flow = create_authorization_flow(
        client_id=body.client_id,
        redirect_uri=body.redirect_uri,
    )

    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "verifier": flow.verifier,
        "state": flow.state,
        "client_id": body.client_id,
        "client_secret": body.client_secret,
        "redirect_uri": flow.redirect_uri,
    }
    _sessions_by_id[session_id] = session
    _sessions_by_state[flow.state] = session

    instructions = (
        "Open the URL in your browser and authorize Presenton to upload videos to YouTube. "
        "You will be redirected back to Presenton when finished."
    )

    return InitiateYouTubeAuthResponse(
        session_id=session_id,
        url=flow.url,
        redirect_uri=flow.redirect_uri,
        instructions=instructions,
    )


@VIDEO_STUDIO_ROUTER.get("/youtube/auth/callback")
async def youtube_auth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    sql_session: AsyncSession = Depends(get_async_session),
):
    """Google OAuth callback. Exchanges the code and stores tokens in the DB."""
    if error:
        detail = f"Google returned an error: {error}"
        return HTMLResponse(content=ERROR_HTML.format(detail=detail), status_code=400)

    if not code or not state:
        detail = "Missing authorization code or state."
        return HTMLResponse(content=ERROR_HTML.format(detail=detail), status_code=400)

    session = _sessions_by_state.pop(state, None)
    if session is None:
        detail = "OAuth session expired or not found. Please start again from Presenton."
        return HTMLResponse(content=ERROR_HTML.format(detail=detail), status_code=400)

    # Clean up the session-by-id entry as well.
    _sessions_by_id.pop(session.get("session_id", ""), None)

    try:
        token_data = exchange_authorization_code(
            code=code,
            verifier=session["verifier"],
            client_id=session["client_id"],
            client_secret=session.get("client_secret"),
            redirect_uri=session.get("redirect_uri"),
        )
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        expires_ms = int(datetime.now().timestamp() * 1000) + int(expires_in) * 1000

        await set_youtube_credentials(
            session=sql_session,
            access_token=access_token,
            refresh_token=refresh_token or "",
            expires_ms=expires_ms,
            client_id=session["client_id"],
            client_secret=session.get("client_secret") or "",
        )

        return HTMLResponse(content=SUCCESS_HTML)
    except Exception as exc:
        detail = f"Token exchange failed: {exc}"
        return HTMLResponse(content=ERROR_HTML.format(detail=detail), status_code=502)


@VIDEO_STUDIO_ROUTER.get("/youtube/auth/status/{session_id}", response_model=YouTubeAuthStatusResponse)
async def poll_youtube_auth_status(
    session_id: str,
    sql_session: AsyncSession = Depends(get_async_session),
):
    """Poll for the result of an ongoing OAuth flow.

    Because the callback is handled by the backend directly, a session is
    considered successful once it has been removed from the in-memory store
    **and** credentials exist in the database.
    """
    from utils.youtube_config import get_youtube_credentials

    session = _sessions_by_id.get(session_id)
    if session is not None:
        return YouTubeAuthStatusResponse(status="pending")

    creds = await get_youtube_credentials(sql_session)
    if creds.get("token"):
        return YouTubeAuthStatusResponse(status="success")

    return YouTubeAuthStatusResponse(status="failed", detail="No credentials stored")


@VIDEO_STUDIO_ROUTER.post("/youtube/auth/exchange", response_model=YouTubeAuthStatusResponse)
async def exchange_youtube_code(
    body: ExchangeYouTubeAuthRequest,
    sql_session: AsyncSession = Depends(get_async_session),
):
    """Manual code exchange fallback."""
    session = _sessions_by_id.pop(body.session_id, None)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or already consumed")

    _sessions_by_state.pop(session.get("state", ""), None)

    try:
        token_data = exchange_authorization_code(
            code=body.code,
            verifier=session["verifier"],
            client_id=session["client_id"],
            client_secret=session.get("client_secret"),
            redirect_uri=session.get("redirect_uri"),
        )
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        expires_ms = int(datetime.now().timestamp() * 1000) + int(expires_in) * 1000

        await set_youtube_credentials(
            session=sql_session,
            access_token=access_token,
            refresh_token=refresh_token or "",
            expires_ms=expires_ms,
            client_id=session["client_id"],
            client_secret=session.get("client_secret") or "",
        )

        return YouTubeAuthStatusResponse(status="success")
    except Exception as exc:
        return YouTubeAuthStatusResponse(status="failed", detail=str(exc))


@VIDEO_STUDIO_ROUTER.get("/youtube/auth/status", response_model=YouTubeAuthStatusResponse)
async def get_youtube_auth_status(
    sql_session: AsyncSession = Depends(get_async_session),
):
    """Return whether valid YouTube credentials are currently stored."""
    from utils.youtube_config import get_youtube_credentials, is_youtube_token_expired

    creds = await get_youtube_credentials(sql_session)
    if not creds.get("token"):
        return YouTubeAuthStatusResponse(status="not_authenticated")

    if await is_youtube_token_expired(sql_session):
        return YouTubeAuthStatusResponse(status="expired", detail="Token expired — re-authenticate")

    return YouTubeAuthStatusResponse(status="authenticated")


@VIDEO_STUDIO_ROUTER.post("/youtube/auth/logout", response_model=YouTubeAuthStatusResponse)
async def logout_youtube(
    sql_session: AsyncSession = Depends(get_async_session),
):
    """Clear stored YouTube credentials."""
    await clear_youtube_credentials(sql_session)
    return YouTubeAuthStatusResponse(status="logged_out")


# FastAPI HTMLResponse is imported lazily to keep the file dependency-light.
from fastapi.responses import HTMLResponse  # noqa: E402
