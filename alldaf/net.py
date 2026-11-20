"""Talking to alldaf.org and GitHub: searches, update check, and the self-updater."""
import hashlib
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.parse, urllib.request
from pathlib import Path
from .config import API_MSG, HEADERS, REPO, SEARCH_API, VERSION, shared
from .util import parse_version


class ApiChanged(Exception):
    """The site's reply did not look the way this program expects."""


def make_ctx(skip_check):
    """None = normal checking. Skipping checks is only for networks whose proxy breaks certificate checks."""
    if not skip_check:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def parse_authors(data):
    """Validate the site's search reply and return [{"id", "name"}, ...] (empty list = no match)."""
    if not isinstance(data, dict):
        raise ApiChanged(API_MSG)
    authors = data.get("authors") or []
    if not isinstance(authors, list) or any(
            not isinstance(a, dict) or not isinstance(a.get("id"), int) or not isinstance(a.get("name"), str)
            for a in authors):
        raise ApiChanged(API_MSG)
    return [{"id": a["id"], "name": a["name"].strip()} for a in authors]


def search_authors(query, ctx):
    """Look a speaker up by name on alldaf.org (the same search the site's search box uses)."""
    inp = {"0": {"query": query, "size": 10, "platform": "AllDaf"}}
    url = SEARCH_API + "?batch=1&input=" + urllib.parse.quote(json.dumps(inp, separators=(",", ":")), safe="")
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20, context=ctx) as r:
        body = r.read()
    try:
        data = json.loads(body)[0]["result"]["data"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise ApiChanged(API_MSG)
    return parse_authors(data)


def check_for_update(skip_ssl):
    """Return a dict with tag, page, exe_url, sha_url if the latest GitHub release is newer than VERSION."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "AllDaf-Downloader",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10, context=make_ctx(skip_ssl)) as r:
        data = json.load(r)

    tag = data.get("tag_name", "")
    if not tag or parse_version(tag) <= parse_version(VERSION):
        return None
    assets = data.get("assets", [])

    def find(suffix):
        return next((a.get("browser_download_url") for a in assets
                     if a.get("name", "").lower().endswith(suffix)), None)

    return {"tag": tag, "page": data.get("html_url", f"https://github.com/{REPO}/releases"),
            "exe_url": find(".exe"), "sha_url": find(".sha256")}


def download_update(exe_url, sha_url):
    """Download the new .exe next to the running one, check it against the release's SHA-256 file,
    then swap the files. Certificates are always checked here: this file gets run, so it must be authentic."""
    current = Path(sys.executable)
    new = current.with_name(current.stem + ".new.exe")
    old = current.with_name(current.stem + ".old.exe")
    with urllib.request.urlopen(urllib.request.Request(sha_url, headers=HEADERS), timeout=30) as r:
        m = re.search(r"\b[0-9a-fA-F]{64}\b", r.read(4096).decode("ascii", "replace"))
    if not m:
        raise IOError("the release's checksum file is not readable")
    want = m.group(0).lower()
    digest = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(exe_url, headers=HEADERS), timeout=60) as r, \
            open(new, "wb") as out:
        size, got = int(r.headers.get("Content-Length") or 0), 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            got += len(chunk)
    if (size and got != size) or digest.hexdigest() != want:
        new.unlink()
        raise IOError("the downloaded update did not match its checksum, so it was discarded")
    # Windows lets a running .exe be renamed but not overwritten, so move the old one aside first
    try:
        old.unlink()
    except OSError:
        pass
    os.replace(current, old)
    try:
        os.replace(new, current)
    except Exception:
        os.replace(old, current)  # put the old version back if the swap fails
        raise
    return current


def cleanup_old_exe():
    """Remove the previous version left behind by an update. The old copy stays locked until it finishes
    closing, so keep retrying in the background for a minute."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        old = exe.with_name(exe.stem + ".old.exe")

        def try_delete():
            for _ in range(30):
                try:
                    old.unlink()
                    return
                except FileNotFoundError:
                    return
                except OSError:
                    time.sleep(2)

        threading.Thread(target=try_delete, daemon=True).start()


def estimate_bytes(url):
    """Size of one file, from a HEAD request (no download)."""
    req = urllib.request.Request(url, method="HEAD", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15, context=shared.ssl_ctx) as r:
        return int(r.headers.get("Content-Length") or 0)
