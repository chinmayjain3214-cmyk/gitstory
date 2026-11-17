"""Tests for the web mode. A fake clone step copies a local repository, so no network is used."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

import pytest

from gitstory.github import CloneError, GitHubRepo, clone_repository
from gitstory.render import render_home
from gitstory.server import StoryService, bind_server, make_server

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _origin(path: Path) -> Path:
    env = dict(os.environ, GIT_AUTHOR_NAME="Grace Hopper", GIT_AUTHOR_EMAIL="grace@example.com",
               GIT_COMMITTER_NAME="Grace Hopper", GIT_COMMITTER_EMAIL="grace@example.com",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    path.mkdir()
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True, env=env)
    for i, message in enumerate(["feat: start", "fix: </script> in message", "docs: readme"]):
        (path / f"file{i}.py").write_text("x = 1\n" * (i + 2), encoding="utf-8")
        subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", message], check=True, env=env)
    return path


@pytest.fixture()
def site(tmp_path: Path) -> Iterator[Tuple[str, Dict[str, Any]]]:
    origin = _origin(tmp_path / "origin")
    calls: Dict[str, Any] = {"clones": 0}

    def fake_clone(repo: GitHubRepo, destination: Path, on_progress=None) -> Path:
        calls["clones"] += 1
        if repo.name == "missing":
            raise CloneError(f"{repo.slug} was not found on GitHub.")
        if on_progress:
            on_progress("Receiving", 50, "1.00 MiB")
        return clone_repository(repo, destination, on_progress=on_progress, url=str(origin))

    work = tmp_path / "work"
    work.mkdir()
    server = make_server("127.0.0.1", 0, StoryService(work, clone=fake_clone))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", calls
    finally:
        server.shutdown()
        server.server_close()


def request(url: str, body: Optional[dict] = None, headers: Optional[dict] = None,
            content_type: str = "application/json") -> Tuple[int, Dict[str, str], bytes]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=dict(headers or {}))
    if data is not None:
        req.add_header("Content-Type", content_type)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):  # type: ignore[override]
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=20) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def wait_for(base: str, job_id: str, timeout: float = 30) -> Dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = json.loads(request(f"{base}/api/stories/{job_id}")[2])
        if job["state"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_home_page_is_self_contained():
    document = render_home(examples=["psf/requests"])
    assert document.startswith("<!DOCTYPE html>")
    assert "GitHub repository link" in document and "What's in a story" in document
    assert "{{" not in document.split('<script id="gitstory-data"')[0]
    assert "<link" not in document and "src=\"http" not in document


@needs_git
def test_home_and_resolve(site):
    base, _ = site
    status, headers, body = request(base + "/")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert b"GitHub repository link" in body

    status, _, body = request(base + "/api/resolve", {"url": "https://github.com/octocat/Hello-World/tree/main"})
    assert status == 200
    assert json.loads(body) == {"slug": "octocat/Hello-World", "owner": "octocat", "name": "Hello-World",
                                "url": "https://github.com/octocat/Hello-World"}

    status, _, body = request(base + "/api/resolve", {"url": "https://gitlab.com/a/b"})
    assert status == 400 and "GitHub repository link" in json.loads(body)["error"]


@needs_git
def test_full_story_flow(site):
    base, calls = site
    status, _, body = request(base + "/api/stories", {"url": "github.com/grace/compiler"})
    assert status == 202
    job = wait_for(base, json.loads(body)["id"])
    assert job["state"] == "done", job
    assert job["report_url"] == "/story/grace/compiler"
    assert job["summary"] == {"commits": 3, "contributors": 1}

    status, _, page = request(base + job["report_url"])
    assert status == 200
    text = page.decode()
    assert "github.com/grace/compiler" in text
    assert '"download":"/story/grace/compiler/download"' in text
    assert "New story" in text
    assert text.count("</script>") == 2  # the commit message containing </script> stayed escaped

    status, headers, download = request(base + job["report_url"] + "/download")
    assert status == 200
    assert headers["Content-Disposition"] == 'attachment; filename="compiler-gitstory.html"'
    offline = download.decode()
    assert '"download":null' in offline and '"links":[]' in offline  # nothing points back at the server
    assert "<script src" not in offline and "<link" not in offline  # everything is inline

    # Asking again reuses the finished story instead of cloning twice.
    again = json.loads(request(base + "/api/stories", {"url": "grace/compiler"})[2])
    assert again["state"] == "done" and calls["clones"] == 1


@needs_git
def test_failed_clone_is_reported(site):
    base, _ = site
    job = wait_for(base, json.loads(request(base + "/api/stories", {"url": "grace/missing"})[2])["id"])
    assert job["state"] == "error"
    assert job["error"] == "grace/missing was not found on GitHub."


@needs_git
def test_unknown_story_redirects_home_with_the_link_filled_in(site):
    base, _ = site
    status, headers, _ = request(base + "/story/someone/thing")
    assert status == 303 and headers["Location"] == "/?repo=someone/thing"
    assert request(base + "/api/stories/nope")[0] == 404
    assert request(base + "/no/such/page")[0] == 404


@needs_git
def test_requests_from_other_sites_are_refused(site):
    base, _ = site
    # A plain HTML form cannot send JSON, so it gets 415.
    assert request(base + "/api/stories", {"url": "a/b"}, content_type="text/plain")[0] == 415
    # A page reached through DNS rebinding has a foreign Host header.
    assert request(base + "/", headers={"Host": "evil.example:8765"})[0] == 403
    assert request(base + "/", headers={"Host": "localhost:8765"})[0] == 200


def test_busy_port_moves_to_a_free_one(tmp_path):
    first = make_server("127.0.0.1", 0, StoryService(tmp_path / "a"))
    busy = first.server_address[1]
    try:
        second, note = bind_server("127.0.0.1", busy, StoryService(tmp_path / "b"))
        try:
            assert second.server_address[1] != busy
            assert note and str(busy) in note
        finally:
            second.server_close()
    finally:
        first.server_close()


def test_free_port_is_used_as_asked(tmp_path):
    server, note = bind_server("127.0.0.1", 0, StoryService(tmp_path))
    try:
        assert note is None
    finally:
        server.server_close()
