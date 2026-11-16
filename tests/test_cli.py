"""End-to-end tests: build a real repository in a temp folder and run the CLI on it."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gitstory import cli, parser

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def git(repo: Path, *args: str, date: str = "2024-03-04T10:00:00+02:00") -> None:
    env = dict(os.environ, **GIT_ENV, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "sample-repo"
    path.mkdir()
    git(path, "init", "-q")
    (path / "hello.py").write_text("print('hello')\nprint('world')\n", encoding="utf-8")
    (path / "logo.bin").write_bytes(bytes(range(256)) * 4)
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "feat: say hello", date="2024-03-04T10:00:00+02:00")
    git(path, "mv", "hello.py", "greeting.py")
    (path / "greeting.py").write_text("print('hello')\nprint('world')\nprint('again')\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "Rename hello to greeting </script>", date="2024-03-05T23:30:00-05:00")
    return path


@needs_git
def test_read_commits_from_a_real_repository(repo: Path):
    newest, oldest = parser.read_commits(repo)
    assert oldest.subject == "feat: say hello"
    assert {f.path: (f.added, f.binary) for f in oldest.files} == {"hello.py": (2, False), "logo.bin": (0, True)}
    assert newest.author_name == "Test Author"
    assert newest.timestamp.utcoffset().total_seconds() == -5 * 3600
    (renamed,) = newest.files
    assert (renamed.path, renamed.old_path, renamed.added) == ("greeting.py", "hello.py", 1)
    assert parser.get_repo_name(repo) == "sample-repo"


@needs_git
def test_cli_writes_a_report(repo: Path, tmp_path: Path, capsys):
    output = tmp_path / "out" / "report.html"
    assert cli.main([str(repo), "-o", str(output), "--theme", "light"]) == 0
    document = output.read_text(encoding="utf-8")
    assert 'data-theme="light"' in document
    assert "sample-repo" in document
    assert "2 commits" in capsys.readouterr().out


@needs_git
def test_cli_filters_are_passed_to_git(repo: Path, tmp_path: Path, capsys):
    output = tmp_path / "report.html"
    assert cli.main([str(repo), "-o", str(output), "--until", "2024-03-04T23:00:00+02:00"]) == 0
    assert "1 commits" in capsys.readouterr().out
    assert cli.main([str(repo), "-o", str(output), "--author", "nobody-by-this-name"]) == 1
    assert "no commits match" in capsys.readouterr().err


@needs_git
def test_cli_reports_a_folder_that_is_not_a_repository(tmp_path: Path, capsys):
    assert cli.main([str(tmp_path), "-o", str(tmp_path / "x.html")]) == 1
    assert "not a git repository" in capsys.readouterr().err
    assert not (tmp_path / "x.html").exists()


@needs_git
def test_cli_reports_a_repository_without_commits(tmp_path: Path, capsys):
    git(tmp_path, "init", "-q")
    assert cli.main([str(tmp_path), "-o", str(tmp_path / "x.html")]) == 1
    assert "no commits yet" in capsys.readouterr().err


def test_cli_reports_a_missing_path(tmp_path: Path, capsys):
    assert cli.main([str(tmp_path / "does-not-exist")]) == 1
    assert "gitstory: error:" in capsys.readouterr().err


def test_cli_reports_missing_git(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr(parser.shutil, "which", lambda name: None)
    assert cli.main([str(tmp_path)]) == 1
    assert "git was not found" in capsys.readouterr().err


def test_cli_defaults():
    args = cli.build_parser().parse_args([])
    assert (args.repo, args.output, args.theme, args.open_report) == (".", "gitstory.html", "dark", False)
    assert (args.since, args.until, args.author) == (None, None, None)
