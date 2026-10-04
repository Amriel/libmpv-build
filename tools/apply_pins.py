#!/usr/bin/env python3
"""Turn a checkout of shinchiro/mpv-winbuild-cmake (at the pinned commit) into OUR recipe.

  1. verifies the upstream checkout is exactly pins.json -> upstream_recipe.rev
  2. verifies that every upstream file we replace / edit still has the sha256 we reviewed
  3. copies overlay/ over the upstream tree
  4. applies a few exact-match text edits to upstream toolchain files (each must match exactly once)
  5. rewrites every package file so that GIT_TAG == the pinned 40-hex commit (and removes
     GIT_REMOTE_NAME / GIT_RESET / branch-name GIT_TAG), or checks URL + URL_HASH for tarballs
  6. FAILS if any package that will be built has no pin, an unpinned GIT_TAG, a git source without
     GIT_TAG, or contains a hidden network fetch (curl/wget/git clone/cargo/rustup)

Usage: apply_pins.py --upstream <dir> --repo <dir with pins.json + overlay/>
Only the Python standard library is used.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HEX40 = re.compile(r"^[0-9a-f]{40}$")

# name -> path (relative to the upstream tree) of the cmake file holding its ExternalProject_Add
TOOLCHAIN_FILES = {
    "llvm": "toolchain/llvm/llvm.cmake",
    "mingw-w64": "toolchain/mingw-w64.cmake",
}


def fail(msg):
    print(f"apply_pins: ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pkg_file(name: str) -> str:
    return TOOLCHAIN_FILES.get(name, f"packages/{name}.cmake")


# --------------------------------------------------------------------------------------------
# 4. text edits on upstream files (exact string must be present exactly `count` times)
# --------------------------------------------------------------------------------------------
def remove_lines_in_list(text: str, stripped_entries: set, relname: str) -> str:
    out, found = [], set()
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if s in stripped_entries:
            found.add(s)
            continue
        out.append(line)
    missing = stripped_entries - found
    if missing:
        fail(f"{relname}: expected list entries not found: {sorted(missing)}")
    return "".join(out)


def replace_exact(text: str, old: str, new: str, relname: str, count: int = 1) -> str:
    n = text.count(old)
    if n != count:
        fail(f"{relname}: expected {count} occurrence(s) of {old!r}, found {n}")
    return text.replace(old, new)


def apply_text_edits(up: Path):
    # toolchain/CMakeLists.txt: we are clang-only, local-only. Drop gcc toolchain, rust, widl,
    # openmp and cppwinrt (cppwinrt is only for mpv's SMTC media-key support, which is disabled,
    # and it downloads Windows.winmd from a mutable windows-rs `master` URL).
    p = up / "toolchain/CMakeLists.txt"
    t = p.read_text(encoding="utf-8")
    t = remove_lines_in_list(
        t,
        {"gcc-binutils", "${gcc_wrapper}", "cppwinrt", "gcc", "widl", "rustup", "llvm-openmp"},
        "toolchain/CMakeLists.txt",
    )
    p.write_text(t, encoding="utf-8", newline="\n")

    p = up / "toolchain/llvm/llvm-clang.cmake"
    t = p.read_text(encoding="utf-8")
    t = remove_lines_in_list(t, {"cppwinrt"}, "toolchain/llvm/llvm-clang.cmake")
    p.write_text(t, encoding="utf-8", newline="\n")

    # LLVM: only the X86 backend is needed (cross-compiling to x86_64-windows from x86_64-linux).
    # NVPTX was only for ffmpeg --enable-cuda-llvm, AArch64 only for the aarch64 target.
    p = up / "toolchain/llvm/llvm.cmake"
    t = p.read_text(encoding="utf-8")
    # LLVM_PARALLEL_LINK_JOBS=2: GitHub-hosted runners have 7-16 GB RAM; the default (one link job
    # per core) can OOM while linking clang/lld.
    t = replace_exact(
        t,
        "-DLLVM_TARGETS_TO_BUILD='AArch64,X86,NVPTX'",
        "-DLLVM_TARGETS_TO_BUILD='X86'\n        -DLLVM_PARALLEL_LINK_JOBS=2",
        "toolchain/llvm/llvm.cmake",
    )
    p.write_text(t, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------------------------
# 5. pin rewriting
# --------------------------------------------------------------------------------------------
def find_block(text: str, name: str, relname: str):
    """Return (start, end) character offsets of ExternalProject_Add(<name> ... ) block."""
    m = re.search(r"^ExternalProject_Add\(\s*" + re.escape(name) + r"\b", text, re.M)
    if not m:
        fail(f"{relname}: no ExternalProject_Add({name}")
    start = m.start()
    # block ends at the first line that is exactly ")" after start
    m2 = re.compile(r"^\)\s*$", re.M).search(text, m.end())
    if not m2:
        fail(f"{relname}: unterminated ExternalProject_Add({name}")
    return start, m2.end()


def pin_git(block: str, pin: dict, relname: str) -> str:
    lines = block.splitlines(keepends=True)
    out, repo_idx = [], None
    for line in lines:
        s = line.strip()
        if re.match(r"^(GIT_REMOTE_NAME|GIT_TAG|GIT_RESET)\b", s):
            continue  # dropped; re-added below as a single GIT_TAG <sha>
        if re.match(r"^GIT_REPOSITORY\b", s):
            if repo_idx is not None:
                fail(f"{relname}: two GIT_REPOSITORY lines in one block")
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}GIT_REPOSITORY {pin['url']}\n")
            out.append(f"{indent}GIT_TAG {pin['rev']}\n")
            repo_idx = len(out)
            continue
        out.append(line)
    if repo_idx is None:
        fail(f"{relname}: package {pin['name']} is pinned as git but has no GIT_REPOSITORY")
    return "".join(out)


def pin_url(block: str, pin: dict, relname: str) -> str:
    """Rewrite URL / URL_HASH of a tarball package to the pinned values (pins.json is the truth)."""
    if not re.search(r"^\s*URL\s+\S+", block, re.M) or not re.search(r"^\s*URL_HASH\s+SHA256=[0-9A-Fa-f]{64}", block, re.M):
        fail(f"{relname}: package {pin['name']} is pinned as url but has no URL / URL_HASH SHA256=")
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", pin["sha256"]):
        fail(f"pins.json: {pin['name']}.sha256 is not 64 hex chars")
    block = re.sub(r"^(\s*URL\s+)\S+", lambda m: m.group(1) + pin["url"], block, count=1, flags=re.M)
    block = re.sub(r"^(\s*URL_HASH\s+SHA256=)[0-9A-Fa-f]{64}", lambda m: m.group(1) + pin["sha256"], block, count=1, flags=re.M)
    return block


def apply_pins_to_packages(up: Path, pins: dict):
    by_name = {p["name"]: p for p in pins["sources"]}
    wanted = list(pins["package_order"]) + [n for n, p in by_name.items() if p["role"] == "toolchain"]
    for name in wanted:
        if name not in by_name:
            fail(f"package {name!r} is built but has NO entry in pins.json")
    for name in wanted:
        pin = {**by_name[name]}
        rel = pkg_file(name)
        path = up / rel
        if not path.exists():
            fail(f"{rel} does not exist in the upstream checkout")
        text = path.read_text(encoding="utf-8")
        start, end = find_block(text, name, rel)
        block = text[start:end]
        if pin["kind"] == "git":
            if not HEX40.match(pin["rev"]):
                fail(f"pins.json: {name}.rev is not a full 40-hex commit: {pin['rev']!r}")
            new_block = pin_git(block, pin, rel)
            path.write_text(text[:start] + new_block + text[end:], encoding="utf-8", newline="\n")
        elif pin["kind"] == "url":
            new_block = pin_url(block, pin, rel)
            path.write_text(text[:start] + new_block + text[end:], encoding="utf-8", newline="\n")
        else:
            fail(f"pins.json: {name}: unknown kind {pin['kind']!r}")
    return wanted


# --------------------------------------------------------------------------------------------
# 6. guards on the final tree
# --------------------------------------------------------------------------------------------
BAD_FETCH = re.compile(r"\b(wget|curl|git\s+clone|cargo|rustup|svn\s|hg\s)\b")


def guard(up: Path, pins: dict, wanted):
    problems = []
    # package list in the overlay must equal pins.package_order
    cm = (up / "packages/CMakeLists.txt").read_text(encoding="utf-8")
    m = re.search(r"list\(APPEND ep\s+(.*?)\n\)", cm, re.S)
    if not m:
        fail("cannot parse 'list(APPEND ep ...)' in packages/CMakeLists.txt")
    ep = [x for x in m.group(1).split() if x]
    if ep != pins["package_order"]:
        problems.append(f"packages/CMakeLists.txt ep list {ep} != pins.json package_order {pins['package_order']}")

    for name in wanted:
        rel = pkg_file(name)
        text = (up / rel).read_text(encoding="utf-8")
        # strip comments for the checks
        code = "\n".join(re.sub(r"#.*$", "", l) for l in text.splitlines())
        for m in re.finditer(r"^\s*GIT_TAG\s+(\S+)", code, re.M):
            if not HEX40.match(m.group(1)):
                problems.append(f"{rel}: unpinned GIT_TAG {m.group(1)}")
        if re.search(r"^\s*GIT_REPOSITORY\b", code, re.M) and not re.search(r"^\s*GIT_TAG\s+[0-9a-f]{40}\b", code, re.M):
            problems.append(f"{rel}: GIT_REPOSITORY without a pinned GIT_TAG")
        if re.search(r"^\s*(GIT_REMOTE_NAME|GIT_RESET)\b", code, re.M):
            problems.append(f"{rel}: GIT_REMOTE_NAME/GIT_RESET still present")
        if re.search(r"^\s*GIT_SHALLOW\b", code, re.M):
            problems.append(f"{rel}: GIT_SHALLOW present (not allowed with pinned hashes)")
        for m in BAD_FETCH.finditer(code):
            problems.append(f"{rel}: hidden network fetch / tool use: {m.group(0)!r}")

    # toolchain/CMakeLists.txt must not list anything we dropped
    tc = (up / "toolchain/CMakeLists.txt").read_text(encoding="utf-8")
    for bad in ("gcc", "gcc-binutils", "cppwinrt", "widl", "rustup", "llvm-openmp"):
        if re.search(r"^\s+" + re.escape(bad) + r"\s*$", tc, re.M):
            problems.append(f"toolchain/CMakeLists.txt still lists {bad}")

    if problems:
        print("apply_pins: guard FAILED:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True, type=Path)
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--skip-head-check", action="store_true",
                    help="test only: do not require the upstream dir to be a git checkout at the pinned commit")
    a = ap.parse_args()
    up, repo = a.upstream.resolve(), a.repo.resolve()
    pins = json.loads((repo / "pins.json").read_text(encoding="utf-8"))

    # 1. upstream commit
    if not a.skip_head_check:
        head = subprocess.run(["git", "-C", str(up), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        want = pins["upstream_recipe"]["rev"]
        if head != want:
            fail(f"upstream checkout is {head}, pins.json wants {want}")

    # 2. reviewed upstream files unchanged
    expected = {k: v for k, v in pins["upstream_files_expected_sha256"].items() if not k.startswith("_")}
    for rel, h in expected.items():
        p = up / rel
        if not p.exists():
            fail(f"expected upstream file missing: {rel}")
        got = sha256_file(p)
        if got != h:
            fail(f"upstream file {rel} changed: sha256 {got} != reviewed {h}. Re-review the overlay, then update pins.json.")

    # 3. overlay
    ov = repo / "overlay"
    n = 0
    for src in sorted(ov.rglob("*")):
        if src.is_file():
            rel = src.relative_to(ov).as_posix()
            if rel not in expected:
                fail(f"overlay file {rel} is not listed in pins.json upstream_files_expected_sha256 "
                     f"(overlay may only REPLACE reviewed upstream files)")
            dst = up / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            n += 1
    print(f"apply_pins: copied {n} overlay files")

    # 4. text edits
    apply_text_edits(up)

    # 5. pins
    wanted = apply_pins_to_packages(up, pins)
    print(f"apply_pins: pinned {len(wanted)} packages: {', '.join(wanted)}")

    # 6. guards
    guard(up, pins, wanted)
    print("apply_pins: OK")


if __name__ == "__main__":
    main()
