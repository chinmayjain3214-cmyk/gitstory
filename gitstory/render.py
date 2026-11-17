"""Build the self-contained HTML report.

The template, stylesheet and script live in ``gitstory/assets`` as ordinary
files (so editors can highlight them) and are inlined into a single HTML
document here. The analysis results are embedded as one JSON blob that the
script reads and draws from; nothing is fetched over the network.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from . import __version__
from .stats import Report

THEMES = ("dark", "light")

_PLACEHOLDER = re.compile(r"\{\{(TITLE|THEME|CSS|JS|DATA|VERSION)\}\}")

# Characters that are legal inside JSON but unsafe inside an HTML <script>
# element (or, for U+2028/U+2029, inside older JavaScript parsers). Each is
# replaced by its \uXXXX escape, which JSON.parse turns back into the original.
_SCRIPT_UNSAFE = {
    "<": "\\u003c",
    ">": "\\u003e",
    "&": "\\u0026",
    "\u2028": "\\u2028",
    "\u2029": "\\u2029",
}


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"cannot serialise {type(value).__name__} to JSON")


def to_script_safe_json(data: Any) -> str:
    """Serialise ``data`` to JSON that can be embedded inside a ``<script>`` tag.

    A commit message containing ``</script>`` or ``<!--`` must not be able to
    end the script element early, so every ``<``, ``>`` and ``&`` is escaped.
    """
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=_json_default)
    for char, escaped in _SCRIPT_UNSAFE.items():
        text = text.replace(char, escaped)
    return text


def load_asset(name: str) -> str:
    """Read one of the packaged template files."""
    return (resources.files(__package__) / "assets" / name).read_text(encoding="utf-8")


def build_payload(
    report: Report,
    generated_at: Optional[datetime] = None,
    filters: Optional[Mapping[str, Optional[str]]] = None,
    source: Optional[Mapping[str, str]] = None,
    links: Optional[Sequence[Mapping[str, str]]] = None,
    download: Optional[str] = None,
) -> Dict[str, Any]:
    """The JSON document embedded in the page: the report plus some metadata.

    ``source`` (``{"label", "url"}``) is shown under the title, for reports of
    a GitHub repository. ``links`` (``[{"label", "href"}]``) adds a small
    navigation bar; the web mode uses it for "New story". ``download`` is a
    same-site path that serves the offline HTML copy; without it the page
    saves a copy of itself.
    """
    payload = report.to_dict()
    payload["meta"] = {
        "version": __version__,
        "generated_at": (generated_at or datetime.now().astimezone()).isoformat(timespec="seconds"),
        "filters": {key: value for key, value in (filters or {}).items() if value},
        "source": dict(source) if source else None,
        "links": [dict(link) for link in links] if links else [],
        "download": download,
    }
    return payload


def _check_theme(theme: str) -> None:
    if theme not in THEMES:
        raise ValueError(f"unknown theme {theme!r}; choose one of {', '.join(THEMES)}")


def _fill(template: str, values: Mapping[str, str]) -> str:
    # A single pass, so text inside the data can never be mistaken for a placeholder.
    return _PLACEHOLDER.sub(lambda match: values.get(match.group(1), ""), load_asset(template))


def render_report(
    report: Report,
    theme: str = "dark",
    generated_at: Optional[datetime] = None,
    filters: Optional[Mapping[str, Optional[str]]] = None,
    source: Optional[Mapping[str, str]] = None,
    links: Optional[Sequence[Mapping[str, str]]] = None,
    download: Optional[str] = None,
) -> str:
    """Return the complete HTML document for ``report`` as a string."""
    _check_theme(theme)
    return _fill("template.html", {
        "TITLE": html.escape(f"{report.repo_name} · gitstory"),
        "THEME": theme,
        "CSS": load_asset("report.css"),
        "JS": load_asset("report.js"),
        "DATA": to_script_safe_json(build_payload(report, generated_at, filters, source, links, download)),
    })


def render_home(theme: str = "dark", examples: Optional[List[str]] = None,
                public: bool = False, max_repo_mb: Optional[int] = None) -> str:
    """Return the web mode's landing page: what gitstory does, and a link form.

    ``public`` switches the wording from "on this computer" to a hosted site.
    """
    _check_theme(theme)
    return _fill("home.html", {
        "TITLE": "gitstory · the story of any GitHub repository",
        "THEME": theme,
        "VERSION": html.escape(__version__),
        "CSS": load_asset("report.css") + "\n" + load_asset("home.css"),
        "JS": load_asset("home.js"),
        "DATA": to_script_safe_json({"version": __version__, "examples": examples or [],
                                     "public": public, "max_repo_mb": max_repo_mb}),
    })


def write_report(document: str, output: Union[str, Path]) -> Path:
    """Write the HTML document to ``output`` (creating folders as needed)."""
    path = Path(output)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    # open() rather than Path.write_text(): its newline argument needs Python 3.10.
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(document)
    return path
