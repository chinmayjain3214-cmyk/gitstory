# gitstory

**Every repository has a story. gitstory turns yours into one beautiful, animated HTML page.**

Point it at any local git repository and get a single self-contained report: who built it, when the code gets written, which files never sit still, and a handful of fun facts. No server, no account, no dependencies, and it works offline.

![A gitstory report](docs/screenshot.png)

> The screenshot shows the report for the fictional demo repository built by [`examples/make_demo_repo.py`](examples/make_demo_repo.py). Replace `docs/screenshot.png` with a capture of your own report whenever you like.

## Features

- **Hero summary**: repository name, first and latest commit, total commits, contributors, lines added and removed, and project age, with numbers that count up on load.
- **Animated timeline**: commits per week, drawn left to right. Hover (or use the arrow keys) to see the week, its commit count and its top commit message.
- **Contributors**: ranked cards with coloured avatar initials, commit and line counts, first and last active dates, and an activity sparkline.
- **When the code gets written**: a 7×24 heatmap of commit times plus a label derived from the data, such as "Night owl 🦉" or "9-to-5er ☀️".
- **File churn**: the 15 most-changed files and the top languages by lines changed. Renamed files keep their history.
- **Commit message insights**: average length, most common words, share of conventional-commit prefixes, and the longest and shortest messages.
- **Fun facts**: biggest single commit, longest streak, longest gap and busiest day ever.
- **One file, zero requests**: all CSS, JavaScript and data are inlined. Charts are hand-drawn SVG, with no chart library and no CDN.
- **Dark and light themes**, a responsive layout down to phone width, scroll-in animations, and full support for `prefers-reduced-motion`.
- **Standard library only**: Python 3.9+ and `git`. Nothing else to install.
- **Private by default**: email addresses are used to group commits and pick avatar colours, but are never written into the report.

## Install

You need Python 3.9 or newer and `git` on your `PATH`.

```bash
# from a clone of this repository
pip install .

# or straight from GitHub, isolated with pipx
pipx install git+https://github.com/<user>/gitstory
```

Replace `<user>` with the GitHub account that hosts the repository.

### Development setup (virtual environment)

```bash
git clone https://github.com/<user>/gitstory
cd gitstory

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"          # gitstory itself (editable) plus pytest
pytest
```

gitstory has no runtime dependencies; `pytest` is the only thing the `dev` extra adds.

## Usage

```bash
gitstory /path/to/repo -o report.html
```

Every flag:

```bash
# Report on the current directory, written to ./gitstory.html
gitstory

# Choose the repository and the output file
gitstory ~/code/my-project -o story.html

# Only part of the history (anything `git log` understands)
gitstory --since "2024-01-01" --until "2024-12-31"
gitstory --since "6 months ago"

# Only one person's commits (matches the author name or email)
gitstory --author "Ada"

# Open in the light theme (the page also has a toggle)
gitstory --theme light

# Open the report in your default browser when it is ready
gitstory ~/code/my-project -o story.html --open

# Also available as a module
python -m gitstory . -o report.html

gitstory --version
gitstory --help
```

| Option | Default | What it does |
| --- | --- | --- |
| `repo` | `.` | Path to a local git repository (any folder inside it works). |
| `-o`, `--output` | `gitstory.html` | Where to write the report. Missing folders are created. |
| `--since DATE` | none | Only commits after this date. Passed through to `git log`. |
| `--until DATE` | none | Only commits before this date. Passed through to `git log`. |
| `--author PATTERN` | none | Only commits whose author matches. Passed through to `git log`. |
| `--theme dark\|light` | `dark` | Theme the report opens in. |
| `--open` | off | Open the report in the default browser afterwards. |
| `--version` | | Print the version and exit. |

Errors are short and specific, and the exit code is `1`:

```text
gitstory: error: not a git repository: /tmp/somewhere
gitstory: error: this repository has no commits yet: /tmp/empty
gitstory: error: no commits match the given --since/--until/--author filters
gitstory: error: git was not found. Install it from https://git-scm.com/downloads and make sure it is on your PATH.
```

## Examples

- [`examples/sample-report.html`](examples/sample-report.html): gitstory run on its own repository.
- [`examples/demo-report.html`](examples/demo-report.html): a two-year, five-person fictional project, which shows the charts with more data.
- [`examples/make_demo_repo.py`](examples/make_demo_repo.py): builds that fictional repository so you can reproduce the demo:

  ```bash
  python examples/make_demo_repo.py orbit-demo
  gitstory orbit-demo -o examples/demo-report.html
  ```

Download a report and open it in a browser; GitHub shows HTML files as source.

## How it works

```text
git log ──► parser.py ──► stats.py ──► render.py ──► report.html
 (subprocess)  (dataclasses)  (pure functions)  (JSON + inline CSS/JS)
```

1. **`parser.py`** runs one `git log --numstat` through `subprocess`, with a `--pretty=format:` string that separates commits and fields with the ASCII record and unit separator characters (`0x1e`, `0x1f`), which do not occur in normal commit text. The output is decoded with `errors="replace"` and parsed into `Commit` and `FileChange` dataclasses.
2. **`stats.py`** is a set of pure functions over those commits: no subprocess calls, no file access, no clock. That is what the test-suite exercises with synthetic histories.
3. **`render.py`** serialises the results to one JSON blob, escapes it so that text such as `</script>` in a commit message cannot break out of the page, and inlines it together with the stylesheet and script from `gitstory/assets/` into a single HTML document.
4. **In the browser**, a small vanilla-JS renderer reads the JSON and draws everything with DOM and SVG. Repository text is always inserted as text, never as HTML.

### Project layout

```text
gitstory/
├── gitstory/
│   ├── __init__.py
│   ├── __main__.py        # python -m gitstory
│   ├── cli.py             # argparse + entry point
│   ├── parser.py          # runs git log, parses it into dataclasses
│   ├── stats.py           # all the analysis, pure functions
│   ├── render.py          # builds the HTML
│   └── assets/            # template.html, report.css, report.js (package data)
├── tests/
│   ├── test_parser.py     # parses a fixed sample git-log string
│   ├── test_stats.py      # streaks, heatmap, churn on synthetic commits
│   ├── test_render.py     # JSON escaping, self-containment
│   └── test_cli.py        # end to end against a temporary repository
├── examples/
├── docs/screenshot.png
├── pyproject.toml
├── LICENSE
└── README.md
```

## Design decisions

Where the idea left room for interpretation, these are the choices gitstory makes:

- **Which commits**: the history reachable from the checked-out branch (`HEAD`), as `git log` lists it.
- **Which date**: the author date, in the author's own timezone. "Day", "week" and "hour" always mean the local calendar of whoever made the commit, so a commit made at 23:30 in New York counts as a late-night commit wherever the report is generated. Ordering and gaps use absolute time.
- **Weeks** start on Monday. Quiet weeks appear as zeros so the timeline keeps its real shape. Histories of 26 weeks or fewer are drawn as bars; longer ones as an area chart.
- **Top commit message** of a week is the subject of its largest non-merge commit by lines changed.
- **Merge commits** count as commits but carry no line statistics (git reports none for them by default, which avoids counting the same change twice). They are left out of the commit-message insights because their messages are usually auto-generated.
- **Binary files** (`-` in numstat) count as a file change with zero lines.
- **Renames** are detected by git (`-M`) and followed: a renamed file's earlier churn moves to its new name.
- **People** are grouped by email address, case-insensitively, and shown under the name they used most. A `.mailmap` file is respected. The contributors section lists the top 30.
- **Project age** is the time between the first and the latest commit, rounded up to whole days, and at least one day.
- **Commit-message statistics** use the subject line (the first line) only. Common words are case-insensitive, at least three letters long, with English stopwords and any conventional-commit prefix removed.
- **Conventional commits** recognised: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`, with an optional scope and `!`.
- **The fun label** is picked from the heatmap in this order: Weekend warrior (at least 50% of commits on Saturday or Sunday), Night owl (30% between 22:00 and 04:00), Early bird (30% between 05:00 and 09:00), 9-to-5er (60% on weekdays between 09:00 and 18:00), After-hours hacker (35% between 18:00 and 22:00), otherwise Round-the-clock coder.
- **Languages** are inferred from file extensions with a small built-in table; unknown extensions are shown as they are.
- **Template location**: the HTML, CSS and JS live as package-data files in `gitstory/assets/` rather than in one Python string, so they get proper editor support.
- **A theme toggle** is included in the report in addition to `--theme`.

Known limits: the whole `git log` output is held in memory, so repositories with hundreds of thousands of commits take a while; and a file whose name literally contains ` => ` is read as a rename.

## Tests

```bash
pytest
```

The suite covers the parser (merges, binary files, both rename notations, quoted paths, undecodable bytes, timezones), the statistics (streaks, gaps, heatmap, churn, personas, message insights, single-commit histories), the renderer (script-safe JSON, no external requests) and the CLI end to end.

## Roadmap

- GitHub API mode: report on a remote repository without cloning it, with pull requests and issues.
- Compare two repositories, or two periods of the same one, side by side.
- Export the report, or single charts, as PNG.
- `--exclude` patterns for lockfiles and generated code.
- Per-contributor pages and a yearly "wrapped" view.
- Translations of the report text.

## Contributing

Issues and pull requests are welcome. Please run `pytest` before opening one, and keep `stats.py` free of side effects.

## License

[MIT](LICENSE)
