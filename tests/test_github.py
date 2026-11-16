"""Tests for gitstory.github: reading links, progress lines and clone errors."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gitstory.github import (
    CloneError,
    GitHubRepo,
    InvalidRepositoryURL,
    clone_repository,
    explain_clone_failure,
    looks_like_github_url,
    parse_github_url,
    parse_progress,
)
from gitstory.parser import read_commits

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@pytest.mark.parametrize("text", [
    "https://github.com/psf/requests",
    "https://github.com/psf/requests/",
    "https://github.com/psf/requests.git",
    "http://www.github.com/psf/requests",
    "github.com/psf/requests",
    "  https://github.com/psf/requests  ",
    "https://github.com/psf/requests/tree/main/src/requests",
    "https://github.com/psf/requests/blob/main/README.md#install",
    "https://github.com/psf/requests?tab=readme-ov-file",
    "git@github.com:psf/requests.git",
    "ssh://git@github.com/psf/requests.git",
    "psf/requests",
])
def test_parse_github_url_accepts_what_people_paste(text):
    assert parse_github_url(text) == GitHubRepo("psf", "requests")


def test_parse_github_url_keeps_dots_and_case():
    repo = parse_github_url("https://github.com/Microsoft/vscode.dev")
    assert (repo.owner, repo.name, repo.slug) == ("Microsoft", "vscode.dev", "Microsoft/vscode.dev")
    assert repo.web_url == "https://github.com/Microsoft/vscode.dev"
    assert repo.clone_url == "https://github.com/Microsoft/vscode.dev.git"


@pytest.mark.parametrize("text", [
    "", "   ", "requests", "https://gitlab.com/psf/requests", "https://github.com/psf",
    "https://github.com/", "file:///etc/passwd", "/home/me/project", "../secret/repo",
    "https://github.com/-bad/repo", "https://github.com/psf/..", "https://evilgithub.com/psf/requests",
    "https://github.com.evil.example/psf/requests", "--upload-pack=touch/x",
])
def test_parse_github_url_rejects_everything_else(text):
    with pytest.raises(InvalidRepositoryURL):
        parse_github_url(text)


def test_shorthand_can_be_disabled():
    with pytest.raises(InvalidRepositoryURL):
        parse_github_url("psf/requests", allow_shorthand=False)


def test_looks_like_github_url():
    assert looks_like_github_url("https://GitHub.com/psf/requests")
    assert not looks_like_github_url("psf/requests")
    assert not looks_like_github_url("./my-project")


def test_parse_progress():
    assert parse_progress("Receiving objects:  45% (450/1000), 3.20 MiB | 1.10 MiB/s") == ("Receiving", 45, "3.20 MiB")
    assert parse_progress("Resolving deltas: 100% (1700/1700), done.") == ("Resolving", 100, "")
    assert parse_progress("remote: Counting objects:   7% (3/40)") == ("Counting", 7, "")
    assert parse_progress("Cloning into bare repository 'x'...") is None


def test_explain_clone_failure():
    repo = GitHubRepo("octocat", "nope")
    missing = "remote: Repository not found.\nfatal: repository 'https://github.com/octocat/nope.git/' not found"
    assert explain_clone_failure(missing, repo).startswith("octocat/nope was not found on GitHub")
    prompt = "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
    assert "was not found" in explain_clone_failure(prompt, repo)
    offline = "fatal: unable to access 'https://github.com/x/y.git/': Could not resolve host: github.com"
    assert "could not reach github.com" in explain_clone_failure(offline, repo)
    assert explain_clone_failure("Receiving objects: 10%\nfatal: something odd", repo) == "git clone failed: fatal: something odd"


def _make_origin(path: Path) -> Path:
    env = dict(os.environ, GIT_AUTHOR_NAME="A", GIT_AUTHOR_EMAIL="a@example.com", GIT_COMMITTER_NAME="A",
               GIT_COMMITTER_EMAIL="a@example.com", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    path.mkdir()
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True, env=env)
    for i in range(3):
        (path / "notes.txt").write_text("line\n" * (i + 1), encoding="utf-8")
        subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", f"commit {i}"], check=True, env=env)
    return path


@needs_git
def test_clone_repository_from_a_local_origin(tmp_path: Path):
    origin = _make_origin(tmp_path / "origin")
    calls = []
    clone = clone_repository(GitHubRepo("me", "origin"), tmp_path / "clone.git",
                             on_progress=lambda *args: calls.append(args), url=str(origin))
    assert [c.subject for c in read_commits(clone)] == ["commit 2", "commit 1", "commit 0"]


@needs_git
def test_clone_repository_failure_is_explained(tmp_path: Path):
    with pytest.raises(CloneError) as error:
        clone_repository(GitHubRepo("me", "missing"), tmp_path / "clone.git", url=str(tmp_path / "missing"))
    assert "git clone failed" in str(error.value) or "not found" in str(error.value)
