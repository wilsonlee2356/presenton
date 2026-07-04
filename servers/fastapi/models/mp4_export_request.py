from typing import Literal, Optional

from pydantic import BaseModel, Field


class Mp4ExportRequest(BaseModel):
    """Optional parameters for exporting a presentation as an MP4 video."""

    include_narration: bool = Field(
        default=True,
        description="Generate narration audio for the video.",
    )
    narration_source: Literal["speaker_notes", "srt"] = Field(
        default="speaker_notes",
        description="Source of narration text: slide speaker notes or an uploaded SRT file.",
    )
    chatterbox_url: str = Field(
        default="http://127.0.0.1:8001",
        description="Base URL of the Chatterbox TTS server.",
    )
    voice_mode: Literal["predefined", "clone"] = Field(
        default="predefined",
        description="Chatterbox voice mode.",
    )
    predefined_voice_id: Optional[str] = Field(
        default=None,
        description="Filename of the predefined Chatterbox voice to use.",
    )
    reference_audio_filename: Optional[str] = Field(
        default=None,
        description="Filename of the reference audio for voice cloning.",
    )
    output_format: Literal["wav", "mp3", "opus"] = Field(
        default="wav",
        description="Audio format returned by Chatterbox.",
    )
    speed_factor: Optional[float] = Field(
        default=None,
        description="Optional Chatterbox speed factor.",
    )
    language: Optional[str] = Field(
        default=None,
        description="Optional language hint for Chatterbox.",
    )
    srt_content: Optional[str] = Field(
        default=None,
        description="Raw SRT file content when narration_source is 'srt'.",
    )
