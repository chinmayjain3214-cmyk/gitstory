"""Command-line interface: ``gitstory [repo] -o report.html``."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import __version__
from .github import clone_repository, looks_like_github_url, parse_github_url
from .parser import Commit, GitStoryError, NoCommitsError, get_repo_name, read_commits
from .render import THEMES, render_report, write_report
from .stats import build_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitstory",
        description="Turn a git repository's history into a self-contained, animated HTML report.",
        epilog="Examples: gitstory ~/code/my-project -o story.html --open\n"
               "          gitstory https://github.com/psf/requests\n"
               "          gitstory --serve --open",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "repo", nargs="?", default=".",
        help="path to a local git repository, or a GitHub link such as "
             "https://github.com/owner/repo (default: the current directory)",
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
        help="open the report (or, with --serve, the website) in your default browser",
    )
    web = parser.add_argument_group("web mode")
    web.add_argument(
        "--serve", action="store_true",
        help="start a local website where you paste a GitHub link and get its story",
    )
    web.add_argument("--host", default=None,
                     help="address to listen on with --serve (default: 127.0.0.1, or 0.0.0.0 with --public)")
    web.add_argument("--port", type=int, default=None,
                     help="port to listen on with --serve (default: 8765, or $PORT with --public; 0 picks a free one)")
    web.add_argument(
        "--public", action="store_true",
        help="run the web mode as a public website (for hosting): accept any address, "
             "log each story, and limit repository size and requests per visitor",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _print_progress(slug: str):
    """A callback that redraws one status line while git clones (terminals only)."""
    if not sys.stderr.isatty():
        return None

    def report(phase: str, percent: Optional[int], size: str) -> None:
        text = f"Cloning {slug}: {phase.lower()} {percent}%" + (f", {size}" if size else "")
        sys.stderr.write("\r" + text[:78].ljust(78))
        sys.stderr.flush()

    return report


def _load(args: argparse.Namespace) -> Tuple[List[Commit], str, Optional[Dict[str, str]]]:
    """Read the commits for ``args.repo``, cloning it first if it is a GitHub link."""
    filters = {"since": args.since, "until": args.until, "author": args.author}
    if Path(args.repo).exists() or not looks_like_github_url(args.repo):
        return read_commits(args.repo, **filters), get_repo_name(args.repo), None

    repo = parse_github_url(args.repo, allow_shorthand=False)
    print(f"Cloning {repo.web_url} ...", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="gitstory-") as folder:
        progress = _print_progress(repo.slug)
        try:
            clone = clone_repository(repo, Path(folder) / "repo.git", on_progress=progress)
        finally:
            if progress:
                sys.stderr.write("\r" + " " * 78 + "\r")
        try:
            commits = read_commits(clone, **filters)
        except NoCommitsError as error:
            if any(filters.values()):
                raise
            raise NoCommitsError(f"{repo.slug} has no commits yet") from error
    return commits, repo.name, {"label": f"github.com/{repo.slug}", "url": repo.web_url}


def _count(number: int, noun: str) -> str:
    """``1 commit``, ``2 commits``, ``1,234 commits``."""
    return f"{number:,} {noun}" + ("" if number == 1 else "s")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``gitstory`` console script. Returns the exit code."""
    args = build_parser().parse_args(argv)
    if args.serve:
        from .server import serve  # imported lazily: only the web mode needs it

        try:
            host = args.host or ("0.0.0.0" if args.public else "127.0.0.1")
            port = args.port
            if port is None:
                port = int(os.environ.get("PORT", 8765)) if args.public else 8765
            return serve(host, port, open_browser=args.open_report, public=args.public)
        except GitStoryError as error:
            print(f"gitstory: error: {error}", file=sys.stderr)
            return 1
    try:
        commits, name, source = _load(args)
        report = build_report(commits, name)
        document = render_report(
            report,
            theme=args.theme,
            filters={"since": args.since, "until": args.until, "author": args.author},
            source=source,
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
