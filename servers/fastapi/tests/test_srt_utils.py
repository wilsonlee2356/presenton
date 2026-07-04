from utils.srt_utils import parse_srt


def test_parse_srt_with_index_lines():
    content = """1
00:00:01,000 --> 00:00:04,500
Hello world

2
00:00:05,000 --> 00:00:07,000
Second entry
"""
    entries = parse_srt(content)
    assert len(entries) == 2
    assert entries[0]["index"] == 1
    assert entries[0]["start_ms"] == 1000
    assert entries[0]["end_ms"] == 4500
    assert entries[0]["duration_ms"] == 3500
    assert entries[0]["text"] == "Hello world"
    assert entries[1]["start_ms"] == 5000
    assert entries[1]["end_ms"] == 7000


def test_parse_srt_without_index_lines():
    content = """00:00:01,000 --> 00:00:03,000
Only text here
"""
    entries = parse_srt(content)
    assert len(entries) == 1
    assert entries[0]["start_ms"] == 1000
    assert entries[0]["text"] == "Only text here"


def test_parse_srt_multiline_text():
    content = """1
00:00:01,000 --> 00:00:04,000
Line one
Line two
"""
    entries = parse_srt(content)
    assert len(entries) == 1
    assert entries[0]["text"] == "Line one Line two"


def test_parse_srt_empty_content():
    assert parse_srt("") == []
    assert parse_srt("   \n\n  ") == []
