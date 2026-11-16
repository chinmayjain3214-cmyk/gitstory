"""Command-line interface: ``gitstory [repo] -o report.html``."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .parser import GitStoryError, get_repo_name, read_commits
from .render import THEMES, render_report, write_report
from .stats import build_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitstory",
        description="Turn a git repository's history into a self-contained, animated HTML report.",
        epilog="Example: gitstory ~/code/my-project -o story.html --since '1 year ago' --open",
    )
    parser.add_argument(
        "repo", nargs="?", default=".",
        help="path to a local git repository (default: the current directory)",
    )
    parser.add_argument(
        "-o", "--output", default="gitstory.html", metavar="FILE",
        help="where to write the report (default: gitstory.html)",
    )
    parser.add_argument(
        "--since", metavar="DATE",
        help="only include commits after this date; passed to git log, so '2024-01-01' and '6 months ago' both work",
    )
    parser.add_argument(
        "--until", metavar="DATE",
        help="only include commits before this date; passed to git log",
    )
    parser.add_argument(
        "--author", metavar="PATTERN",
        help="only include commits whose author name or email matches this pattern",
    )
    parser.add_argument(
        "--theme", choices=THEMES, default="dark",
        help="colour theme the report opens in (default: dark)",
    )
    parser.add_argument(
        "--open", action="store_true", dest="open_report",
        help="open the report in your default browser when it is ready",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _count(number: int, noun: str) -> str:
    """``1 commit``, ``2 commits``, ``1,234 commits``."""
    return f"{number:,} {noun}" + ("" if number == 1 else "s")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``gitstory`` console script. Returns the exit code."""
    args = build_parser().parse_args(argv)
    try:
        commits = read_commits(args.repo, since=args.since, until=args.until, author=args.author)
        report = build_report(commits, get_repo_name(args.repo))
        document = render_report(
            report,
            theme=args.theme,
            filters={"since": args.since, "until": args.until, "author": args.author},
        )
        output = write_report(document, args.output)
    except GitStoryError as error:
        print(f"gitstory: error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"gitstory: error: could not write {args.output}: {error}", file=sys.stderr)
        return 1

    summary = report.summary
    # Plain ASCII on purpose: legacy Windows consoles cannot print much else.
    print(
        f"Wrote {output} ({_count(summary.commits, 'commit')}, "
        f"{_count(summary.contributors, 'contributor')}, {_count(summary.age_days, 'day')} of history)"
    )
    if args.open_report:
        webbrowser.open(Path(output).resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
