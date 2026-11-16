"""Run ``git log`` and parse its output into dataclasses.

The module has two halves:

* :func:`parse_git_log` is a pure function that turns the text printed by
  ``git log`` (in the format built by :func:`build_log_command`) into a list of
  :class:`Commit` objects. It never touches the filesystem, so it is easy to
  test with a fixed string.
* :func:`read_commits` and friends shell out to ``git`` through
  :mod:`subprocess` and turn the usual failure modes into friendly exceptions.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

# ASCII "record separator" and "unit separator": control characters that do not
# show up in real commit messages, author names or file paths.
RECORD_SEP = "\x1e"
FIELD_SEP = "\x1f"

# hash, author name, author email, author date, parent hashes, raw message.
# %aN/%aE respect .mailmap; a trailing separator marks where --numstat begins.
LOG_FORMAT = "%x1e%H%x1f%aN%x1f%aE%x1f%ad%x1f%P%x1f%B%x1f"

# A record starts with the separator followed by a full SHA-1 or SHA-256 hash.
# Anchoring on the hash keeps a stray separator inside a message from
# splitting a commit in two.
_RECORD_START = re.compile(RECORD_SEP + r"(?=[0-9a-f]{40,64}" + FIELD_SEP + ")")
_BRACE_RENAME = re.compile(r"^(?P<pre>.*)\{(?P<old>.*) => (?P<new>.*)\}(?P<post>.*)$")
_RAW_DATE = re.compile(r"^(-?\d+)(?:\s+([+-])(\d{2})(\d{2}))?")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_SIMPLE_ESCAPES = {
    "a": 0x07, "b": 0x08, "t": 0x09, "n": 0x0A, "v": 0x0B,
    "f": 0x0C, "r": 0x0D, '"': 0x22, "\\": 0x5C,
}

PathLike = Union[str, Path]


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class GitStoryError(Exception):
    """Base class for errors that should be shown to the user without a traceback."""


class GitNotFoundError(GitStoryError):
    """The ``git`` executable is not installed or not on PATH."""


class NotAGitRepositoryError(GitStoryError):
    """The given path does not exist or is not inside a git repository."""


class NoCommitsError(GitStoryError):
    """The repository (or the filtered slice of it) contains no commits."""


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FileChange:
    """One file touched by a commit, as reported by ``git log --numstat``."""

    path: str
    added: int = 0
    removed: int = 0
    binary: bool = False
    old_path: Optional[str] = None  # set when the file was renamed in this commit

    @property
    def changed(self) -> int:
        """Total lines added plus removed."""
        return self.added + self.removed

    @property
    def is_rename(self) -> bool:
        return self.old_path is not None


@dataclass(frozen=True)
class Commit:
    """A single commit. ``timestamp`` is timezone-aware, in the author's own offset."""

    hash: str
    author_name: str
    author_email: str
    timestamp: datetime
    message: str
    files: Tuple[FileChange, ...] = ()
    parents: Tuple[str, ...] = ()

    @property
    def short_hash(self) -> str:
        return self.hash[:7]

    @property
    def subject(self) -> str:
        """First line of the commit message."""
        # split("\n"), not splitlines(): the latter also breaks on exotic
        # separators such as U+2028 that can legitimately appear in a subject.
        return self.message.strip().split("\n", 1)[0].strip()

    @property
    def body(self) -> str:
        """Everything after the subject line."""
        _, _, rest = self.message.strip().partition("\n")
        return rest.strip()

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def lines_added(self) -> int:
        return sum(change.added for change in self.files)

    @property
    def lines_removed(self) -> int:
        return sum(change.removed for change in self.files)

    @property
    def lines_changed(self) -> int:
        return self.lines_added + self.lines_removed


# --------------------------------------------------------------------------
# Parsing (pure)
# --------------------------------------------------------------------------


def parse_git_log(text: str) -> List[Commit]:
    """Parse the output of ``git log`` produced with :data:`LOG_FORMAT` and ``--numstat``.

    Commits are returned in the order git printed them (newest first by default).
    Malformed records are skipped rather than raising.
    """
    commits: List[Commit] = []
    for record in _RECORD_START.split(text)[1:]:
        commit = _parse_record(record)
        if commit is not None:
            commits.append(commit)
    return commits


def _parse_record(record: str) -> Optional[Commit]:
    # The numstat block sits after the last field separator. Paths can never
    # contain that character (git quotes control characters), so splitting
    # from the right is safe even if the message contains one.
    head, sep, numstat = record.rpartition(FIELD_SEP)
    if not sep:
        return None
    fields = head.split(FIELD_SEP, 5)
    if len(fields) != 6:
        return None
    commit_hash, name, email, raw_date, parents, message = fields
    files = tuple(
        change
        for change in (parse_numstat_line(line) for line in numstat.split("\n"))
        if change is not None
    )
    return Commit(
        hash=commit_hash.strip(),
        author_name=name.strip() or "Unknown",
        author_email=email.strip(),
        timestamp=parse_raw_date(raw_date),
        message=message.strip("\r\n"),
        files=files,
        parents=tuple(parents.split()),
    )


def parse_raw_date(value: str) -> datetime:
    """Parse git's ``--date=raw`` format (``"<epoch seconds> <+hhmm>"``).

    Returns an aware datetime in the offset the author committed from. A
    missing or unreadable offset falls back to UTC.
    """
    match = _RAW_DATE.match(value.strip())
    if match is None:
        return _EPOCH
    seconds = int(match.group(1))
    tz = timezone.utc
    if match.group(2):
        offset = timedelta(hours=int(match.group(3)), minutes=int(match.group(4)))
        try:
            tz = timezone(-offset if match.group(2) == "-" else offset)
        except ValueError:  # offsets of 24h or more are not real timezones
            tz = timezone.utc
    # Adding to the epoch (instead of datetime.fromtimestamp) also works for
    # pre-1970 dates on Windows.
    return (_EPOCH + timedelta(seconds=seconds)).astimezone(tz)


def parse_numstat_line(line: str) -> Optional[FileChange]:
    """Parse one ``--numstat`` line: ``"<added>\\t<removed>\\t<path>"``.

    Binary files report ``-`` for both counts; they are kept with zero lines
    and ``binary=True``. Returns ``None`` for blank or unrecognised lines.
    """
    line = line.rstrip("\r\n")
    if not line.strip():
        return None
    parts = line.split("\t", 2)
    if len(parts) != 3:
        return None
    added_raw, removed_raw, raw_path = parts
    binary = added_raw == "-" or removed_raw == "-"
    try:
        added = 0 if added_raw == "-" else int(added_raw)
        removed = 0 if removed_raw == "-" else int(removed_raw)
    except ValueError:
        return None
    path, old_path = split_rename(raw_path)
    return FileChange(path=path, added=added, removed=removed, binary=binary, old_path=old_path)


def split_rename(raw_path: str) -> Tuple[str, Optional[str]]:
    """Resolve git's rename notation to ``(new_path, old_path)``.

    Handles both ``old.py => new.py`` and the compact brace form
    ``src/{old => new}/file.py``. ``old_path`` is ``None`` for ordinary changes.
    """
    brace = _BRACE_RENAME.match(raw_path)
    if brace:
        pre, post = brace.group("pre"), brace.group("post")
        old = _collapse_slashes(pre + brace.group("old") + post)
        new = _collapse_slashes(pre + brace.group("new") + post)
        return _unquote_path(new), _unquote_path(old)
    if " => " in raw_path:
        old, new = raw_path.split(" => ", 1)
        return _unquote_path(new), _unquote_path(old)
    return _unquote_path(raw_path), None


def _collapse_slashes(path: str) -> str:
    # "src/{ => lib}/a.py" expands to "src//a.py" on the old side.
    return re.sub(r"/{2,}", "/", path)


def _unquote_path(path: str) -> str:
    """Undo git's C-style quoting of paths with unusual characters."""
    if len(path) < 2 or not (path.startswith('"') and path.endswith('"')):
        return path
    body = path[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        char = body[i]
        if char != "\\" or i + 1 >= len(body):
            out += char.encode("utf-8")
            i += 1
            continue
        nxt = body[i + 1]
        if nxt in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[nxt])
            i += 2
        elif nxt in "01234567":
            j = i + 1
            while j < len(body) and j < i + 4 and body[j] in "01234567":
                j += 1
            out.append(int(body[i + 1 : j], 8) & 0xFF)
            i = j
        else:
            out += nxt.encode("utf-8")
            i += 2
    return out.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# Running git
# --------------------------------------------------------------------------


def build_log_command(
    repo: PathLike,
    since: Optional[str] = None,
    until: Optional[str] = None,
    author: Optional[str] = None,
) -> List[str]:
    """Build the ``git log`` argument list used to read a repository's history."""
    command = [
        "git",
        "-C", str(repo),
        "--no-pager",
        "-c", "core.quotepath=false",    # keep non-ASCII paths readable
        "-c", "log.showSignature=false",  # GPG output would corrupt the format
        "log",
        "--no-color",
        "--date=raw",
        "--numstat",
        "-M",                             # detect renames
        "--pretty=format:" + LOG_FORMAT,
    ]
    if since:
        command.append("--since=" + since)
    if until:
        command.append("--until=" + until)
    if author:
        command.append("--author=" + author)
    return command


def _run(command: Sequence[str]) -> "subprocess.CompletedProcess[bytes]":
    try:
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError as exc:
        raise GitNotFoundError(
            "git was not found. Install it from https://git-scm.com/downloads "
            "and make sure it is on your PATH."
        ) from exc


def _decode(raw: bytes) -> str:
    # Commit messages are not guaranteed to be UTF-8; never crash on them.
    return raw.decode("utf-8", errors="replace")


def ensure_git_available() -> None:
    """Raise :class:`GitNotFoundError` if no ``git`` executable is on PATH."""
    if shutil.which("git") is None:
        raise GitNotFoundError(
            "git was not found. Install it from https://git-scm.com/downloads "
            "and make sure it is on your PATH."
        )


def ensure_repository(repo: PathLike) -> None:
    """Raise unless ``repo`` is a git repository with at least one commit."""
    path = Path(repo)
    if not path.exists():
        raise NotAGitRepositoryError(f"path does not exist: {path}")
    if not path.is_dir():
        raise NotAGitRepositoryError(f"not a directory: {path}")
    probe = _run(["git", "-C", str(path), "rev-parse", "--git-dir"])
    if probe.returncode != 0:
        detail = _decode(probe.stderr).strip().splitlines()
        hint = f" (git says: {detail[0]})" if detail and "not a git repository" not in detail[0] else ""
        raise NotAGitRepositoryError(f"not a git repository: {path.resolve()}{hint}")
    head = _run(["git", "-C", str(path), "rev-parse", "--verify", "--quiet", "HEAD"])
    if head.returncode != 0:
        raise NoCommitsError(f"this repository has no commits yet: {path.resolve()}")


def get_repo_name(repo: PathLike) -> str:
    """Best-effort human name for the repository: its top-level folder name."""
    path = Path(repo)
    result = _run(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    top = _decode(result.stdout).strip() if result.returncode == 0 else ""
    name = Path(top).name if top else path.resolve().name
    if name.endswith(".git") and len(name) > 4:  # bare repositories
        name = name[:-4]
    return name or "repository"


def read_commits(
    repo: PathLike = ".",
    since: Optional[str] = None,
    until: Optional[str] = None,
    author: Optional[str] = None,
) -> List[Commit]:
    """Read and parse the history of ``repo`` (the currently checked-out branch).

    Raises :class:`GitNotFoundError`, :class:`NotAGitRepositoryError` or
    :class:`NoCommitsError` with a message suitable for showing to the user.
    """
    ensure_git_available()
    ensure_repository(repo)
    result = _run(build_log_command(repo, since=since, until=until, author=author))
    if result.returncode != 0:
        detail = _decode(result.stderr).strip() or "unknown error"
        raise GitStoryError(f"git log failed: {detail}")
    commits = parse_git_log(_decode(result.stdout))
    if not commits:
        if since or until or author:
            raise NoCommitsError("no commits match the given --since/--until/--author filters")
        raise NoCommitsError(f"this repository has no commits yet: {Path(repo).resolve()}")
    return commits
