import re
from typing import Any


_SRT_TIME_RE = re.compile(
    r"^(\d{1,2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2}),(\d{3})$"
)


def _parse_srt_time(hours: str, minutes: str, seconds: str, millis: str) -> int:
    return (
        int(hours) * 3600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + int(millis)
    )


def parse_srt(content: str) -> list[dict[str, Any]]:
    """
    Parse SRT subtitle content into a list of entries.

    Each entry has ``index``, ``start_ms``, ``end_ms``, and ``text``.
    """
    entries: list[dict[str, Any]] = []
    if not content or not content.strip():
        return entries

    blocks = re.split(r"\n\s*\n", content.strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue

        # Some SRT files omit the index line; accept both shapes.
        time_line_index = 0
        try:
            int(lines[0])
            time_line_index = 1
        except ValueError:
            pass

        if time_line_index >= len(lines):
            continue

        match = _SRT_TIME_RE.match(lines[time_line_index])
        if not match:
            continue

        start_ms = _parse_srt_time(*match.groups()[:4])
        end_ms = _parse_srt_time(*match.groups()[4:])
        text = " ".join(lines[time_line_index + 1 :]).strip()

        entries.append(
            {
                "index": len(entries) + 1,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text,
                "duration_ms": max(0, end_ms - start_ms),
            }
        )

    return entries
