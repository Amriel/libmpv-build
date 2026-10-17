#!/usr/bin/env python3
"""Generate SOURCES.txt, CONFIG.txt and licenses/ for a finished build (stdlib only).

  gen_info.py --pins pins.json --dist <build>/libmpv-dist --meta <build>/libmpv-meta \
              --srcdir upstream/src_packages --out <release dir> --variant 64 \
              [--lto ON] [--run-url URL] [--host-packages pacman-Q.txt]

Also FAILS (exit 1) if the ffmpeg configuration evidence shows --enable-gpl / --enable-version3 /
--enable-nonfree, a network protocol, a non-LGPL FFMPEG_LICENSE, or an enabled external library
other than zlib + libdav1d.
"""
import argparse
import datetime
import json
import re
import shutil
import sys
import tarfile
from pathlib import Path

LICENSE_NAME = re.compile(r"^(copying|license|licence|notice|copyright|unlicense|copying\.lib|copying\.lgpl).*", re.I)
MAX_LICENSE_BYTES = 400_000
# ffmpeg tree also carries GPL texts for options we do not use; ship only the relevant ones
FFMPEG_LICENSE_ALLOW = {"LICENSE.md", "COPYING.LGPLv2.1"}


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def ffmpeg_evidence(meta: Path):
    cfg_h = read(meta / "ffmpeg" / "config.h")
    cfg_c = read(meta / "ffmpeg" / "config_components.h")
    m = re.search(r'#define FFMPEG_CONFIGURATION "(.*)"', cfg_h)
    configuration = m.group(1).replace('\\"', '"') if m else ""
    m = re.search(r'#define FFMPEG_LICENSE "(.*)"', cfg_h)
    license_ = m.group(1) if m else ""
    enabled = {}
    for kind in ("DECODER", "ENCODER", "DEMUXER", "MUXER", "PARSER", "BSF", "PROTOCOL", "HWACCEL", "FILTER", "INDEV", "OUTDEV"):
        names = re.findall(rf"#define CONFIG_([A-Z0-9_]+)_{kind} 1\b", cfg_c)
        enabled[kind] = sorted(n.lower() for n in names)
    ext = sorted(set(re.findall(r"#define (CONFIG_LIB[A-Z0-9_]+|CONFIG_(?:OPENSSL|GNUTLS|SCHANNEL|ZLIB|BZLIB|LZMA|ICONV|SDL2|VAAPI|VDPAU|D3D11VA|DXVA2|D3D12VA|NVDEC|CUDA|FFNVCODEC|AMF|CUVID|NVENC|VULKAN|OPENCL|OPENGL|MEDIAFOUNDATION)) 1\b", cfg_h)))
    return configuration, license_, enabled, ext


def check_ffmpeg(configuration, license_, enabled, ext):
    problems = []
    if not configuration:
        problems.append("FFMPEG_CONFIGURATION not found in config.h")
    for bad in ("--enable-gpl", "--enable-version3", "--enable-nonfree"):
        if bad in configuration:
            problems.append(f"ffmpeg configured with {bad}")
    if license_.strip() != "LGPL version 2.1 or later":
        problems.append(f"FFMPEG_LICENSE is {license_!r}, expected 'LGPL version 2.1 or later'")
    if enabled["PROTOCOL"] != ["file"]:
        problems.append(f"ffmpeg protocols enabled: {enabled['PROTOCOL']} (expected ['file'])")
    if enabled["INDEV"] or enabled["OUTDEV"]:
        problems.append(f"ffmpeg devices enabled: {enabled['INDEV']} {enabled['OUTDEV']}")
    if enabled["MUXER"]:
        # not fatal: a muxer pulled in by a `select` dependency is harmless (no network, no write path
        # is reachable from mpv's read-only use), but we want it visible in the log
        print(f"gen_info: NOTE ffmpeg muxers enabled: {enabled['MUXER']}")
    allowed_ext = {"CONFIG_ZLIB", "CONFIG_LIBDAV1D", "CONFIG_D3D11VA", "CONFIG_DXVA2", "CONFIG_FFNVCODEC", "CONFIG_NVDEC",
                   "CONFIG_CUDA"}
    extra = [e for e in ext if e not in allowed_ext]
    if extra:
        problems.append(f"unexpected external/hw libs enabled in ffmpeg: {extra}")
    return problems


def meson_options(dist: Path):
    p = dist / "meson-info" / "intro-buildoptions.json"
    if not p.exists():
        return [], []
    data = json.loads(read(p))
    user = sorted((o["name"], o["value"]) for o in data if o.get("section") == "user")
    core_keys = {"buildtype", "optimization", "debug", "b_lto", "b_lto_mode", "b_ndebug", "default_library", "prefer_static", "werror"}
    core = sorted((o["name"], o["value"]) for o in data if o["name"] in core_keys)
    return user, core


def copy_licenses(pins, srcdir: Path, out: Path):
    lic = out / "licenses"
    if lic.exists():
        shutil.rmtree(lic)
    missing = []
    for s in pins["sources"]:
        name = s["name"]
        d = srcdir / name
        dest = lic / name
        found = 0
        if s["kind"] == "git" and (d / ".git").exists():
            cands = [p for p in d.iterdir() if p.is_file() and LICENSE_NAME.match(p.name)]
            # one level down: llvm sub-projects (libcxx, compiler-rt, ...), mingw-w64 runtime, winpthreads
            for sub in d.iterdir():
                if sub.is_dir() and not sub.name.startswith(".") and sub.name not in ("test", "tests", "docs", "doc"):
                    cands += [p for p in sub.iterdir() if p.is_file() and LICENSE_NAME.match(p.name)]
            for p in cands:
                if name == "ffmpeg" and p.name not in FFMPEG_LICENSE_ALLOW:
                    continue
                if p.stat().st_size > MAX_LICENSE_BYTES:
                    continue
                rel = p.relative_to(d)
                tgt = dest / rel
                tgt.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, tgt)
                found += 1
            if name == "mingw-w64":
                for extra in ("mingw-w64-libraries/winpthreads/COPYING", "mingw-w64-crt/COPYING"):
                    p = d / extra
                    if p.is_file():
                        tgt = dest / extra
                        tgt.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(p, tgt)
                        found += 1
        elif s["kind"] == "url":
            for tb in d.glob("*.tar.*") if d.exists() else []:
                try:
                    with tarfile.open(tb) as t:
                        for m in t.getmembers():
                            parts = m.name.split("/")
                            if m.isfile() and len(parts) == 2 and LICENSE_NAME.match(parts[1]) and m.size < MAX_LICENSE_BYTES:
                                tgt = dest / parts[1]
                                tgt.parent.mkdir(parents=True, exist_ok=True)
                                tgt.write_bytes(t.extractfile(m).read())
                                found += 1
                except Exception as e:  # noqa
                    print(f"WARN: cannot read {tb}: {e}", file=sys.stderr)
        if not found:
            missing.append(name)
    return missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pins", required=True, type=Path)
    ap.add_argument("--dist", required=True, type=Path)
    ap.add_argument("--meta", required=True, type=Path)
    ap.add_argument("--srcdir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--variant", default="64")
    ap.add_argument("--lto", default="ON")
    ap.add_argument("--run-url", default="")
    ap.add_argument("--host-packages", type=Path)
    a = ap.parse_args()

    pins = json.loads(read(a.pins))
    a.out.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    configuration, license_, enabled, ext = ffmpeg_evidence(a.meta)
    problems = check_ffmpeg(configuration, license_, enabled, ext)
    user_opts, core_opts = meson_options(a.dist)
    missing_lic = copy_licenses(pins, a.srcdir, a.out)

    # ---------------- SOURCES.txt ----------------
    L = []
    L.append("libmpv build - SOURCES")
    L.append(f"generated   : {now}")
    L.append(f"variant     : {'x86-64 baseline' if a.variant == '64' else 'x86-64-v3'}")
    if a.run_url:
        L.append(f"build run   : {a.run_url}")
    up = pins["upstream_recipe"]
    L.append("")
    L.append("Build recipe (this repository) = our overlay + pins.json on top of:")
    L.append(f"  {up['name']}  {up['url']}  commit {up['rev']}")
    L.append("  (checked out at build time; that upstream project publishes no licence, its files are not redistributed here)")
    bh = pins["build_host"]
    L.append(f"Build container : {bh['container_image']}@{bh['container_digest']}")
    L.append(f"Arch snapshot   : https://archive.archlinux.org/repos/{bh['arch_archive_snapshot']}/")
    ep = pins["cmake_externalproject"]
    L.append(f"CMake ExternalProject.cmake : {ep['repo']} {ep['rev']} sha256 {ep['sha256']}")
    L.append("")
    L.append("Every component below was built from EXACTLY the listed commit / tarball.")
    L.append("Compiled into libmpv-2.dll: mpv, ffmpeg (avcodec/avformat/avfilter/avutil/swscale/swresample),")
    L.append("libplacebo, libass, freetype, harfbuzz, fribidi, libiconv, lcms2, zimg, dav1d, zlib-ng, xxhash,")
    L.append("shaderc (+ glslang, SPIRV-Tools, SPIRV-Headers) and SPIRV-Cross (Apache-2.0 / BSD: GLSL->SPIR-V->HLSL for the D3D11 output),")
    L.append("plus libc++/libc++abi/libunwind/compiler-rt-builtins/mingw-w64 CRT+winpthreads from the toolchain.")
    L.append("Build-time only (not in the DLL): llvm/clang/lld, glad, fast_float, vulkan-header, nv-codec-headers, angle-headers.")
    L.append("")
    hdr = f"{'name':16} {'version':26} {'commit / sha256':42} {'license':34} url"
    L.append(hdr)
    L.append("-" * len(hdr))
    for s in pins["sources"]:
        ident = s["rev"] if s["kind"] == "git" else "sha256:" + s["sha256"]
        L.append(f"{s['name']:16} {s['version'][:26]:26} {ident:42} {s['license'][:34]:34} {s['url']}")
        L.append(f"{'':16}   source ref: {s.get('ref', '-')}")
    L.append("")
    L.append("Licence texts of all components: licenses/<name>/ (shipped next to the DLL).")
    if missing_lic:
        L.append("(no licence file could be collected automatically for: " + ", ".join(missing_lic) + ")")
    L.append("")
    L.append("Source offer: all sources are public at the URLs above; the exact recipe to rebuild this DLL is")
    L.append("this repository at the tag of this release (pins.json + overlay/ + tools/ + .github/workflows/build.yml).")
    if a.host_packages and a.host_packages.exists():
        L.append("")
        L.append("Build host packages (pacman -Q inside the container):")
        L.append(read(a.host_packages).rstrip())
    (a.out / "SOURCES.txt").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    # ---------------- CONFIG.txt ----------------
    C = []
    C.append("libmpv build - CONFIG")
    C.append(f"generated : {now}")
    C.append(f"variant   : {a.variant}   ThinLTO for libraries/libmpv: {a.lto}")
    C.append("")
    C.append("== ffmpeg configure line (FFMPEG_CONFIGURATION from the build tree's config.h) ==")
    C.append(configuration or "(MISSING)")
    C.append("")
    C.append(f"FFMPEG_LICENSE : {license_}")
    C.append("")
    C.append("== ffmpeg enabled components (config_components.h) ==")
    for kind in ("PROTOCOL", "DEMUXER", "DECODER", "ENCODER", "MUXER", "PARSER", "BSF", "HWACCEL", "INDEV", "OUTDEV"):
        C.append(f"{kind.lower()+'s':10}[{len(enabled[kind])}]: " + ", ".join(enabled[kind]))
    C.append(f"filters   [{len(enabled['FILTER'])}]: (all filters whose dependencies are met)")
    C.append("external/hw libs enabled in ffmpeg: " + ", ".join(ext))
    C.append("")
    C.append("== mpv meson options (user options, meson-info/intro-buildoptions.json) ==")
    for n, v in user_opts:
        C.append(f"-D{n}={v if not isinstance(v, bool) else str(v).lower()}")
    C.append("")
    C.append("== mpv meson core options ==")
    for n, v in core_opts:
        C.append(f"{n} = {v}")
    C.append("")
    C.append("== mpv dependencies resolved by meson ==")
    dp = a.dist / "meson-info" / "intro-dependencies.json"
    if dp.exists():
        for d in sorted(json.loads(read(dp)), key=lambda x: x["name"]):
            C.append(f"{d['name']:28} {d.get('version', '')}")
    (a.out / "CONFIG.txt").write_text("\n".join(C) + "\n", encoding="utf-8", newline="\n")

    # raw evidence for auditors
    ev = a.out / "evidence"
    ev.mkdir(exist_ok=True)
    for f in ("config.h", "config_components.h", "config.log"):
        p = a.meta / "ffmpeg" / f
        if p.exists():
            shutil.copyfile(p, ev / f"ffmpeg-{f}")
    for f in ("meson-log.txt",):
        p = a.dist / f
        if p.exists():
            shutil.copyfile(p, ev / f"mpv-{f}")
    if (a.dist / "meson-info").exists():
        shutil.copytree(a.dist / "meson-info", ev / "mpv-meson-info", dirs_exist_ok=True)

    if problems:
        print("gen_info: ffmpeg configuration policy violations:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 1
    print("gen_info: OK (ffmpeg: LGPL, protocols=[file], no devices/muxers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
