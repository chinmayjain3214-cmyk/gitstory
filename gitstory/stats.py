"""All of gitstory's analysis, as pure functions over a list of commits.

Nothing in this module runs a subprocess, reads a file or looks at the clock:
every function takes :class:`~gitstory.parser.Commit` objects and returns plain
dataclasses. That keeps the analysis easy to test with synthetic commits.

Conventions used throughout:

* "Day", "week" and "hour" always mean the **author's local** calendar, i.e.
  the UTC offset recorded in each commit. Ordering and gaps use absolute time.
* Weeks start on Monday. Weekday indexes follow Python: Monday is 0.
* Commit-message analysis looks at the subject line (the first line) only.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .parser import Commit

CONVENTIONAL_TYPES: Tuple[str, ...] = (
    "feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert",
)
_CONVENTIONAL = re.compile(
    r"^(?P<type>" + "|".join(CONVENTIONAL_TYPES) + r")(?:\([^)]*\))?!?:\s*(?=\S)",
    re.IGNORECASE,
)
_WORD = re.compile(r"[^\W\d_]{3,}")  # runs of letters in any script, 3+ long
_NAME_SPLIT = re.compile(r"[\s._\-]+")

STOPWORDS = frozenset(
    """
    a about above after again all also am an and any are aren as at be because been before
    being below between both but by can cannot could did didn do does doesn doing don down
    during each few for from further had hadn has hasn have haven having he her here hers
    herself him himself his how i if in into is isn it its itself just let ll me more most
    my myself no nor not now of off on once only or other our ours ourselves out over own
    re same shan she should shouldn so some such than that the their theirs them themselves
    then there these they this those through to too under until up ve very was wasn we were
    weren what when where which while who whom why will with won would wouldn you your yours
    yourself yourselves
    """.split()
)

LANGUAGES: Dict[str, str] = {
    ".py": "Python", ".pyi": "Python", ".ipynb": "Jupyter", ".js": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "Sass",
    ".sass": "Sass", ".less": "Less", ".vue": "Vue", ".svelte": "Svelte", ".java": "Java",
    ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala", ".groovy": "Groovy", ".c": "C",
    ".h": "C/C++ header", ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".hpp": "C++",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".m": "Objective-C", ".dart": "Dart", ".lua": "Lua", ".r": "R", ".jl": "Julia",
    ".pl": "Perl", ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang", ".hs": "Haskell",
    ".clj": "Clojure", ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".ps1": "PowerShell",
    ".bat": "Batch", ".sql": "SQL", ".md": "Markdown", ".rst": "reStructuredText",
    ".txt": "Text", ".json": "JSON", ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML",
    ".xml": "XML", ".ini": "INI", ".cfg": "Config", ".csv": "CSV", ".svg": "SVG",
    ".tex": "LaTeX", ".proto": "Protocol Buffers", ".tf": "Terraform", ".gradle": "Gradle",
    ".lock": "Lockfile",
}
NO_EXTENSION = "(no extension)"


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Summary:
    commits: int
    contributors: int
    merges: int
    files_touched: int
    lines_added: int
    lines_removed: int
    first_commit: datetime
    last_commit: datetime
    age_days: int


@dataclass(frozen=True)
class WeekBucket:
    start: date  # the Monday the week begins on
    commits: int
    lines_added: int
    lines_removed: int
    top_message: str  # subject of the week's largest commit ("" for empty weeks)


@dataclass(frozen=True)
class ContributorStats:
    name: str
    initials: str
    color: str  # CSS colour derived from a hash of the email address
    commits: int
    lines_added: int
    lines_removed: int
    first_active: date
    last_active: date
    sparkline: List[int]  # commits per equal slice of the project's lifetime


@dataclass(frozen=True)
class Persona:
    label: str
    emoji: str
    description: str


@dataclass(frozen=True)
class FileChurn:
    path: str
    lines_added: int
    lines_removed: int
    commits: int

    @property
    def lines_changed(self) -> int:
        return self.lines_added + self.lines_removed


@dataclass(frozen=True)
class ExtensionChurn:
    extension: str
    language: str
    lines_changed: int
    files: int
    share: float  # fraction of all changed lines, 0..1


@dataclass(frozen=True)
class WordCount:
    word: str
    count: int


@dataclass(frozen=True)
class PrefixCount:
    type: str
    count: int


@dataclass(frozen=True)
class MessageRef:
    text: str
    hash: str
    author: str
    when: datetime
    length: int


@dataclass(frozen=True)
class MessageInsights:
    analysed: int  # messages looked at (merge commits are skipped)
    average_length: float  # characters in the subject line
    average_words: float
    common_words: List[WordCount]
    conventional_count: int
    conventional_share: float  # 0..1
    conventional_types: List[PrefixCount]
    longest: Optional[MessageRef]
    shortest: Optional[MessageRef]


@dataclass(frozen=True)
class BiggestCommit:
    hash: str
    subject: str
    author: str
    when: datetime
    lines_added: int
    lines_removed: int
    files: int


@dataclass(frozen=True)
class Streak:
    days: int
    start: date
    end: date


@dataclass(frozen=True)
class Gap:
    seconds: int
    start: datetime
    end: datetime

    @property
    def days(self) -> float:
        return self.seconds / 86400


@dataclass(frozen=True)
class BusiestDay:
    day: date
    commits: int


@dataclass(frozen=True)
class FunFacts:
    biggest_commit: Optional[BiggestCommit]
    longest_streak: Streak
    longest_gap: Optional[Gap]  # None when there is only one commit
    busiest_day: BusiestDay


@dataclass(frozen=True)
class Report:
    """Everything the HTML report needs, ready to be serialised to JSON."""

    repo_name: str
    summary: Summary
    timeline: List[WeekBucket]
    contributors: List[ContributorStats]
    heatmap: List[List[int]]
    persona: Persona
    files: List[FileChurn]
    extensions: List[ExtensionChurn]
    messages: MessageInsights
    facts: FunFacts

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def sort_commits(commits: Sequence[Commit]) -> List[Commit]:
    """Return commits oldest first, by absolute time."""
    return sorted(commits, key=lambda commit: commit.timestamp)


def local_day(commit: Commit) -> date:
    """The calendar day on which the author made the commit, in their timezone."""
    return commit.timestamp.date()


def week_start(day: date) -> date:
    """The Monday of the week containing ``day``."""
    return day - timedelta(days=day.weekday())


def author_key(commit: Commit) -> str:
    """Identity used to group commits by person: the email, else the name."""
    return (commit.author_email or commit.author_name).strip().lower()


def initials(name: str) -> str:
    """Up to two initials for an avatar: ``"Ada Lovelace"`` becomes ``"AL"``."""
    parts = [part for part in _NAME_SPLIT.split(name.strip()) if part and part[0].isalnum()]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def avatar_color(email: str) -> str:
    """A stable, pleasant colour derived from a hash of the email address."""
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    hue = int(digest[:8], 16) % 360
    return f"hsl({hue}, 58%, 46%)"


def _clip(text: str, limit: int = 140) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# --------------------------------------------------------------------------
# Hero summary
# --------------------------------------------------------------------------


def summarize(commits: Sequence[Commit]) -> Summary:
    """Headline totals for the whole history."""
    if not commits:
        raise ValueError("cannot summarise an empty history")
    ordered = sort_commits(commits)
    first, last = ordered[0].timestamp, ordered[-1].timestamp
    paths: Set[str] = {change.path for commit in ordered for change in commit.files}
    return Summary(
        commits=len(ordered),
        contributors=len({author_key(commit) for commit in ordered}),
        merges=sum(1 for commit in ordered if commit.is_merge),
        files_touched=len(paths),
        lines_added=sum(commit.lines_added for commit in ordered),
        lines_removed=sum(commit.lines_removed for commit in ordered),
        first_commit=first,
        last_commit=last,
        # A project is at least one day old, even with a single commit.
        age_days=max(1, math.ceil((last - first).total_seconds() / 86400)),
    )


# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------


def weekly_timeline(commits: Sequence[Commit]) -> List[WeekBucket]:
    """Commits per week from the first to the last commit, with quiet weeks as zeros.

    ``top_message`` is the subject of the week's largest non-merge commit by
    lines changed (the most recent one wins a tie).
    """
    if not commits:
        return []
    by_week: Dict[date, List[Commit]] = {}
    for commit in commits:
        by_week.setdefault(week_start(local_day(commit)), []).append(commit)
    buckets: List[WeekBucket] = []
    week, last_week = min(by_week), max(by_week)
    while week <= last_week:
        members = by_week.get(week, [])
        top = max(
            members,
            key=lambda commit: (not commit.is_merge, commit.lines_changed, commit.timestamp),
            default=None,
        )
        buckets.append(
            WeekBucket(
                start=week,
                commits=len(members),
                lines_added=sum(commit.lines_added for commit in members),
                lines_removed=sum(commit.lines_removed for commit in members),
                top_message=_clip(top.subject) if top is not None else "",
            )
        )
        week += timedelta(days=7)
    return buckets


# --------------------------------------------------------------------------
# Contributors
# --------------------------------------------------------------------------


def contributor_stats(commits: Sequence[Commit], sparkline_buckets: int = 24) -> List[ContributorStats]:
    """Per-person totals, ranked by commits (then lines changed, then name).

    People are grouped by email address, case-insensitively. The display name
    is the one they used most often.
    """
    if not commits:
        return []
    ordered = sort_commits(commits)
    start = ordered[0].timestamp
    span = (ordered[-1].timestamp - start).total_seconds()

    groups: Dict[str, List[Commit]] = {}
    for commit in ordered:
        groups.setdefault(author_key(commit), []).append(commit)

    people: List[ContributorStats] = []
    for members in groups.values():
        name = Counter(commit.author_name for commit in members).most_common(1)[0][0]
        spark = [0] * sparkline_buckets
        for commit in members:
            offset = (commit.timestamp - start).total_seconds()
            index = int(offset / span * sparkline_buckets) if span > 0 else 0
            spark[min(sparkline_buckets - 1, index)] += 1
        people.append(
            ContributorStats(
                name=name,
                initials=initials(name),
                color=avatar_color(members[0].author_email or name),
                commits=len(members),
                lines_added=sum(commit.lines_added for commit in members),
                lines_removed=sum(commit.lines_removed for commit in members),
                first_active=local_day(members[0]),
                last_active=local_day(members[-1]),
                sparkline=spark,
            )
        )
    people.sort(key=lambda p: (-p.commits, -(p.lines_added + p.lines_removed), p.name.lower()))
    return people


# --------------------------------------------------------------------------
# When the code gets written
# --------------------------------------------------------------------------


def commit_heatmap(commits: Sequence[Commit]) -> List[List[int]]:
    """A 7x24 grid of commit counts: ``grid[weekday][hour]``, Monday first."""
    grid = [[0] * 24 for _ in range(7)]
    for commit in commits:
        grid[commit.timestamp.weekday()][commit.timestamp.hour] += 1
    return grid


def coding_persona(grid: Sequence[Sequence[int]]) -> Persona:
    """A light-hearted label for when the commits happen, derived from the heatmap."""
    total = sum(sum(row) for row in grid)
    if total == 0:
        return Persona("Mystery committer", "\U0001F47B", "No commits to read the tea leaves from.")

    def share(days: Sequence[int], hours: Sequence[int]) -> float:
        return sum(grid[day][hour] for day in days for hour in hours) / total

    all_days, weekdays, weekend = range(7), range(5), (5, 6)
    night = share(all_days, (22, 23, 0, 1, 2, 3))
    early = share(all_days, range(5, 9))
    office = share(weekdays, range(9, 18))
    evening = share(all_days, range(18, 22))
    weekends = share(weekend, range(24))

    def pct(value: float) -> str:
        return f"{round(value * 100)}%"

    if weekends >= 0.5:
        return Persona("Weekend warrior", "\U0001F6E0️",
                       f"{pct(weekends)} of commits land on a Saturday or Sunday.")
    if night >= 0.3:
        return Persona("Night owl", "\U0001F989",
                       f"{pct(night)} of commits land between 10pm and 4am.")
    if early >= 0.3:
        return Persona("Early bird", "\U0001F426",
                       f"{pct(early)} of commits land between 5am and 9am.")
    if office >= 0.6:
        return Persona("9-to-5er", "☀️",
                       f"{pct(office)} of commits land on weekdays between 9am and 6pm.")
    if evening >= 0.35:
        return Persona("After-hours hacker", "\U0001F306",
                       f"{pct(evening)} of commits land between 6pm and 10pm.")
    return Persona("Round-the-clock coder", "\U0001F30D",
                   "Commits are spread across the whole day, with no single favourite time.")


# --------------------------------------------------------------------------
# File churn
# --------------------------------------------------------------------------


def file_churn(commits: Sequence[Commit], limit: int = 15) -> List[FileChurn]:
    """The most-changed files, by lines added plus removed.

    Renames are followed: when a file is renamed, its earlier history moves to
    the new path so one file is not counted twice under two names.
    """
    totals: Dict[str, List[int]] = {}  # path -> [added, removed, commits]
    for commit in sort_commits(commits):
        for change in commit.files:
            old = change.old_path
            if old and old != change.path and old in totals:
                moved = totals.pop(old)
                merged = totals.setdefault(change.path, [0, 0, 0])
                for i in range(3):
                    merged[i] += moved[i]
            entry = totals.setdefault(change.path, [0, 0, 0])
            entry[0] += change.added
            entry[1] += change.removed
            entry[2] += 1
    ranked = sorted(totals.items(), key=lambda kv: (-(kv[1][0] + kv[1][1]), -kv[1][2], kv[0]))
    return [FileChurn(path, added, removed, count) for path, (added, removed, count) in ranked[:limit]]


def file_extension(path: str) -> str:
    """Lower-cased extension of ``path``; dotfiles use their whole name."""
    name = PurePosixPath(path).name
    suffix = PurePosixPath(name).suffix.lower()
    if suffix:
        return suffix
    if name.startswith(".") and len(name) > 1:
        return name.lower()
    return NO_EXTENSION


def extension_churn(commits: Sequence[Commit], limit: int = 8) -> List[ExtensionChurn]:
    """File extensions ranked by lines changed, with a friendly language name."""
    lines: Counter = Counter()
    paths: Dict[str, Set[str]] = {}
    for commit in commits:
        for change in commit.files:
            ext = file_extension(change.path)
            lines[ext] += change.changed
            paths.setdefault(ext, set()).add(change.path)
    total = sum(lines.values())
    ranked = sorted(lines.items(), key=lambda kv: (-kv[1], kv[0]))
    return [
        ExtensionChurn(
            extension=ext,
            language=LANGUAGES.get(ext, ext),
            lines_changed=count,
            files=len(paths[ext]),
            share=(count / total) if total else 0.0,
        )
        for ext, count in ranked[:limit]
    ]


# --------------------------------------------------------------------------
# Commit messages
# --------------------------------------------------------------------------


def conventional_type(subject: str) -> Optional[str]:
    """The Conventional Commits type of a subject line (``"feat"``, ``"fix"``...), if any."""
    match = _CONVENTIONAL.match(subject.strip())
    return match.group("type").lower() if match else None


def significant_words(subject: str) -> List[str]:
    """Lower-cased words of a subject, minus stopwords and any conventional prefix."""
    text = _CONVENTIONAL.sub("", subject.strip(), count=1)
    return [word for word in _WORD.findall(text.lower()) if word not in STOPWORDS]


def message_insights(commits: Sequence[Commit], top_words: int = 12) -> MessageInsights:
    """Statistics about commit subject lines.

    Merge commits are skipped (their messages are usually auto-generated)
    unless the history consists of nothing else.
    """
    pool = [commit for commit in commits if not commit.is_merge] or list(commits)
    if not pool:
        return MessageInsights(0, 0.0, 0.0, [], 0, 0.0, [], None, None)
    ordered = sort_commits(pool)
    subjects = [commit.subject for commit in ordered]

    words: Counter = Counter()
    types: Counter = Counter()
    for subject in subjects:
        words.update(significant_words(subject))
        kind = conventional_type(subject)
        if kind:
            types[kind] += 1

    def ref(commit: Commit) -> MessageRef:
        return MessageRef(
            text=_clip(commit.subject, 300),
            hash=commit.short_hash,
            author=commit.author_name,
            when=commit.timestamp,
            length=len(commit.subject),
        )

    conventional = sum(types.values())
    return MessageInsights(
        analysed=len(ordered),
        average_length=round(sum(len(s) for s in subjects) / len(subjects), 1),
        average_words=round(sum(len(s.split()) for s in subjects) / len(subjects), 1),
        common_words=[
            WordCount(word, count)
            for word, count in sorted(words.items(), key=lambda kv: (-kv[1], kv[0]))[:top_words]
        ],
        conventional_count=conventional,
        conventional_share=conventional / len(ordered),
        conventional_types=[
            PrefixCount(kind, count)
            for kind, count in sorted(types.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        # max()/min() return the first match, so ties go to the earliest commit.
        longest=ref(max(ordered, key=lambda commit: len(commit.subject))),
        shortest=ref(min(ordered, key=lambda commit: len(commit.subject))),
    )


# --------------------------------------------------------------------------
# Fun facts
# --------------------------------------------------------------------------


def biggest_commit(commits: Sequence[Commit]) -> Optional[BiggestCommit]:
    """The commit that changed the most lines (earliest wins a tie)."""
    if not commits:
        return None
    top = max(sort_commits(commits), key=lambda commit: commit.lines_changed)
    return BiggestCommit(
        hash=top.short_hash,
        subject=_clip(top.subject),
        author=top.author_name,
        when=top.timestamp,
        lines_added=top.lines_added,
        lines_removed=top.lines_removed,
        files=len(top.files),
    )


def longest_streak(commits: Sequence[Commit]) -> Streak:
    """The longest run of consecutive calendar days with at least one commit."""
    days = sorted({local_day(commit) for commit in commits})
    if not days:
        raise ValueError("cannot compute a streak for an empty history")
    best_start = run_start = days[0]
    best_length = run_length = 1
    for previous, current in zip(days, days[1:]):
        if (current - previous).days == 1:
            run_length += 1
        else:
            run_start, run_length = current, 1
        if run_length > best_length:
            best_start, best_length = run_start, run_length
    return Streak(days=best_length, start=best_start, end=best_start + timedelta(days=best_length - 1))


def longest_gap(commits: Sequence[Commit]) -> Optional[Gap]:
    """The longest silence between two consecutive commits, or ``None`` with fewer than two."""
    ordered = sort_commits(commits)
    best: Optional[Gap] = None
    for previous, current in zip(ordered, ordered[1:]):
        seconds = int((current.timestamp - previous.timestamp).total_seconds())
        if best is None or seconds > best.seconds:
            best = Gap(seconds=seconds, start=previous.timestamp, end=current.timestamp)
    return best


def busiest_day(commits: Sequence[Commit]) -> BusiestDay:
    """The calendar day with the most commits (earliest wins a tie)."""
    counts = Counter(local_day(commit) for commit in commits)
    if not counts:
        raise ValueError("cannot find the busiest day of an empty history")
    day, count = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return BusiestDay(day=day, commits=count)


def fun_facts(commits: Sequence[Commit]) -> FunFacts:
    return FunFacts(
        biggest_commit=biggest_commit(commits),
        longest_streak=longest_streak(commits),
        longest_gap=longest_gap(commits),
        busiest_day=busiest_day(commits),
    )


# --------------------------------------------------------------------------
# Everything together
# --------------------------------------------------------------------------


def build_report(commits: Sequence[Commit], repo_name: str, max_contributors: int = 30) -> Report:
    """Run every analysis and bundle the results for the renderer."""
    if not commits:
        raise ValueError("cannot build a report from an empty history")
    grid = commit_heatmap(commits)
    return Report(
        repo_name=repo_name,
        summary=summarize(commits),
        timeline=weekly_timeline(commits),
        contributors=contributor_stats(commits)[:max_contributors],
        heatmap=grid,
        persona=coding_persona(grid),
        files=file_churn(commits),
        extensions=extension_churn(commits),
        messages=message_insights(commits),
        facts=fun_facts(commits),
    )
