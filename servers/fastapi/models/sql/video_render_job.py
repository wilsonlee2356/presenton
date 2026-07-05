from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import JSON, Column, DateTime, String
from sqlmodel import Field, SQLModel

from utils.datetime_utils import get_current_utc_datetime


class VideoRenderJobModel(SQLModel, table=True):
    """A single render or upload job for a video project."""

    __tablename__ = "video_render_jobs"

    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)
    project_id: uuid.UUID = Field(foreign_key="video_projects.id", index=True)
    job_type: str = Field(
        sa_column=Column(String), default="render"
    )  # render | upload

    status: str = Field(
        sa_column=Column(String), default="pending"
    )  # pending | running | completed | failed
    stage: Optional[str] = Field(
        sa_column=Column(String), default=None
    )  # generating_html | rendering_video | synthesizing_audio | muxing | uploading
    progress: int = Field(default=0)
    message: Optional[str] = Field(sa_column=Column(String), default=None)
    error: Optional[dict] = Field(sa_column=Column(JSON), default=None)

    output_path: Optional[str] = Field(sa_column=Column(String), default=None)
    youtube_video_id: Optional[str] = Field(sa_column=Column(String), default=None)

    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), nullable=False, default=get_current_utc_datetime
        ),
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            default=get_current_utc_datetime,
            onupdate=get_current_utc_datetime,
        ),
    )
    completed_at: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True)), default=None
    )
