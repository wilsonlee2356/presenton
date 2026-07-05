import asyncio
import logging
import os
import shutil
import tempfile

from fastapi import HTTPException

from services.video_export_service import _exec_ffmpeg

LOGGER = logging.getLogger(__name__)


def _ensure_even_dimension(value: int) -> int:
    """Return the nearest even integer >= value (required by many video codecs)."""
    return value if value % 2 == 0 else value + 1


async def render_html_to_video(
    html_path: str,
    output_path: str,
    width: int,
    height: int,
    duration_seconds: float,
    fps: int = 30,
) -> str:
    """
    Render a self-contained HTML file to an H.264 MP4 using Playwright + FFmpeg.

    The HTML is expected to drive its own animations (CSS/JS). The function records
    the browser viewport for ``duration_seconds`` and transcodes the resulting WebM
    to MP4 with yuv420p for broad compatibility.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Playwright is not installed. Run 'playwright install chromium'.",
        ) from exc

    width = _ensure_even_dimension(width)
    height = _ensure_even_dimension(height)
    temp_dir = tempfile.mkdtemp(prefix="presenton_html_video_")

    try:
        async with async_playwright() as playwright:
            launch_kwargs = {
                "headless": True,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            }
            # Prefer a system Chromium when available (e.g. Docker image).
            system_chromium = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or "/usr/bin/chromium"
            if os.path.isfile(system_chromium):
                launch_kwargs["executable_path"] = system_chromium
            browser = await playwright.chromium.launch(**launch_kwargs)
            context = await browser.new_context(
                viewport={"width": width, "height": height},
                record_video_dir=temp_dir,
                record_video_size={"width": width, "height": height},
            )
            page = await context.new_page()

            LOGGER.info(
                "[html_video_renderer] recording %sx%s for %.1fs from %s",
                width,
                height,
                duration_seconds,
                html_path,
            )
            await page.goto(f"file://{html_path}", wait_until="networkidle")
            await page.wait_for_timeout(int(duration_seconds * 1000))

            await context.close()
            await browser.close()

        webm_files = [f for f in os.listdir(temp_dir) if f.endswith(".webm")]
        if not webm_files:
            raise RuntimeError("Playwright did not produce a video file")

        webm_path = os.path.join(temp_dir, webm_files[0])
        LOGGER.info("[html_video_renderer] transcoding %s to %s", webm_path, output_path)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            webm_path,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-movflags",
            "+faststart",
            output_path,
        ]
        await _exec_ffmpeg(cmd)
        return output_path
    except Exception as exc:
        LOGGER.exception("[html_video_renderer] rendering failed")
        raise HTTPException(
            status_code=500, detail=f"Failed to render HTML video: {exc}"
        ) from exc
    finally:
        await asyncio.to_thread(shutil.rmtree, temp_dir, ignore_errors=True)
