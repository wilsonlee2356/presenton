from pydantic import BaseModel, Field


class Mp4ExportRequest(BaseModel):
    """Optional parameters for exporting a presentation as an MP4 video."""

    include_narration: bool = Field(
        default=True,
        description="Generate TTS narration from each slide's speaker notes.",
    )
    voice: str = Field(
        default="alloy",
        description="OpenAI TTS voice to use for narration.",
    )
