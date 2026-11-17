"""Turn a GitHub link into a local clone that gitstory can read.

:func:`parse_github_url` is pure and accepts the forms people actually paste
(full URLs, ``.git`` URLs, links to a file or branch, SSH remotes and the
``owner/repo`` shorthand). :func:`clone_repository` runs ``git clone`` and
reports progress as it goes.

Only ``github.com`` is accepted. That keeps the web mode from being used to
read local paths or arbitrary servers.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Union

from .parser import GitNotFoundError, GitStoryError, ensure_git_available

_OWNER = r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))"
_NAME = r"(?P<name>[A-Za-z0-9._-]{1,100})"
_FULL_URL = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/" + _OWNER + "/" + _NAME + r"(?:/.*)?$", re.IGNORECASE)
_SSH_URL = re.compile(r"^(?:ssh://)?git@github\.com[:/]" + _OWNER + "/" + _NAME + r"/?$", re.IGNORECASE)
_SHORTHAND = re.compile(r"^" + _OWNER + "/" + _NAME + r"$")
_PROGRESS = re.compile(r"(?P<phase>Counting|Compressing|Receiving|Resolving) (?:objects|deltas):\s+(?P<percent>\d+)%(?P<rest>.*)")
_SIZE = re.compile(r"(\d+(?:\.\d+)?\s*[KMG]iB)")

ProgressCallback = Callable[[str, Optional[int], str], None]
"""Called with ``(phase, percent, detail)`` while a clone is running."""


class InvalidRepositoryURL(GitStoryError):
    """The text does not look like a GitHub repository link."""


class CloneError(GitStoryError):
    """``git clone`` failed or took too long."""


@dataclass(frozen=True)
class GitHubRepo:
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def web_url(self) -> str:
        return f"https://github.com/{self.slug}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.slug}.git"


def parse_github_url(text: str, allow_shorthand: bool = True) -> GitHubRepo:
    """Read a GitHub repository out of a pasted link.

    Accepts ``https://github.com/owner/repo`` (with or without ``https://``,
    ``www.``, ``.git``, a trailing slash, or a deeper path such as
    ``/tree/main/src``), ``git@github.com:owner/repo.git`` and, when
    ``allow_shorthand`` is true, plain ``owner/repo``.
    """
    cleaned = re.split(r"[?#]", text.strip(), maxsplit=1)[0].strip().rstrip("/")
    match = _FULL_URL.match(cleaned) or _SSH_URL.match(cleaned)
    if match is None and allow_shorthand:
        match = _SHORTHAND.match(cleaned)
    if match is None:
        raise InvalidRepositoryURL(
            "that does not look like a GitHub repository link; "
            "use something like https://github.com/owner/repository"
        )
    owner, name = match.group("owner"), match.group("name")
    if name.lower().endswith(".git"):
        name = name[:-4]
    if not name or name in {".", ".."}:
        raise InvalidRepositoryURL("the link is missing the repository name")
    return GitHubRepo(owner=owner, name=name)


def looks_like_github_url(text: str) -> bool:
    """True for text that names github.com explicitly (used by the CLI)."""
    return "github.com" in text.lower()


def parse_progress(line: str) -> Optional[tuple]:
    """Parse one line of ``git clone --progress`` into ``(phase, percent, size)``."""
    match = _PROGRESS.search(line)
    if match is None:
        return None
    size = _SIZE.search(match.group("rest"))
    return match.group("phase"), int(match.group("percent")), size.group(1) if size else ""


def explain_clone_failure(stderr: str, repo: GitHubRepo) -> str:
    """Turn git's error output into a sentence a person can act on."""
    low = stderr.lower()
    if any(hint in low for hint in (
        "repository not found", "could not read username", "terminal prompts disabled",
        "authentication failed", "invalid username or password",
    )):
        return (f"{repo.slug} was not found on GitHub. Check the link; private repositories "
                "only work if your git credentials can access them.")
    if any(hint in low for hint in ("could not resolve host", "failed to connect", "connection timed out",
                                    "network is unreachable", "couldn't connect")):
        return "could not reach github.com. Check your internet connection and try again."
    lines = [line.strip() for line in stderr.splitlines() if line.strip() and not _PROGRESS.search(line)]
    return "git clone failed: " + (lines[-1] if lines else "unknown error")


def clone_repository(
    repo: GitHubRepo,
    destination: Union[str, Path],
    on_progress: Optional[ProgressCallback] = None,
    timeout: float = 900.0,
    url: Optional[str] = None,
) -> Path:
    """Clone the default branch of ``repo`` (bare, no tags) into ``destination``.

    ``url`` overrides the address cloned from; the tests use it to clone a
    local repository instead of reaching the network.
    """
    ensure_git_available()
    target = Path(destination)
    command = [
        "git", "clone", "--bare", "--single-branch", "--no-tags", "--progress",
        "--", url or repo.clone_url, str(target),
    ]
    # Never stop to ask for a password: a private or missing repository
    # should fail straight away instead of hanging the web page.
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
    except FileNotFoundError as exc:  # pragma: no cover - checked above
        raise GitNotFoundError("git was not found") from exc

    timed_out = threading.Event()

    def kill() -> None:
        timed_out.set()
        process.kill()

    timer = threading.Timer(timeout, kill)
    timer.daemon = True
    timer.start()
    captured: List[str] = []
    try:
        assert process.stderr is not None
        pending = b""
        while True:
            chunk = process.stderr.read1(4096) if hasattr(process.stderr, "read1") else process.stderr.read(1)
            if not chunk:
                break
            pending += chunk
            # git redraws its progress line with \r; treat that as a line break.
            parts = re.split(rb"[\r\n]", pending)
            pending = parts.pop()
            for raw in parts:
                line = raw.decode("utf-8", errors="replace")
                if not line.strip():
                    continue
                captured.append(line)
                del captured[:-60]
                progress = parse_progress(line)
                if progress and on_progress:
                    on_progress(*progress)
        if pending.strip():
            captured.append(pending.decode("utf-8", errors="replace"))
        code = process.wait()
    finally:
        timer.cancel()
    if timed_out.is_set():
        raise CloneError(f"cloning {repo.slug} took longer than {int(timeout)} seconds and was stopped")
    if code != 0:
        raise CloneError(explain_clone_failure("\n".join(captured), repo))
    return target
