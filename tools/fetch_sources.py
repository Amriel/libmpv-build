#!/usr/bin/env python3
"""Fetch every git source listed in pins.json at its EXACT pinned commit into <srcdir>/<name>.

Why we do this ourselves instead of letting CMake's ExternalProject clone:
  * `git fetch --depth 1 origin <sha>` gives exactly that commit, nothing else moves;
  * the upstream recipe's `check-git` step sees <srcdir>/<name>/.git and skips its own
    clone/update, so these checkouts are what gets built;
  * we verify `git rev-parse HEAD == rev` for every package and abort otherwise.

Tarball sources (kind=url) are downloaded and sha256-verified by CMake (URL_HASH), nothing to
do here except create the download dir.

Usage: fetch_sources.py <pins.json> <srcdir> [name ...]
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def run(cmd, cwd=None, check=True):
    print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=check)


def out(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True).stdout.strip()


def head_of(d: Path) -> str:
    if not (d / ".git").exists():
        return ""
    return out(["git", "rev-parse", "HEAD"], cwd=d)


def fetch_one(pin: dict, dest: Path):
    rev, url, depth, sparse = pin["rev"], pin["url"], pin.get("depth", 1), pin.get("sparse")
    if head_of(dest) == rev:
        print(f"[{pin['name']}] already at {rev[:10]}", flush=True)
        return
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    if depth == 0:
        # full (blobless) history so that `git describe` works for ffmpeg / mpv version strings
        run(["git", "clone", "--filter=blob:none", "--no-checkout", url, str(dest)])
        if sparse:
            run(["git", "sparse-checkout", "set", "--no-cone", *sparse], cwd=dest)
        run(["git", "-c", "advice.detachedHead=false", "checkout", "--detach", rev], cwd=dest)
    else:
        run(["git", "init", "-q"], cwd=dest)
        run(["git", "remote", "add", "origin", url], cwd=dest)
        run(["git", "config", "remote.origin.promisor", "true"], cwd=dest)
        run(["git", "config", "remote.origin.partialclonefilter", "blob:none"], cwd=dest)
        if sparse:
            run(["git", "sparse-checkout", "set", "--no-cone", *sparse], cwd=dest)
        run(["git", "fetch", "--depth", "1", "--filter=blob:none", "origin", rev], cwd=dest)
        run(["git", "-c", "advice.detachedHead=false", "checkout", "--detach", "FETCH_HEAD"], cwd=dest)

    got = head_of(dest)
    if got != rev:
        raise SystemExit(f"[{pin['name']}] checked out {got}, pinned {rev}")
    print(f"[{pin['name']}] OK {rev}", flush=True)


def main():
    pins = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    srcdir = Path(sys.argv[2]).resolve()
    only = set(sys.argv[3:])
    srcdir.mkdir(parents=True, exist_ok=True)
    failures = []
    for pin in pins["sources"]:
        if only and pin["name"] not in only:
            continue
        dest = srcdir / pin["name"]
        if pin["kind"] == "url":
            dest.mkdir(parents=True, exist_ok=True)  # DOWNLOAD_DIR of the tarball
            continue
        for attempt in range(1, 4):
            try:
                fetch_one(pin, dest)
                break
            except (subprocess.CalledProcessError, SystemExit) as e:
                print(f"[{pin['name']}] attempt {attempt} failed: {e}", flush=True)
                if attempt == 3:
                    failures.append(pin["name"])
                else:
                    time.sleep(10 * attempt)
    if failures:
        raise SystemExit("fetch failed for: " + ", ".join(failures))


if __name__ == "__main__":
    main()
