import os
import tempfile
import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from models.sql.video_project import VideoProjectModel
from services.html_video_renderer import _ensure_even_dimension, render_html_to_video
from services.video_studio_service import (
    _generate_html_content,
    _mux_video_audio,
    _parse_resolution,
)
from utils.oauth.youtube import create_authorization_flow


SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
  body { margin: 0; background: #000; }
  .box { width: 100px; height: 100px; background: #fff; }
</style>
</head>
<body>
  <div class="box">Hello</div>
</body>
</html>
"""


class TestVideoStudioHelpers:
    def test_ensure_even_dimension(self):
        assert _ensure_even_dimension(1280) == 1280
        assert _ensure_even_dimension(721) == 722
        assert _ensure_even_dimension(1) == 2

    def test_parse_resolution(self):
        assert _parse_resolution("1920x1080") == (1920, 1080)
        assert _parse_resolution("1280x720") == (1280, 720)
        assert _parse_resolution("bad") == (1280, 720)
        assert _parse_resolution(None) == (1280, 720)

    def test_generate_html_content_fallback(self):
        project = VideoProjectModel(
            title="Test & Video",
            description="A <b>description</b>",
            style="bold",
            duration_seconds=5.0,
        )
        html = _generate_html_content(project)
        assert "Test & Video" in html
        assert "A &lt;b&gt;description&lt;/b&gt;" in html
        assert "<html" in html.lower()


class TestYouTubeOAuth:
    def test_create_authorization_flow(self):
        flow = create_authorization_flow("my-client-id")
        parsed = urlparse(flow.url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "accounts.google.com"
        qs = parse_qs(parsed.query)
        assert qs["client_id"] == ["my-client-id"]
        assert qs["response_type"] == ["code"]
        assert qs["scope"] == ["https://www.googleapis.com/auth/youtube.upload"]
        assert qs["code_challenge_method"] == ["S256"]
        assert qs["access_type"] == ["offline"]
        assert "code_challenge" in qs
        assert "state" in qs
        assert flow.state
        assert flow.verifier

    def test_custom_redirect_uri(self):
        flow = create_authorization_flow(
            "my-client-id",
            redirect_uri="http://example.com/callback",
        )
        parsed = urlparse(flow.url)
        qs = parse_qs(parsed.query)
        assert qs["redirect_uri"] == ["http://example.com/callback"]


@pytest.mark.anyio
class TestHtmlVideoRenderer:
    async def test_render_html_to_video_produces_mp4(self):
        """Integration test: Playwright + FFmpeg renders a simple HTML page to MP4."""
        try:
            import playwright  # noqa: F401
        except ImportError:
            pytest.skip("Playwright not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = os.path.join(tmpdir, "scene.html")
            output_path = os.path.join(tmpdir, "output.mp4")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_HTML)

            await render_html_to_video(
                html_path=html_path,
                output_path=output_path,
                width=320,
                height=240,
                duration_seconds=1.0,
                fps=10,
            )

            assert os.path.isfile(output_path)
            assert os.path.getsize(output_path) > 0

    async def test_mux_video_audio(self):
        """Smoke test for the mux helper using a silent video and generated silence."""
        from services.video_export_service import _generate_silent_audio_segment

        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = os.path.join(tmpdir, "scene.html")
            video_path = os.path.join(tmpdir, "video.mp4")
            audio_path = os.path.join(tmpdir, "audio.mp3")
            output_path = os.path.join(tmpdir, "muxed.mp4")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_HTML)

            await render_html_to_video(
                html_path=html_path,
                output_path=video_path,
                width=320,
                height=240,
                duration_seconds=1.0,
                fps=10,
            )
            await _generate_silent_audio_segment(audio_path, 1.0)
            await _mux_video_audio(video_path, audio_path, output_path)

            assert os.path.isfile(output_path)
            assert os.path.getsize(output_path) > 0
