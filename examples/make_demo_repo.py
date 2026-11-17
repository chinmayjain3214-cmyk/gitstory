"""Create a throwaway git repository with a made-up history.

Useful for trying gitstory out, taking screenshots, or checking how the report
looks with a couple of years of activity:

    python examples/make_demo_repo.py orbit-demo
    gitstory orbit-demo -o examples/demo-report.html

Every author, commit and file in the generated repository is fictional. The
history is deterministic (seeded), so the report looks the same on every run.
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# name, email, UTC offset in hours, share of commits, favourite hour, first day, last day
AUTHORS: List[Tuple[str, str, float, float, int, int, int]] = [
    ("Ada Okafor", "ada@orbit.example", 1, 0.38, 10, 0, 720),
    ("Mateus Lindqvist", "mateus@orbit.example", -3, 0.24, 15, 20, 720),
    ("Priya Raman", "priya@orbit.example", 5.5, 0.18, 22, 90, 640),
    ("Yuki Tanabe", "yuki@orbit.example", 9, 0.12, 7, 200, 720),
    ("Tomás Herrera", "tomas@orbit.example", -6, 0.08, 19, 330, 560),
]

FILES = [
    "orbit/core.py", "orbit/scheduler.py", "orbit/api/routes.py", "orbit/api/auth.py",
    "orbit/storage/sqlite.py", "orbit/cli.py", "web/src/App.tsx", "web/src/components/Timeline.tsx",
    "web/src/components/Sidebar.tsx", "web/src/styles.css", "web/index.html", "tests/test_core.py",
    "tests/test_scheduler.py", "tests/test_api.py", "docs/guide.md", "docs/architecture.md",
    "README.md", "pyproject.toml", "Makefile", ".github/workflows/ci.yml",
]

THINGS = [
    "retry logic", "the scheduler queue", "login flow", "timeline zoom", "sqlite migrations",
    "sidebar filters", "token refresh", "the export command", "dark mode", "rate limiting",
    "pagination", "keyboard shortcuts", "error messages", "the job runner", "search indexing",
]
CONVENTIONAL = {
    "feat": ["add {t}", "support {t} in the api", "introduce {t}"],
    "fix": ["handle empty input in {t}", "stop {t} from crashing on restart", "correct off-by-one in {t}"],
    "docs": ["explain {t} in the guide", "update readme for {t}"],
    "refactor": ["simplify {t}", "split {t} into smaller functions"],
    "test": ["cover {t} edge cases"],
    "chore": ["bump dependencies", "tidy ci config"],
    "perf": ["cache results for {t}"],
}
PLAIN = [
    "Fix typo", "WIP", "Make {t} faster", "Clean up {t}", "Rework {t} after review feedback",
    "Oops, forgot a file", "Update {t}", "Remove dead code around {t}",
    "Rewrite {t} so that it no longer blocks the event loop when the queue is full",
]


def git(repo: Path, *args: str, env: Optional[Dict[str, str]] = None) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def commit(repo: Path, message: str, author: Sequence, when: datetime) -> None:
    stamp = when.isoformat(timespec="seconds")
    env = dict(os.environ, GIT_AUTHOR_NAME=author[0], GIT_AUTHOR_EMAIL=author[1], GIT_AUTHOR_DATE=stamp,
               GIT_COMMITTER_NAME=author[0], GIT_COMMITTER_EMAIL=author[1], GIT_COMMITTER_DATE=stamp)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message, env=env)


def edit(repo: Path, rng: random.Random, path: str, serial: int) -> None:
    """Append some lines to a file and, sometimes, delete a few from the top."""
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    if len(lines) > 12 and rng.random() < 0.45:
        del lines[: rng.randint(1, min(30, len(lines) // 3))]
    lines += [f"change {serial} line {i}" for i in range(rng.randint(2, 40) * (4 if rng.random() < 0.06 else 1))]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_message(rng: random.Random) -> str:
    thing = rng.choice(THINGS)
    if rng.random() < 0.62:
        kind = rng.choices(list(CONVENTIONAL), weights=[30, 28, 10, 12, 8, 8, 4])[0]
        scope = rng.choice(["", "", "(api)", "(web)", "(core)"])
        return f"{kind}{scope}: {rng.choice(CONVENTIONAL[kind]).format(t=thing)}"
    return rng.choice(PLAIN).format(t=thing)


def build(repo: Path, seed: int = 7) -> int:
    rng = random.Random(seed)
    files = list(FILES)
    repo.mkdir(parents=True, exist_ok=False)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "commit.gpgsign", "false")

    start = datetime(2024, 11, 4, tzinfo=timezone.utc)
    made = 0
    for day in range(721):
        if 400 <= day < 431:  # a month where nothing happened
            continue
        date = start + timedelta(days=day)
        weekend = date.weekday() >= 5
        # Busy launch, quieter middle, second wind near the end.
        phase = 1.5 if day < 120 else (0.45 if day < 400 else 0.95)
        expected = phase * (0.25 if weekend else 1.0) * 0.72
        for _ in range(sum(1 for _ in range(6) if rng.random() < expected / 6) + (3 if rng.random() < 0.02 else 0)):
            active = [a for a in AUTHORS if a[5] <= day <= a[6]]
            author = rng.choices(active, weights=[a[3] for a in active])[0]
            hour = int(rng.gauss(author[4], 2.2)) % 24
            tz = timezone(timedelta(hours=author[2]))
            when = datetime(date.year, date.month, date.day, hour, rng.randint(0, 59), rng.randint(0, 59), tzinfo=tz)
            for path in rng.sample(files, rng.choices([1, 2, 3, 5], weights=[50, 28, 16, 6])[0]):
                edit(repo, rng, path, made)
            if made == 60:  # one binary file
                (repo / "web").mkdir(exist_ok=True)
                (repo / "web" / "logo.png").write_bytes(bytes(rng.getrandbits(8) for _ in range(2048)))
            if made == 180:  # and one rename
                git(repo, "mv", "orbit/storage/sqlite.py", "orbit/storage/database.py")
                files[files.index("orbit/storage/sqlite.py")] = "orbit/storage/database.py"
            commit(repo, make_message(rng), author, when)
            made += 1
    return made


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("destination", nargs="?", default="orbit-demo",
                        help="folder to create the repository in (must not exist yet)")
    args = parser.parse_args(argv)
    destination = Path(args.destination)
    if destination.exists():
        print(f"error: {destination} already exists; pick a new folder name", file=sys.stderr)
        return 1
    made = build(destination)
    print(f"Created {destination} with {made} fictional commits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
