"""``gitstory --serve``: a small local website for GitHub repositories.

The home page explains what gitstory does and asks for a GitHub link. Once the
visitor confirms, a background job clones the repository into a temporary
folder, runs the normal analysis, deletes the clone and keeps the finished
report in memory. The page polls the job for progress and then opens the
report.

Routes::

    GET  /                               home page
    POST /api/resolve   {"url": ...}     check a link, return the repository it names
    POST /api/stories   {"url": ...}     start (or reuse) a job, 202 + job JSON
    GET  /api/stories/<id>               job status and progress
    GET  /story/<owner>/<repo>           the finished report
    GET  /story/<owner>/<repo>/download  the same report as a standalone offline file

Only the standard library is used. The server binds to 127.0.0.1 by default,
only accepts JSON for POSTs (so other websites cannot submit forms to it) and
checks the Host header (so DNS-rebinding pages cannot reach it).
"""

from __future__ import annotations

import json
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import os
from collections import deque
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

from .github import GitHubRepo, clone_repository, parse_github_url
from .parser import GitStoryError, NoCommitsError, read_commits
from .render import render_home, render_report
from .stats import Report, build_report

CloneFunction = Callable[..., Path]

EXAMPLES = ["pallets/itsdangerous", "psf/requests", "expressjs/express"]
MAX_BODY = 4096
MAX_CONCURRENT_CLONES = 2

PHASE_LABELS = {
    "Counting": "Counting objects",
    "Compressing": "Compressing objects",
    "Receiving": "Downloading",
    "Resolving": "Unpacking",
}


# --------------------------------------------------------------------------
# Limits for a public server
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Limits:
    """What one visitor may ask of a server that is open to everyone.

    The defaults (no limits) suit gitstory on your own computer; ``public()``
    gives settings for a small free hosting plan, each one adjustable with an
    environment variable.
    """

    max_repo_mb: Optional[int] = None        # stop clones that download more than this
    clone_timeout: float = 900.0             # seconds
    max_stories: Optional[int] = None        # finished stories kept in memory
    max_waiting: Optional[int] = None        # stories being built or waiting at once
    per_client: Optional[int] = None         # new stories per visitor ...
    per_client_window: float = 600.0         # ... in this many seconds
    workers: int = MAX_CONCURRENT_CLONES     # stories built at the same time

    @classmethod
    def public(cls, env: Optional[Dict[str, str]] = None) -> "Limits":
        env = dict(os.environ if env is None else env)

        def number(name: str, default: float) -> float:
            try:
                return float(env.get(name, default))
            except ValueError:
                return default

        return cls(
            max_repo_mb=int(number("GITSTORY_MAX_REPO_MB", 150)),
            clone_timeout=number("GITSTORY_CLONE_TIMEOUT", 300),
            max_stories=int(number("GITSTORY_MAX_STORIES", 10)),
            max_waiting=int(number("GITSTORY_MAX_WAITING", 6)),
            per_client=int(number("GITSTORY_PER_VISITOR", 6)),
            per_client_window=number("GITSTORY_PER_VISITOR_WINDOW", 600),
            workers=max(1, int(number("GITSTORY_WORKERS", 1))),   # one at a time fits in 512 MB
        )


class Busy(GitStoryError):
    """The server cannot take another story right now."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------


@dataclass
class Job:
    id: str
    repo: GitHubRepo
    state: str = "queued"  # queued -> cloning -> analysing -> done | error
    phase: str = ""
    percent: Optional[int] = None
    detail: str = ""
    error: str = ""
    created: float = field(default_factory=time.monotonic)
    finished: Optional[float] = None
    report: Optional[Report] = None

    @property
    def report_path(self) -> str:
        return f"/story/{self.repo.owner}/{self.repo.name}"

    def to_json(self) -> Dict[str, Any]:
        end = self.finished if self.finished is not None else time.monotonic()
        data: Dict[str, Any] = {
            "id": self.id,
            "repo": {"slug": self.repo.slug, "url": self.repo.web_url},
            "state": self.state,
            "phase": self.phase,
            "percent": self.percent,
            "detail": self.detail,
            "error": self.error,
            "elapsed": round(end - self.created, 1),
        }
        if self.state == "done" and self.report is not None:
            summary = self.report.summary
            data["report_url"] = self.report_path
            data["summary"] = {"commits": summary.commits, "contributors": summary.contributors}
        return data


class StoryService:
    """Runs and remembers jobs. Thread-safe; one instance per server."""

    def __init__(self, workdir: Path, clone: CloneFunction = clone_repository,
                 max_concurrent: int = MAX_CONCURRENT_CLONES, limits: Limits = Limits(),
                 log: Optional[Callable[[str], None]] = None) -> None:
        self.workdir = Path(workdir)
        self.clone = clone
        self.limits = limits
        self.log = log or (lambda message: None)
        self._jobs: Dict[str, Job] = {}
        self._by_slug: Dict[str, Job] = {}
        self._recent: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self._slots = threading.Semaphore(max_concurrent)

    def submit(self, repo: GitHubRepo, refresh: bool = False, client: str = "") -> Job:
        """Start a job for ``repo``, or return the one already running or finished.

        Raises ``Busy`` when a limit says no.
        """
        key = repo.slug.lower()
        limits = self.limits
        now = time.monotonic()
        with self._lock:
            existing = self._by_slug.get(key)
            if existing and existing.state != "error" and not (refresh and existing.state == "done"):
                return existing
            if limits.max_waiting is not None:
                waiting = sum(1 for job in self._jobs.values() if job.state not in ("done", "error"))
                if waiting >= limits.max_waiting:
                    raise Busy("gitstory is busy with other stories right now. Try again in a minute.",
                               HTTPStatus.SERVICE_UNAVAILABLE)
            if limits.per_client is not None and client:
                times = self._recent.setdefault(client, deque())
                while times and now - times[0] > limits.per_client_window:
                    times.popleft()
                if len(times) >= limits.per_client:
                    minutes = max(1, int(limits.per_client_window // 60))
                    raise Busy(f"you can build {limits.per_client} new stories every {minutes} minutes. "
                               "Try again a little later.", HTTPStatus.TOO_MANY_REQUESTS)
                times.append(now)
                if len(self._recent) > 10000:      # forget visitors with nothing recent
                    for name in [n for n, t in self._recent.items() if not t]:
                        del self._recent[name]
            job = Job(id=uuid.uuid4().hex[:12], repo=repo)
            self._jobs[job.id] = job
            self._by_slug[key] = job
            self._forget_old()
        self.log(f"story requested: {repo.slug}")
        threading.Thread(target=self._run, args=(job,), name=f"gitstory-{job.id}", daemon=True).start()
        return job

    def _forget_old(self) -> None:
        """Keep at most ``max_stories`` finished stories (and their jobs). Call with the lock held."""
        limit = self.limits.max_stories
        if limit is None:
            return
        finished: List[Job] = sorted((job for job in self._jobs.values() if job.finished is not None),
                                     key=lambda job: job.finished or 0.0)
        for job in finished[:max(0, len(finished) - limit)]:
            self._jobs.pop(job.id, None)
            if self._by_slug.get(job.repo.slug.lower()) is job:
                del self._by_slug[job.repo.slug.lower()]

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def finished_report(self, owner: str, name: str) -> Optional[Job]:
        with self._lock:
            job = self._by_slug.get(f"{owner}/{name}".lower())
        return job if job is not None and job.state == "done" else None

    def _run(self, job: Job) -> None:
        folder = Path(tempfile.mkdtemp(prefix="clone-", dir=self.workdir))
        try:
            with self._slots:
                job.state, job.phase = "cloning", "Connecting to GitHub"

                def progress(phase: str, percent: Optional[int], size: str) -> None:
                    job.phase = PHASE_LABELS.get(phase, phase)
                    job.percent = percent
                    if size:
                        job.detail = size

                options: Dict[str, Any] = {}
                if self.limits.max_repo_mb is not None:
                    options = {"max_bytes": self.limits.max_repo_mb * 1024 * 1024,
                               "timeout": self.limits.clone_timeout}
                clone_path = self.clone(job.repo, folder / "repo.git", on_progress=progress, **options)
                job.state, job.phase, job.percent, job.detail = "analysing", "Reading the history", None, ""
                try:
                    commits = read_commits(clone_path)
                except NoCommitsError:
                    raise NoCommitsError(f"{job.repo.slug} has no commits yet") from None
                job.phase = "Drawing the story"
                job.report = build_report(commits, job.repo.name)
                job.state, job.phase = "done", "Done"
        except GitStoryError as error:
            job.state, job.error = "error", str(error)
        except Exception as error:  # keep the server alive whatever happens
            job.state, job.error = "error", f"something went wrong: {error}"
        finally:
            job.finished = time.monotonic()
            shutil.rmtree(folder, ignore_errors=True)  # the clone is not needed once analysed
            self.log(f"story {job.state}: {job.repo.slug}" + (f" ({job.error})" if job.error else ""))
            with self._lock:
                self._forget_old()


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class StoryServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, SO_REUSEADDR lets a second server bind a port that another
    # one is still listening on, and the old one keeps answering. Ask for the
    # port exclusively there so a stale gitstory can never hide a new one.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if sys.platform == "win32" and exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()

    def __init__(self, address: Tuple[str, int], service: StoryService, public: bool = False) -> None:
        super().__init__(address, StoryHandler)
        self.service = service
        self.public = public
        self.home_page = render_home(examples=EXAMPLES, public=public,
                                     max_repo_mb=service.limits.max_repo_mb)


class StoryHandler(BaseHTTPRequestHandler):
    server: StoryServer
    server_version = "gitstory"
    sys_version = ""

    # -- plumbing ---------------------------------------------------------

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib name
        pass  # keep the terminal quiet; errors are shown in the page

    def _send(self, status: int, body: bytes, content_type: str, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: Dict[str, Any]) -> None:
        self._send(status, json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")

    def _html(self, status: int, document: str, extra: Optional[Dict[str, str]] = None) -> None:
        self._send(status, document.encode("utf-8"), "text/html; charset=utf-8", extra)

    def _client(self) -> str:
        """Who is asking: the first X-Forwarded-For address behind a hosting proxy."""
        if self.server.public:
            forwarded = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if forwarded:
                return forwarded
        return str(self.client_address[0])

    def _host_allowed(self) -> bool:
        if self.server.public:
            return True   # a public site is reached by its own name; there is no local server to protect
        host = (self.headers.get("Host") or "").strip().lower()
        if host.startswith("["):
            name = host[1:].split("]", 1)[0]
        else:
            name = host.rsplit(":", 1)[0] if ":" in host else host
        bound = self.server.server_address[0]
        return name in {"localhost", "127.0.0.1", "::1", str(bound).lower()} or bound in ("0.0.0.0", "::")

    def _read_json(self) -> Optional[Dict[str, Any]]:
        if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "send JSON"})
            return None
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large"})
            return None
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            data = None
        if not isinstance(data, dict):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "send a JSON object"})
            return None
        return data

    def _repo_from(self, data: Dict[str, Any]) -> Optional[GitHubRepo]:
        try:
            return parse_github_url(str(data.get("url") or ""))
        except GitStoryError as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return None

    # -- routes -----------------------------------------------------------

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib name
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802 - stdlib name
        if not self._host_allowed():
            self._json(HTTPStatus.FORBIDDEN, {"error": "unexpected Host header"})
            return
        path = urlsplit(self.path).path
        parts = [unquote(part) for part in path.strip("/").split("/") if part]

        if not parts:
            self._html(HTTPStatus.OK, self.server.home_page)
        elif parts == ["healthz"]:
            self._send(HTTPStatus.OK, b"ok\n", "text/plain; charset=utf-8")
        elif parts == ["favicon.ico"]:
            self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
        elif len(parts) == 3 and parts[:2] == ["api", "stories"]:
            job = self.server.service.get(parts[2])
            if job is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "no such story"})
            else:
                self._json(HTTPStatus.OK, job.to_json())
        elif parts[0] == "story" and len(parts) in (3, 4) and (len(parts) == 3 or parts[3] == "download"):
            self._story(parts[1], parts[2], download=len(parts) == 4)
        else:
            self._html(HTTPStatus.NOT_FOUND, _not_found_page())

    def do_POST(self) -> None:  # noqa: N802 - stdlib name
        if not self._host_allowed():
            self._json(HTTPStatus.FORBIDDEN, {"error": "unexpected Host header"})
            return
        path = urlsplit(self.path).path.rstrip("/")
        if path not in ("/api/resolve", "/api/stories"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        data = self._read_json()
        if data is None:
            return
        repo = self._repo_from(data)
        if repo is None:
            return
        if path == "/api/resolve":
            self._json(HTTPStatus.OK, {"slug": repo.slug, "owner": repo.owner, "name": repo.name, "url": repo.web_url})
            return
        try:
            job = self.server.service.submit(repo, refresh=bool(data.get("refresh")), client=self._client())
        except Busy as busy:
            self._json(busy.status, {"error": str(busy)})
            return
        self._json(HTTPStatus.ACCEPTED, job.to_json())

    def _story(self, owner: str, name: str, download: bool) -> None:
        job = self.server.service.finished_report(owner, name)
        if job is None or job.report is None:
            # Not built yet in this session: send them home with the link filled in.
            self._send(HTTPStatus.SEE_OTHER, b"", "text/plain", {"Location": f"/?repo={owner}/{name}"})
            return
        repo = job.repo
        source = {"label": f"github.com/{repo.slug}", "url": repo.web_url}
        if download:
            document = render_report(job.report, source=source)
            filename = f"{repo.name}-gitstory.html".replace('"', "")
            self._html(HTTPStatus.OK, document, {"Content-Disposition": f'attachment; filename="{filename}"'})
            return
        links = [{"label": "← New story", "href": "/"}]
        document = render_report(job.report, source=source, links=links, download=f"{job.report_path}/download")
        self._html(HTTPStatus.OK, document)


def _not_found_page() -> str:
    return ('<!DOCTYPE html><meta charset="utf-8"><title>Not found · gitstory</title>'
            '<body style="font-family:system-ui;background:#0a1020;color:#eef1fa;padding:3rem">'
            '<p>Nothing here. <a href="/" style="color:#ff8f3d">Back to gitstory</a></p>')


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def make_server(host: str, port: int, service: StoryService, public: bool = False) -> StoryServer:
    return StoryServer((host, port), service, public=public)


def bind_server(host: str, port: int, service: StoryService, public: bool = False) -> Tuple[StoryServer, Optional[str]]:
    """Start listening, moving to a free port if the chosen one is busy.

    Returns the server and, when it had to move, a note explaining why.
    """
    try:
        return make_server(host, port, service, public), None
    except OSError as error:
        if port == 0 or public:   # a hosting platform tells us which port to use; never wander off it
            raise
        server = make_server(host, 0, service, public)
        note = (
            f"Port {port} is already in use (probably an older gitstory that is still "
            f"running; close that window to stop it), so this one uses port "
            f"{server.server_address[1]}."
        )
        return server, note


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False, public: bool = False) -> int:
    """Run the web mode until Ctrl+C (or, on a hosting platform, until stopped).

    ``public`` is for running gitstory as a website for everyone: it accepts
    any host name, logs each story, and applies ``Limits.public()``.
    """
    limits = Limits.public() if public else Limits()
    log = (lambda message: print(message, flush=True)) if public else None
    with tempfile.TemporaryDirectory(prefix="gitstory-") as workdir:
        service = StoryService(Path(workdir), limits=limits, log=log, max_concurrent=limits.workers)
        try:
            server, note = bind_server(host, port, service, public)
        except OSError as error:
            raise GitStoryError(
                f"could not listen on {host}:{port} ({error.strerror or error}); "
                "is something else using that port? Try --port 0 to pick a free one."
            ) from error
        if public:
            # Hosting platforms stop a service with SIGTERM; finish cleanly.
            import signal

            def stop(*_: Any) -> None:
                threading.Thread(target=server.shutdown, daemon=True).start()

            signal.signal(signal.SIGTERM, stop)
            print(f"gitstory is serving the public website on {host}:{server.server_address[1]} "
                  f"(repositories up to {limits.max_repo_mb} MB, {limits.max_stories} stories kept)", flush=True)
        else:
            shown_host = "localhost" if host in ("127.0.0.1", "0.0.0.0", "::", "") else host
            url = f"http://{shown_host}:{server.server_address[1]}/"
            if note:
                print(note)
            print(f"gitstory is running at {url}")
            print("Paste a GitHub link there to see its story. Press Ctrl+C to stop.")
            if open_browser:
                webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            server.server_close()
    return 0
