"""Tests for gitstory.render: the HTML is self-contained and safe to embed data in."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from gitstory.parser import Commit, FileChange
from gitstory.render import render_report, to_script_safe_json, write_report
from gitstory.stats import build_report

NASTY = "</script><script>alert('pwned')</script> <!-- & \u2028 {{JS}} {{DATA}}"


def _report(message: str = "Initial commit", repo_name: str = "demo"):
    commit = Commit(
        hash="f" * 40,
        author_name="Ada <b>Lovelace</b>",
        author_email="ada@example.com",
        timestamp=datetime(2024, 3, 4, 9, 30, tzinfo=timezone.utc),
        message=message,
        files=(FileChange("src/app.py", 10, 2),),
        parents=(),
    )
    return build_report([commit], repo_name)


def _embedded_data(document: str):
    match = re.search(r'<script id="gitstory-data" type="application/json">(.*?)</script>', document, re.S)
    assert match, "data blob not found"
    return json.loads(match.group(1))


def test_script_safe_json_escapes_html_sensitive_characters():
    encoded = to_script_safe_json({"message": NASTY})
    assert "<" not in encoded and ">" not in encoded and "&" not in encoded
    assert "\u2028" not in encoded
    assert json.loads(encoded) == {"message": NASTY}


def test_hostile_commit_message_cannot_break_out_of_the_data_block():
    document = render_report(_report(message=NASTY))
    assert "alert('pwned')</script>" not in document
    assert document.count("</script>") == 2  # the data block and the renderer, nothing else
    data = _embedded_data(document)
    assert data["messages"]["longest"]["text"] == NASTY
    assert data["contributors"][0]["name"] == "Ada <b>Lovelace</b>"


def test_report_is_self_contained():
    document = render_report(_report())
    assert document.startswith("<!DOCTYPE html>")
    assert "{{" not in document.split('<script id="gitstory-data"')[0]
    for pattern in (r'src\s*=\s*["\']?https?:', r'href\s*=\s*["\']?https?:', r"url\(\s*['\"]?https?:", r"@import", r"<link\b"):
        assert not re.search(pattern, document, re.I), pattern


def test_embedded_data_round_trips():
    data = _embedded_data(render_report(_report(), generated_at=datetime(2024, 3, 5, tzinfo=timezone.utc),
                                        filters={"since": "2024-01-01", "until": None, "author": None}))
    assert data["repo_name"] == "demo"
    assert data["summary"]["commits"] == 1
    assert data["summary"]["first_commit"] == "2024-03-04T09:30:00+00:00"
    assert data["timeline"][0]["start"] == "2024-03-04"
    assert len(data["heatmap"]) == 7 and data["heatmap"][0][9] == 1
    assert data["meta"]["generated_at"].startswith("2024-03-05")
    assert data["meta"]["filters"] == {"since": "2024-01-01"}


def test_emails_are_not_written_into_the_report():
    assert "ada@example.com" not in render_report(_report())


def test_theme_and_title():
    dark = render_report(_report(repo_name="a<b>&c"))
    assert '<html lang="en" data-theme="dark">' in dark
    assert "<title>a&lt;b&gt;&amp;c · gitstory</title>" in dark
    assert 'data-theme="light"' in render_report(_report(), theme="light")
    with pytest.raises(ValueError):
        render_report(_report(), theme="neon")


def test_write_report_creates_parent_folders(tmp_path):
    target = write_report("<p>café</p>", tmp_path / "nested" / "out.html")
    assert target.read_text(encoding="utf-8") == "<p>café</p>"
