"""Tests for gitstory.parser, using a fixed sample of ``git log`` output."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gitstory.parser import (
    FIELD_SEP,
    RECORD_SEP,
    build_log_command,
    parse_git_log,
    parse_numstat_line,
    parse_raw_date,
    split_rename,
)

H1, H2, H3, H4 = "a" * 40, "b" * 40, "c" * 40, "d" * 40


def record(commit_hash: str, name: str, email: str, date: str, parents: str, message: str, numstat: str = "") -> str:
    """Build one record exactly the way ``git log`` prints it with our format."""
    return RECORD_SEP + FIELD_SEP.join([commit_hash, name, email, date, parents, message, ""]) + numstat


SAMPLE_LOG = "\n".join(
    [
        record(
            H4, "Grace Hopper", "grace@example.com", "1709820000 -0500", f"{H3} {H2}",
            "Merge branch 'feature/parser'\n",
        ),
        record(
            H3, "Ada Lovelace", "ada@example.com", "1709812800 +0530", H2,
            "feat(parser): handle </script> in messages\n\nA longer body\nwith two lines.\n",
            "\n12\t3\tgitstory/parser.py\n-\t-\tdocs/screenshot.png\n0\t0\tsrc/{old => new}/util.py\n",
        ),
        record(
            H2, "Ada Lovelace", "ada@example.com", "1709726400 +0530", H1,
            "Rename the readme �\n",
            "\n4\t1\tREADME.txt => README.md\n",
        ),
        record(
            H1, "Linus", "linus@example.com", "1709640000 +0000", "",
            "Initial commit\n",
            "\n100\t0\tREADME.txt\n7\t0\t\"caf\\303\\251 menu.txt\"\n",
        ),
    ]
)


@pytest.fixture()
def commits():
    return parse_git_log(SAMPLE_LOG)


def test_parses_every_commit_in_order(commits):
    assert [c.hash for c in commits] == [H4, H3, H2, H1]
    assert [c.author_name for c in commits] == ["Grace Hopper", "Ada Lovelace", "Ada Lovelace", "Linus"]
    assert commits[1].author_email == "ada@example.com"
    assert commits[1].short_hash == "c" * 7


def test_subject_and_body_are_split(commits):
    commit = commits[1]
    assert commit.subject == "feat(parser): handle </script> in messages"
    assert commit.body == "A longer body\nwith two lines."


def test_timestamps_keep_the_authors_timezone(commits):
    ist = commits[1].timestamp
    assert ist.utcoffset() == timedelta(hours=5, minutes=30)
    assert ist == datetime.fromtimestamp(1709812800, tz=timezone.utc)
    assert commits[0].timestamp.utcoffset() == timedelta(hours=-5)
    # 2024-03-07 12:00 UTC is 17:30 in +05:30.
    assert (ist.hour, ist.minute) == (17, 30)


def test_merge_commit_has_two_parents_and_no_files(commits):
    merge = commits[0]
    assert merge.is_merge
    assert merge.parents == (H3, H2)
    assert merge.files == ()
    assert merge.lines_changed == 0
    assert not commits[1].is_merge
    assert commits[3].parents == ()


def test_numstat_lines_and_totals(commits):
    commit = commits[1]
    assert [f.path for f in commit.files] == ["gitstory/parser.py", "docs/screenshot.png", "src/new/util.py"]
    assert (commit.lines_added, commit.lines_removed, commit.lines_changed) == (12, 3, 15)


def test_binary_files_count_zero_lines(commits):
    binary = commits[1].files[1]
    assert binary.binary
    assert (binary.added, binary.removed) == (0, 0)


def test_renames_resolve_to_the_new_path(commits):
    brace = commits[1].files[2]
    assert (brace.path, brace.old_path) == ("src/new/util.py", "src/old/util.py")
    assert brace.is_rename
    plain = commits[2].files[0]
    assert (plain.path, plain.old_path, plain.added, plain.removed) == ("README.md", "README.txt", 4, 1)
    assert not commits[3].files[0].is_rename


def test_quoted_paths_are_unescaped(commits):
    assert commits[3].files[1].path == "café menu.txt"


def test_undecodable_bytes_survive_as_replacement_characters(commits):
    assert "�" in commits[2].subject


def test_separator_inside_a_message_does_not_split_the_commit():
    log = record(H1, "A", "a@example.com", "1709640000 +0000", "", f"odd {FIELD_SEP} message {RECORD_SEP} here\n",
                 "\n1\t1\ta.py\n")
    (commit,) = parse_git_log(log)
    assert commit.subject.startswith("odd")
    assert commit.files[0].path == "a.py"


def test_empty_and_garbage_input():
    assert parse_git_log("") == []
    assert parse_git_log("not a git log at all") == []


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("a.py", ("a.py", None)),
        ("old.py => new.py", ("new.py", "old.py")),
        ("src/{old => new}/f.py", ("src/new/f.py", "src/old/f.py")),
        ("src/{ => lib}/f.py", ("src/lib/f.py", "src/f.py")),
        ("{a => b}/f.py", ("b/f.py", "a/f.py")),
        ("pkg/{mod.py => mod/__init__.py}", ("pkg/mod/__init__.py", "pkg/mod.py")),
    ],
)
def test_split_rename(raw, expected):
    assert split_rename(raw) == expected


def test_parse_numstat_line_rejects_noise():
    assert parse_numstat_line("") is None
    assert parse_numstat_line("just some text") is None
    assert parse_numstat_line("x\ty\tfile") is None


def test_parse_raw_date_edge_cases():
    assert parse_raw_date("0 +0000") == datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert parse_raw_date("-86400 +0000") == datetime(1969, 12, 31, tzinfo=timezone.utc)
    assert parse_raw_date("1709640000").utcoffset() == timedelta(0)
    assert parse_raw_date("nonsense") == datetime(1970, 1, 1, tzinfo=timezone.utc)


def test_build_log_command_passes_filters_through():
    command = build_log_command("repo", since="2024-01-01", until="1 week ago", author="ada")
    assert command[:3] == ["git", "-C", "repo"]
    assert "--numstat" in command
    assert "--since=2024-01-01" in command
    assert "--until=1 week ago" in command
    assert "--author=ada" in command
    assert not any(arg.startswith("--since") for arg in build_log_command("repo"))
