"""Tests for gitstory.stats, using small synthetic histories."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Sequence, Tuple

import pytest

from gitstory.parser import Commit, FileChange
from gitstory.stats import (
    avatar_color,
    biggest_commit,
    build_report,
    busiest_day,
    coding_persona,
    commit_heatmap,
    contributor_stats,
    conventional_type,
    extension_churn,
    file_churn,
    file_extension,
    initials,
    longest_gap,
    longest_streak,
    message_insights,
    significant_words,
    summarize,
    weekly_timeline,
)

UTC = timezone.utc
_counter = iter(range(1, 10_000))


def make_commit(
    when: datetime,
    message: str = "Update things",
    files: Sequence[Tuple] = (),
    name: str = "Ada Lovelace",
    email: str = "ada@example.com",
    parents: Optional[Tuple[str, ...]] = None,
) -> Commit:
    """Build a commit. ``files`` holds ``(path, added, removed[, old_path])`` tuples."""
    serial = next(_counter)
    changes = tuple(
        FileChange(path=f[0], added=f[1], removed=f[2], old_path=f[3] if len(f) > 3 else None) for f in files
    )
    return Commit(
        hash=f"{serial:040x}",
        author_name=name,
        author_email=email,
        timestamp=when,
        message=message,
        files=changes,
        parents=parents if parents is not None else (f"{serial - 1:040x}",),
    )


def at(year: int, month: int, day: int, hour: int = 12, minute: int = 0, tz: timezone = UTC) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=tz)


# ---------------------------------------------------------------- streaks, gaps, busiest day


def test_longest_streak_counts_consecutive_days():
    days = [1, 2, 3, 10, 11, 12, 13, 20]
    commits = [make_commit(at(2024, 3, d)) for d in days]
    streak = longest_streak(commits)
    assert (streak.days, streak.start, streak.end) == (4, date(2024, 3, 10), date(2024, 3, 13))


def test_longest_streak_ignores_several_commits_on_one_day_and_input_order():
    commits = [make_commit(at(2024, 3, d, h)) for d, h in [(5, 9), (4, 9), (4, 18), (4, 23)]]
    assert longest_streak(commits).days == 2


def test_longest_streak_crosses_month_boundaries():
    commits = [make_commit(at(2024, 2, 28)), make_commit(at(2024, 2, 29)), make_commit(at(2024, 3, 1))]
    assert longest_streak(commits).days == 3


def test_streak_uses_the_authors_local_day():
    # 23:30 and 00:30 local time are consecutive days locally, even though
    # both fall on the same UTC day.
    ist = timezone(timedelta(hours=5, minutes=30))
    commits = [make_commit(at(2024, 3, 1, 23, 30, ist)), make_commit(at(2024, 3, 2, 0, 30, ist))]
    assert longest_streak(commits).days == 2


def test_longest_gap():
    commits = [make_commit(at(2024, 1, 1)), make_commit(at(2024, 1, 3)), make_commit(at(2024, 2, 2)), make_commit(at(2024, 2, 3))]
    gap = longest_gap(commits)
    assert gap is not None
    assert gap.days == 30
    assert (gap.start, gap.end) == (at(2024, 1, 3), at(2024, 2, 2))


def test_longest_gap_needs_two_commits():
    assert longest_gap([make_commit(at(2024, 1, 1))]) is None


def test_busiest_day_prefers_the_earliest_on_a_tie():
    commits = [make_commit(at(2024, 5, d, h)) for d, h in [(2, 9), (2, 10), (7, 9), (7, 10), (9, 9)]]
    busiest = busiest_day(commits)
    assert (busiest.day, busiest.commits) == (date(2024, 5, 2), 2)


def test_biggest_commit():
    commits = [
        make_commit(at(2024, 1, 1), "small", [("a.py", 5, 1)]),
        make_commit(at(2024, 1, 2), "huge refactor", [("a.py", 300, 200), ("b.py", 50, 0)]),
    ]
    biggest = biggest_commit(commits)
    assert biggest is not None
    assert (biggest.subject, biggest.lines_added, biggest.lines_removed, biggest.files) == ("huge refactor", 350, 200, 2)


# ---------------------------------------------------------------- heatmap and persona


def test_heatmap_buckets_by_weekday_and_hour():
    commits = [
        make_commit(at(2024, 3, 4, 9)),   # Monday 09:xx
        make_commit(at(2024, 3, 4, 9, 45)),
        make_commit(at(2024, 3, 10, 23)),  # Sunday 23:xx
    ]
    grid = commit_heatmap(commits)
    assert len(grid) == 7 and all(len(row) == 24 for row in grid)
    assert grid[0][9] == 2
    assert grid[6][23] == 1
    assert sum(map(sum, grid)) == 3


def test_heatmap_uses_local_time_not_utc():
    tokyo = timezone(timedelta(hours=9))
    grid = commit_heatmap([make_commit(at(2024, 3, 4, 1, 0, tokyo))])  # Sunday 16:00 UTC
    assert grid[0][1] == 1


def _grid(cells):
    grid = [[0] * 24 for _ in range(7)]
    for day, hour, count in cells:
        grid[day][hour] = count
    return grid


@pytest.mark.parametrize(
    "cells, label",
    [
        ([(1, 23, 6), (2, 1, 4), (3, 14, 5)], "Night owl"),
        ([(0, 10, 5), (2, 14, 5), (4, 16, 3), (1, 20, 2)], "9-to-5er"),
        ([(5, 11, 6), (6, 15, 5), (2, 10, 3)], "Weekend warrior"),
        ([(1, 6, 5), (3, 7, 4), (2, 13, 5)], "Early bird"),
        ([(0, 19, 5), (2, 20, 4), (3, 12, 6)], "After-hours hacker"),
        ([(0, 4, 3), (1, 10, 3), (2, 13, 3), (3, 17, 3), (4, 20, 3), (5, 12, 3)], "Round-the-clock coder"),
    ],
)
def test_coding_persona(cells, label):
    assert coding_persona(_grid(cells)).label == label


def test_coding_persona_handles_an_empty_grid():
    assert coding_persona(_grid([])).label == "Mystery committer"


# ---------------------------------------------------------------- churn


def test_file_churn_ranks_by_lines_changed():
    commits = [
        make_commit(at(2024, 1, 1), files=[("a.py", 10, 0), ("b.py", 1, 0)]),
        make_commit(at(2024, 1, 2), files=[("a.py", 5, 5), ("c.py", 30, 0)]),
    ]
    churn = file_churn(commits)
    assert [(f.path, f.lines_added, f.lines_removed, f.commits) for f in churn] == [
        ("c.py", 30, 0, 1), ("a.py", 15, 5, 2), ("b.py", 1, 0, 1),
    ]
    assert churn[1].lines_changed == 20
    assert [f.path for f in file_churn(commits, limit=1)] == ["c.py"]


def test_file_churn_follows_renames():
    commits = [
        make_commit(at(2024, 1, 3), files=[("new.py", 7, 0)]),
        make_commit(at(2024, 1, 2), files=[("new.py", 2, 1, "old.py")]),
        make_commit(at(2024, 1, 1), files=[("old.py", 100, 0)]),
    ]
    (only,) = file_churn(commits)
    assert (only.path, only.lines_added, only.lines_removed, only.commits) == ("new.py", 109, 1, 3)


def test_binary_changes_count_as_touches_without_lines():
    commits = [make_commit(at(2024, 1, 1), files=[("logo.png", 0, 0)])]
    assert file_churn(commits)[0].commits == 1
    assert extension_churn(commits)[0].share == 0.0


def test_extension_churn():
    commits = [
        make_commit(at(2024, 1, 1), files=[("src/a.py", 60, 0), ("src/b.PY", 20, 0), ("web/app.ts", 15, 0)]),
        make_commit(at(2024, 1, 2), files=[("Makefile", 5, 0), ("src/a.py", 0, 0)]),
    ]
    rows = extension_churn(commits)
    assert [(r.extension, r.language, r.lines_changed, r.files) for r in rows] == [
        (".py", "Python", 80, 2), (".ts", "TypeScript", 15, 1), ("(no extension)", "(no extension)", 5, 1),
    ]
    assert rows[0].share == pytest.approx(0.8)


@pytest.mark.parametrize(
    "path, expected",
    [("a/b/c.TXT", ".txt"), (".gitignore", ".gitignore"), ("Dockerfile", "(no extension)"), ("x.tar.gz", ".gz")],
)
def test_file_extension(path, expected):
    assert file_extension(path) == expected


# ---------------------------------------------------------------- timeline


def test_weekly_timeline_fills_quiet_weeks_with_zeros():
    commits = [
        make_commit(at(2024, 3, 6), "small", [("a.py", 1, 0)]),      # Wednesday, week of 4 March
        make_commit(at(2024, 3, 8), "the big one", [("a.py", 90, 9)]),
        make_commit(at(2024, 3, 20), "later", [("a.py", 2, 2)]),      # week of 18 March
    ]
    weeks = weekly_timeline(commits)
    assert [w.start for w in weeks] == [date(2024, 3, 4), date(2024, 3, 11), date(2024, 3, 18)]
    assert [w.commits for w in weeks] == [2, 0, 1]
    assert weeks[0].top_message == "the big one"
    assert (weeks[0].lines_added, weeks[0].lines_removed) == (91, 9)
    assert weeks[1].top_message == ""


def test_weekly_timeline_prefers_real_commits_over_merges_for_the_top_message():
    commits = [
        make_commit(at(2024, 3, 6), "real work", [("a.py", 1, 0)]),
        make_commit(at(2024, 3, 7), "Merge branch 'x'", [("a.py", 500, 0)], parents=("1" * 40, "2" * 40)),
    ]
    assert weekly_timeline(commits)[0].top_message == "real work"


# ---------------------------------------------------------------- contributors


def test_contributors_are_grouped_by_email_and_ranked():
    commits = [
        make_commit(at(2024, 1, 1), files=[("a.py", 10, 0)], name="Ada", email="ADA@example.com"),
        make_commit(at(2024, 1, 5), files=[("a.py", 5, 2)], name="Ada Lovelace", email="ada@example.com"),
        make_commit(at(2024, 1, 9), files=[("a.py", 1, 1)], name="Ada Lovelace", email="ada@example.com"),
        make_commit(at(2024, 1, 3), files=[("b.py", 99, 0)], name="Grace Hopper", email="grace@example.com"),
    ]
    ada, grace = contributor_stats(commits, sparkline_buckets=4)
    assert (ada.name, ada.commits, ada.lines_added, ada.lines_removed) == ("Ada Lovelace", 3, 16, 3)
    assert (ada.first_active, ada.last_active) == (date(2024, 1, 1), date(2024, 1, 9))
    assert ada.initials == "AL"
    assert ada.sparkline == [1, 0, 1, 1]
    assert grace.sparkline == [0, 1, 0, 0]
    assert sum(ada.sparkline) == ada.commits


def test_initials_and_avatar_colour():
    assert initials("Ada Lovelace") == "AL"
    assert initials("linus") == "LI"
    assert initials("mary-jane o'neil") == "MO"
    assert initials("   ") == "?"
    assert avatar_color("Ada@Example.com") == avatar_color("ada@example.com ")
    assert avatar_color("ada@example.com") != avatar_color("grace@example.com")
    assert avatar_color("ada@example.com").startswith("hsl(")


# ---------------------------------------------------------------- messages


def test_conventional_type():
    assert conventional_type("feat: add thing") == "feat"
    assert conventional_type("Fix(parser)!: handle renames") == "fix"
    assert conventional_type("docs(readme): typo") == "docs"
    assert conventional_type("feature: not a real type") is None
    assert conventional_type("fix the build") is None
    assert conventional_type("fix:") is None


def test_significant_words_drops_stopwords_and_prefixes():
    assert significant_words("fix(parser): Handle the renames in a parser") == ["handle", "renames", "parser"]
    assert significant_words("Añade soporte para café") == ["añade", "soporte", "para", "café"]


def test_message_insights():
    commits = [
        make_commit(at(2024, 1, 1), "feat: add the parser"),
        make_commit(at(2024, 1, 2), "fix: parser crash on empty repos\n\nLong body that is ignored."),
        make_commit(at(2024, 1, 3), "WIP"),
        make_commit(at(2024, 1, 4), "Tidy the parser tests"),
        make_commit(at(2024, 1, 5), "Merge branch 'main' into parser parser parser", parents=("1" * 40, "2" * 40)),
    ]
    insights = message_insights(commits)
    assert insights.analysed == 4  # the merge commit is skipped
    assert insights.conventional_count == 2
    assert insights.conventional_share == pytest.approx(0.5)
    assert {(t.type, t.count) for t in insights.conventional_types} == {("feat", 1), ("fix", 1)}
    assert (insights.common_words[0].word, insights.common_words[0].count) == ("parser", 3)
    assert insights.shortest is not None and insights.shortest.text == "WIP"
    assert insights.longest is not None and insights.longest.text == "fix: parser crash on empty repos"
    assert insights.average_length == pytest.approx((20 + 32 + 3 + 21) / 4)


# ---------------------------------------------------------------- summary and the full report


def test_summarize():
    commits = [
        make_commit(at(2024, 1, 1), files=[("a.py", 10, 0)]),
        make_commit(at(2024, 1, 11), files=[("a.py", 2, 3), ("b.py", 1, 0)], name="Grace", email="grace@example.com"),
        make_commit(at(2024, 1, 6), "Merge", parents=("1" * 40, "2" * 40)),
    ]
    summary = summarize(commits)
    assert (summary.commits, summary.contributors, summary.merges, summary.files_touched) == (3, 2, 1, 2)
    assert (summary.lines_added, summary.lines_removed) == (13, 3)
    assert (summary.first_commit, summary.last_commit) == (at(2024, 1, 1), at(2024, 1, 11))
    assert summary.age_days == 10


def test_single_commit_repository():
    report = build_report([make_commit(at(2024, 6, 1), "Initial commit", [("README.md", 3, 0)])], "solo")
    assert report.summary.commits == 1
    assert report.summary.age_days == 1
    assert len(report.timeline) == 1
    assert report.facts.longest_streak.days == 1
    assert report.facts.longest_gap is None
    assert report.facts.busiest_day.commits == 1
    assert report.contributors[0].sparkline[0] == 1
    assert report.to_dict()["repo_name"] == "solo"


def test_commits_without_any_file_changes():
    report = build_report([make_commit(at(2024, 6, 1), "empty"), make_commit(at(2024, 6, 2), "also empty")], "empty")
    assert report.files == [] and report.extensions == []
    assert report.facts.biggest_commit is not None and report.facts.biggest_commit.lines_added == 0


def test_empty_history_is_rejected():
    with pytest.raises(ValueError):
        build_report([], "nothing")
