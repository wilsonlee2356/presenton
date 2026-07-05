import asyncio
import os
import shutil
import tempfile

import pytest
from PIL import Image

from services.video_export_service import (
    _concatenate_audio_segments,
    _estimate_speaker_note_duration,
    _generate_silent_audio_segment,
    _get_audio_duration,
    _normalize_audio_segment,
    _run_ffmpeg,
    _which_ffmpeg,
    _which_ffprobe,
    MIN_SECONDS_PER_SLIDE,
    MAX_SECONDS_PER_SLIDE,
    PAUSE_BETWEEN_SLIDES,
)


async def _exec_ffmpeg(cmd: list[str]) -> None:
    """Test helper to run FFmpeg commands."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace")[-500:])


def _create_test_slides(temp_dir: str, count: int = 2) -> list[str]:
    image_paths = []
    for i in range(count):
        image_path = os.path.join(temp_dir, f"slide_{i}.png")
        image = Image.new("RGB", (1280, 720), color=(i * 80, i * 60, i * 120))
        image.save(image_path)
        image_paths.append(image_path)
    return image_paths


def _count_streams(mp4_path: str) -> tuple[int, int]:
    """Return (video_stream_count, audio_stream_count) using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    assert ffprobe, "ffprobe is required for stream count assertions"

    import subprocess

    video_count = 0
    audio_count = 0
    for stream_type, counter_ref in (("v", video_count), ("a", audio_count)):
        cmd = [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            stream_type,
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            mp4_path,
        ]
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if stream_type == "v":
            video_count = len(lines)
        else:
            audio_count = len(lines)
    return video_count, audio_count


@pytest.mark.anyio
async def test_which_ffmpeg_returns_path():
    path = await _which_ffmpeg()
    assert path
    assert os.path.isfile(path)


@pytest.mark.anyio
async def test_which_ffprobe_returns_path():
    path = await _which_ffprobe()
    assert path
    assert os.path.isfile(path)


@pytest.mark.anyio
async def test_run_ffmpeg_produces_silent_mp4():
    with tempfile.TemporaryDirectory() as temp_dir:
        image_paths = _create_test_slides(temp_dir)
        output_path = os.path.join(temp_dir, "output.mp4")
        await _run_ffmpeg(image_paths, output_path, seconds_per_slide=0.5, fps=10)

        assert os.path.isfile(output_path)
        assert os.path.getsize(output_path) > 0
        video_count, audio_count = _count_streams(output_path)
        assert video_count == 1
        assert audio_count == 0


@pytest.mark.anyio
async def test_run_ffmpeg_with_audio_produces_mp4_with_audio():
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required"

    with tempfile.TemporaryDirectory() as temp_dir:
        image_paths = _create_test_slides(temp_dir, count=2)
        seconds_per_slide = 0.5

        # Build a silent AAC audio track equal to the total video duration.
        audio_track = os.path.join(temp_dir, "audio.aac")
        await _exec_ffmpeg(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono",
                "-t",
                str(len(image_paths) * seconds_per_slide),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                audio_track,
            ]
        )

        output_path = os.path.join(temp_dir, "output_with_audio.mp4")
        await _run_ffmpeg(
            image_paths,
            output_path,
            seconds_per_slide=seconds_per_slide,
            fps=10,
            audio_path=audio_track,
        )

        assert os.path.isfile(output_path)
        assert os.path.getsize(output_path) > 0
        video_count, audio_count = _count_streams(output_path)
        assert video_count == 1
        assert audio_count == 1


@pytest.mark.anyio
async def test_get_audio_duration_returns_expected_value():
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg

    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = os.path.join(temp_dir, "tone.mp3")
        await _exec_ffmpeg(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:duration=0.75",
                "-c:a",
                "libmp3lame",
                audio_path,
            ]
        )

        duration = await _get_audio_duration(audio_path)
        assert duration is not None
        assert abs(duration - 0.75) < 0.1


@pytest.mark.anyio
async def test_normalize_audio_segment_pads_short_clip():
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg

    with tempfile.TemporaryDirectory() as temp_dir:
        short_clip = os.path.join(temp_dir, "short.mp3")
        await _exec_ffmpeg(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:duration=0.2",
                "-c:a",
                "libmp3lame",
                short_clip,
            ]
        )

        normalized = os.path.join(temp_dir, "normalized.mp3")
        await _normalize_audio_segment(short_clip, normalized, duration=0.5)

        normalized_duration = await _get_audio_duration(normalized)
        assert normalized_duration is not None
        assert abs(normalized_duration - 0.5) < 0.05


@pytest.mark.anyio
async def test_normalize_audio_segment_truncates_long_clip():
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg

    with tempfile.TemporaryDirectory() as temp_dir:
        long_clip = os.path.join(temp_dir, "long.mp3")
        await _exec_ffmpeg(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:duration=1.2",
                "-c:a",
                "libmp3lame",
                long_clip,
            ]
        )

        normalized = os.path.join(temp_dir, "normalized.mp3")
        await _normalize_audio_segment(long_clip, normalized, duration=0.5)

        normalized_duration = await _get_audio_duration(normalized)
        assert normalized_duration is not None
        assert abs(normalized_duration - 0.5) < 0.05


@pytest.mark.anyio
async def test_generate_silent_audio_segment_has_expected_duration():
    with tempfile.TemporaryDirectory() as temp_dir:
        silent = os.path.join(temp_dir, "silent.mp3")
        await _generate_silent_audio_segment(silent, duration=0.75)

        duration = await _get_audio_duration(silent)
        assert duration is not None
        assert abs(duration - 0.75) < 0.05


@pytest.mark.anyio
async def test_concatenate_audio_segments_joins_clips():
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg

    with tempfile.TemporaryDirectory() as temp_dir:
        segments = []
        for i in range(3):
            segment = os.path.join(temp_dir, f"seg_{i}.mp3")
            await _exec_ffmpeg(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"sine=frequency={500 + i * 200}:duration=0.3",
                    "-c:a",
                    "libmp3lame",
                    segment,
                ]
            )
            segments.append(segment)

        output = os.path.join(temp_dir, "concat.aac")
        await _concatenate_audio_segments(segments, output)

        duration = await _get_audio_duration(output)
        assert duration is not None
        assert abs(duration - 0.9) < 0.1


async def _make_synthetic_mp3(path: str, duration_s: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    await _exec_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:duration={duration_s}",
            "-c:a",
            "libmp3lame",
            path,
        ]
    )


def _get_video_duration(mp4_path: str) -> float:
    ffprobe = shutil.which("ffprobe")
    assert ffprobe, "ffprobe is required"

    import subprocess

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        mp4_path,
    ]
    output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
    return float(output.strip())


@pytest.mark.anyio
async def test_build_speaker_note_audio_track_returns_durations():
    from services.video_export_service import _build_speaker_note_audio_track

    with tempfile.TemporaryDirectory() as temp_dir:
        notes = ["First note", "Second note with more words"]
        clips = [
            os.path.join(temp_dir, "clip0.mp3"),
            os.path.join(temp_dir, "clip1.mp3"),
        ]
        await _make_synthetic_mp3(clips[0], 0.5)
        await _make_synthetic_mp3(clips[1], 0.9)

        audio_track, durations = await _build_speaker_note_audio_track(
            notes, clips, pause_between_slides=0.25, min_seconds_per_slide=0.4
        )

        assert os.path.isfile(audio_track)
        assert len(durations) == len(notes)
        # First slide: max(0.5, 0.4) + 0.25 = 0.75
        assert abs(durations[0] - 0.75) < 0.05
        # Second (last) slide: max(0.9, 0.4) + 0 = 0.9
        assert abs(durations[1] - 0.9) < 0.05

        track_duration = await _get_audio_duration(audio_track)
        assert track_duration is not None
        assert abs(track_duration - sum(durations)) < 0.2


@pytest.mark.anyio
async def test_run_ffmpeg_with_variable_durations_produces_mp4():
    with tempfile.TemporaryDirectory() as temp_dir:
        image_paths = _create_test_slides(temp_dir, count=2)
        output_path = os.path.join(temp_dir, "output_variable.mp4")
        slide_durations = [0.5, 1.2]
        await _run_ffmpeg(
            image_paths,
            output_path,
            slide_durations=slide_durations,
            fps=10,
        )

        assert os.path.isfile(output_path)
        assert os.path.getsize(output_path) > 0
        video_count, audio_count = _count_streams(output_path)
        assert video_count == 1
        assert audio_count == 0
        duration = _get_video_duration(output_path)
        assert abs(duration - sum(slide_durations)) < 0.3


@pytest.mark.anyio
async def test_run_ffmpeg_with_variable_durations_and_audio():
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required"

    with tempfile.TemporaryDirectory() as temp_dir:
        image_paths = _create_test_slides(temp_dir, count=2)
        slide_durations = [0.6, 1.0]

        audio_track = os.path.join(temp_dir, "audio.aac")
        await _exec_ffmpeg(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono",
                "-t",
                str(sum(slide_durations)),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                audio_track,
            ]
        )

        output_path = os.path.join(temp_dir, "output_variable_audio.mp4")
        await _run_ffmpeg(
            image_paths,
            output_path,
            slide_durations=slide_durations,
            fps=10,
            audio_path=audio_track,
        )

        assert os.path.isfile(output_path)
        video_count, audio_count = _count_streams(output_path)
        assert video_count == 1
        assert audio_count == 1


def test_estimate_speaker_note_duration_uses_word_count():
    # 10 words at 2.5 words/sec = 4 seconds, clamped to min of 3 -> 4
    duration = _estimate_speaker_note_duration("one two three four five six seven eight nine ten")
    assert abs(duration - 4.0) < 0.01
    assert duration >= MIN_SECONDS_PER_SLIDE


def test_estimate_speaker_note_duration_clamps_to_max():
    long_note = "word " * 200  # 200 words -> 80 seconds, clamped to MAX
    duration = _estimate_speaker_note_duration(long_note)
    assert duration == MAX_SECONDS_PER_SLIDE


def test_estimate_speaker_note_duration_empty_note():
    assert _estimate_speaker_note_duration("") == MIN_SECONDS_PER_SLIDE
    assert _estimate_speaker_note_duration("   ") == MIN_SECONDS_PER_SLIDE


def test_estimate_speaker_note_duration_non_space_languages():
    # CJK text without spaces uses character count.
    duration = _estimate_speaker_note_duration("一二三四五六七八九十")
    assert abs(duration - 10 / CHARS_PER_SECOND) < 0.01


@pytest.mark.anyio
async def test_build_srt_audio_track_places_clips_at_timestamps():
    from services.video_export_service import _build_srt_audio_track

    with tempfile.TemporaryDirectory() as temp_dir:
        entries = [
            {"index": 1, "start_ms": 0, "end_ms": 1000, "duration_ms": 1000, "text": "A"},
            {"index": 2, "start_ms": 2000, "end_ms": 3000, "duration_ms": 1000, "text": "B"},
        ]
        clips = [
            os.path.join(temp_dir, "clip0.mp3"),
            os.path.join(temp_dir, "clip1.mp3"),
        ]
        for clip in clips:
            await _make_synthetic_mp3(clip, 0.8)

        audio_track = await _build_srt_audio_track(entries, clips, total_duration_ms=3500)

        assert os.path.isfile(audio_track)
        duration = await _get_audio_duration(audio_track)
        assert duration is not None
        # The base track is 3.5 s; encoding may add a small MP3/AAC padding tail.
        assert duration >= 3.4
        assert duration <= 4.2


@pytest.mark.anyio
async def test_run_ffmpeg_with_srt_audio_produces_mp4_with_audio():
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg

    with tempfile.TemporaryDirectory() as temp_dir:
        from services.video_export_service import _build_srt_audio_track

        image_paths = _create_test_slides(temp_dir, count=1)
        entries = [
            {"index": 1, "start_ms": 0, "end_ms": 1000, "duration_ms": 1000, "text": "A"},
        ]
        clip = os.path.join(temp_dir, "clip.mp3")
        await _make_synthetic_mp3(clip, 0.8)

        audio_track = await _build_srt_audio_track(entries, [clip], total_duration_ms=1000)
        output_path = os.path.join(temp_dir, "output_srt.mp4")
        await _run_ffmpeg(image_paths, output_path, seconds_per_slide=1.0, fps=10, audio_path=audio_track)

        assert os.path.isfile(output_path)
        video_count, audio_count = _count_streams(output_path)
        assert video_count == 1
        assert audio_count == 1
