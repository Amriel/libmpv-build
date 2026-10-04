#!/usr/bin/env python3
"""Small helper around pins.json (stdlib only).

  pins_info.py get <dotted.path>              print a value, e.g. build_host.arch_archive_snapshot
  pins_info.py rev <source-name>              print the pinned commit of a source
  pins_info.py cache-key <variant>            key for the toolchain cache (changes only when the
                                              toolchain inputs change, NOT when a library pin moves)
  pins_info.py check-workflow <workflow.yml>  fail unless the container digest and action SHAs
                                              written in the workflow match pins.json
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = json.loads((ROOT / "pins.json").read_text(encoding="utf-8"))


def dotted(d, path):
    for part in path.split("."):
        d = d[part]
    return d


def src(name):
    for s in PINS["sources"]:
        if s["name"] == name:
            return s
    raise SystemExit(f"no source named {name}")


def main():
    cmd = sys.argv[1]
    if cmd == "get":
        print(dotted(PINS, sys.argv[2]))
    elif cmd == "rev":
        print(src(sys.argv[2])["rev"])
    elif cmd == "cache-key":
        variant = sys.argv[2]
        h = hashlib.sha256()
        for part in (
            PINS["upstream_recipe"]["rev"],
            src("llvm")["rev"],
            src("mingw-w64")["rev"],
            PINS["build_host"]["container_digest"],
            PINS["build_host"]["arch_archive_snapshot"],
            variant,
        ):
            h.update(part.encode() + b"\0")
        for f in ("tools/apply_pins.py", "tools/build.sh", "tools/setup_host.sh"):
            h.update((ROOT / f).read_bytes())
        print(f"toolchain-{variant}-{h.hexdigest()[:20]}")
    elif cmd == "check-workflow":
        wf = Path(sys.argv[2]).read_text(encoding="utf-8")
        missing = []
        if PINS["build_host"]["container_digest"] not in wf:
            missing.append("container digest")
        import re
        for name, a in PINS["actions"].items():
            # actions/cache is used as actions/cache/restore and actions/cache/save
            if not re.search(re.escape(name) + r"(/[a-z]+)?@" + a["sha"], wf):
                missing.append(f"{name}@{a['sha']}")
        # no third-party / floating action references at all
        for m in re.finditer(r"^\s*-?\s*uses:\s*(\S+)", wf, re.M):
            ref = m.group(1)
            if not re.search(r"@[0-9a-f]{40}\b", ref):
                missing.append(f"action not pinned to a commit SHA: {ref}")
        if missing:
            raise SystemExit("workflow/pins.json mismatch:\n  - " + "\n  - ".join(missing))
        print("workflow pins OK")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
