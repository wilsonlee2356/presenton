from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import JSON, Column, DateTime, String
from sqlmodel import Field, SQLModel

from utils.datetime_utils import get_current_utc_datetime


class VideoProjectModel(SQLModel, table=True):
    """A user-created video project based on HTML animations."""

    __tablename__ = "video_projects"

    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)
    title: str = Field(sa_column=Column(String, nullable=False))
    description: Optional[str] = Field(sa_column=Column(String), default=None)
    prompt: Optional[str] = Field(sa_column=Column(String), default=None)

    template: Optional[str] = Field(sa_column=Column(String), default="default")
    style: Optional[str] = Field(sa_column=Column(String), default=None)
    resolution: Optional[str] = Field(
        sa_column=Column(String), default="1280x720"
    )
    fps: int = Field(default=30)
    duration_seconds: Optional[float] = Field(default=None)

    narration_source: Optional[str] = Field(
        sa_column=Column(String), default="script"
    )
    narration_text: Optional[str] = Field(sa_column=Column(String), default=None)
    srt_content: Optional[str] = Field(sa_column=Column(String), default=None)

    chatterbox_config: Optional[dict] = Field(
        sa_column=Column(JSON), default=None
    )
    youtube_config: Optional[dict] = Field(
        sa_column=Column(JSON), default=None
    )

    status: str = Field(sa_column=Column(String), default="draft")
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
