# libmpv-build

Our own, pinned, minimal **LGPL** build of **libmpv** for Windows x86_64, made for Scrub Explorer
(closed-source PySide6 file manager that embeds libmpv as its video / image-sequence player, either through
the OpenGL render API or with mpv's own Direct3D 11 GPU output rendering into a window handle, `wid`).

Goals, in priority order:

1. **LGPL only.** `-Dgpl=false` for mpv, no `--enable-gpl` / `--enable-version3` / `--enable-nonfree` for ffmpeg.
   The app stays closed; libmpv is a separate, replaceable DLL. (Since the Direct3D 11 output was added the DLL as a whole
   is effectively **LGPL-3.0-or-later**, see "Licence situation".)
2. **We own it.** Nothing depends on somebody else's releases. Every source is pinned to a full
   commit hash (or tarball + sha256) in [`pins.json`](pins.json). A rebuild is reproducible; things only
   change when we change a pin.
3. **Minimal attack surface.** The DLL can only read **local files**: no network stack, no scripting,
   no capture devices, no archive/disc readers.

The workflow ([`.github/workflows/build.yml`](.github/workflows/build.yml)) is `workflow_dispatch` only.

## Contents

| Path | What |
|---|---|
| `pins.json` | **Every** external input: upstream recipe commit, container digest, Arch snapshot date, action SHAs, each source (commit or url+sha256, licence, why it is there). Single source of truth. |
| `overlay/` | Our own cmake package files that replace the corresponding upstream ones (ffmpeg, mpv, libass, libplacebo, spirv-cross, freetype2, harfbuzz, lcms2, libzimg, package list, ExternalProject download). |
| `tools/apply_pins.py` | Copies `overlay/` over the upstream checkout, applies 3 exact-match text edits, rewrites every package to `GIT_TAG <40-hex>`, **fails if anything is unpinned**. |
| `tools/fetch_sources.py` | Fetches each git source at exactly its pinned commit (verifies `HEAD`). |
| `tools/build.sh` | Our build driver (toolchain stage, libs stage). |
| `tools/gen_info.py` | Writes `SOURCES.txt`, `CONFIG.txt`, `licenses/`, `evidence/`; fails if ffmpeg is not LGPL / has network protocols / devices / unexpected libs. |
| `tools/check_dll.py` | Policy check of the finished DLL (imports incl. delay-load, forbidden strings, licence strings). Used by CI and by `verify.ps1`. |
| `verify.ps1` | Run locally on Windows after downloading a release. |
| `reference/` | zhongfly's `compile-lgpl-libmpv.patch` + licence (MIT), kept as attribution / to see what we started from. Not applied. |
| `NOTICE`, `LICENSE` | Attributions; licence of this repository's own files (MIT). |

## Licence situation (read this before shipping)

* **mpv** is built with `-Dgpl=false` => **LGPL-2.1-or-later**.
* **The DLL as a whole is effectively LGPL-3.0-or-later.** The Direct3D 11 GPU output links shaderc, glslang,
  SPIRV-Tools, SPIRV-Headers and SPIRV-Cross statically (Apache-2.0 / BSD / MIT). Apache-2.0 is compatible with the LGPL only from
  version 3 on; mpv, FFmpeg and libplacebo are all "2.1 **or later**", so they can be combined under the LGPL-3.0. Practically nothing
  changes for the application (separate replaceable DLL, licence texts, source offer, see below), except that the third-party notices
  must say "LGPL-3.0-or-later" for libmpv and list the Apache-2.0 components with their NOTICE/LICENSE texts (`licenses/` of the release).
* **FFmpeg** is built without `--enable-gpl`, `--enable-version3`, `--enable-nonfree` => **LGPL-2.1-or-later**.
  Only two external libraries are linked into it: zlib-ng (zlib licence) and dav1d (BSD-2). CI fails the
  build if `config.h` says anything else (`tools/gen_info.py`).
* Statically linked into the DLL besides mpv + ffmpeg: libplacebo (LGPL-2.1+), libass (ISC),
  freetype (FTL), harfbuzz (MIT), fribidi (LGPL-2.1+), libiconv (LGPL-2.1+), lcms2 (MIT),
  zimg (WTFPL), xxhash (BSD-2), shaderc (Apache-2.0), glslang (BSD/MIT/Apache-2.0), SPIRV-Tools (Apache-2.0),
  SPIRV-Headers (MIT-style), SPIRV-Cross (Apache-2.0), plus libc++/libc++abi/libunwind/compiler-rt builtins (Apache-2.0 with
  LLVM exception) and the mingw-w64 CRT/winpthreads (ZPL/public domain). Texts are in `licenses/`.
* **No GPL component is linked.** The DLL has no Lua, no MuJS, no libcurl, no rubberband, no x264/x265, no libbluray, no libarchive.
* The upstream build recipe `shinchiro/mpv-winbuild-cmake` publishes **no licence**. We therefore do **not** copy it
  into this repo: CI checks it out at a pinned commit and our overlay replaces/edits the parts that matter.
  If this repo is ever made public, ask the author or replace the framework (see NOTICE).

### Obligations for the application (LGPL-2.1 section 6, "closed app + separate DLL")

1. Ship `libmpv-2.dll` as a **separate file** that the user can replace (do not embed it in an exe or
   obfuscate/encrypt it). Loading it with `ctypes`/`LoadLibrary` from a normal folder is exactly that.
2. Ship the licence texts (`licenses/` of the release) and mention mpv / FFmpeg / libplacebo / libass / ... and
   their licences in the app's "About / third-party notices".
3. Offer the corresponding source: ship (or link in the notices) `SOURCES.txt` and say that the exact
   build recipe is this repository at the release tag. All sources are public at the URLs in `SOURCES.txt`.
   Because this repo is private, **keep a copy of the repo (zip of the release tag) with every app release** so that the
   offer can actually be honoured.
4. Do not forbid reverse engineering / modification of the DLL in the app's licence.
   (LGPL-3.0 additionally: no technical measures that stop the user from running a modified DLL in place of ours.)
5. Do not add GPL-only pieces (e.g. a different libmpv build with `--enable-gpl`) next to it without re-checking.

## How to rebuild

1. Push this repo to `Amriel/libmpv-build` (public: it is the LGPL build recipe that ships with Scrub Explorer). Actions must be allowed to run; only GitHub-owned actions
   (`actions/checkout`, `actions/cache`, `actions/upload-artifact`, `actions/download-artifact`) are used, pinned to commit SHAs.
2. Actions -> `build-libmpv` -> *Run workflow*. Inputs:
   * `release` (default off) + `release_tag` (e.g. `libmpv-0.41.0-1095-r1`, must not exist) -> creates a GitHub release in this repo.
   * `include_v3` (default off): also build an x86-64-v3 (AVX2) variant. Separate toolchain => ~2x the CI time.
   * `lto` (default on): ThinLTO like the upstream recipe. Off = faster, for debugging only.
   * `runner`: label, default `ubuntu-latest`.
3. Without `release`, the result is the workflow artifact `libmpv-64` (and `libmpv-64-v3`) plus `logs-*`.
4. Download, then run `.\verify.ps1 -Dll <path>\libmpv-2.dll` locally.

What a run does: bootstrap the Arch container (digest-pinned) from a dated Arch Linux Archive snapshot -> checkout
upstream recipe at the pinned commit -> `apply_pins.py` -> `fetch_sources.py` -> build the clang/lld/libc++/mingw-w64 toolchain
(cached by `actions/cache`, key = hash of the toolchain pins) -> build zlib, libiconv, fribidi, freetype, harfbuzz, libass,
ffnvcodec headers, xxhash, dav1d, lcms2, zimg, spirv-headers, spirv-tools, glslang, shaderc, spirv-cross, libplacebo, ffmpeg, mpv -> `gen_info.py` -> `check_dll.py` -> upload.
A failed policy check fails the build job, so a release is never published from a DLL that violates the policy
(the artifact is still uploaded for inspection).

Release assets: `libmpv-2.dll`, `libmpv-2.dll.sha256`, `SOURCES.txt`, `CONFIG.txt`, `libmpv-dev.zip`
(`include/mpv/*.h` + `libmpv.dll.a`), `licenses.zip`, `build-evidence.zip`; with `include_v3` also
`libmpv-2.x86-64-v3.dll` (+ `.sha256`, `CONFIG.x86-64-v3.txt`; rename to `libmpv-2.dll` to use it).

## How to bump a pin

* **A library** (e.g. libass): in `pins.json` change `rev` (full 40-hex commit; look it up with
  `gh api repos/libass/libass/commits/<tag> --jq .sha`), `ref`, `version`. Run the workflow with `release=false`, verify, then release.
  If the library is also a *submodule of libplacebo* (`glad`, `fast_float`), take the commit that the new libplacebo tag
  references: `gh api "repos/haasn/libplacebo/contents/3rdparty/glad?ref=<tag-sha>" --jq .sha`.
* **mpv or ffmpeg**: change `rev`. Check mpv's `meson.build` minimum versions (libplacebo, libass, ffmpeg libs) against the other pins.
  Re-read `overlay/packages/mpv.cmake` against the new `meson.options` (new features default to `auto`!): a new option that
  pulls in a network/scripting feature must be added as `disabled`. Same for ffmpeg: check `ffbuild/config.log` for
  "did not match anything" after renames of decoders/demuxers.
* **A tarball** (`libiconv`): change `url` and `sha256` in `pins.json` only; `apply_pins.py` rewrites `URL`/`URL_HASH` in the cmake file, and CMake verifies the hash on download. (For a new libiconv version also check the `set(VERSION ...)` line of upstream `libiconv.cmake`, it only labels the generated `iconv.pc`.)
* **The toolchain** (`llvm`, `mingw-w64`): change `rev`; the toolchain cache key changes automatically (first run is slow again).
* **The upstream recipe** (`upstream_recipe.rev`): `apply_pins.py` refuses to run if any upstream file we replace or edit has
  changed (`upstream_files_expected_sha256`). Diff the new upstream version of those files against our overlay, port what is needed, then update the hashes.
* **Build host**: new Arch snapshot date -> `ARCH_SNAPSHOT` in the workflow **and** `pins.json build_host`; new container digest ->
  the `image:` line **and** `pins.json` (`tools/pins_info.py check-workflow` fails the build if they disagree).
  Get a digest with `docker buildx imagetools inspect ghcr.io/archlinux/archlinux:base-devel` (or `skopeo inspect`).
* **GitHub actions**: new commit SHA in the workflow **and** `pins.json actions` (same check).

## What was disabled, and why

### FFmpeg (`overlay/packages/ffmpeg.cmake`)

| Setting | Why |
|---|---|
| `--disable-everything` then whitelist | Only listed decoders/demuxers/hwaccels/protocols exist. Unknown codecs/containers cannot be reached. |
| `--disable-autodetect` | Mingw would otherwise silently enable schannel, bcrypt TLS, mediafoundation, iconv, lzma, bzlib ... |
| `--disable-network` | No ws2_32 link, no sockets, no TLS. |
| `--enable-protocol=file` only | No http/https/tcp/udp/rtp/rtmp/ftp/tls/pipe/fd/data/concat... Even a media file or playlist that names `http://...` cannot make ffmpeg connect. |
| `--disable-avdevice`, no indev/outdev | The reference DLL exposed `avdevice://gdigrab:desktop` (screen capture) and VFW capture (AVICAP32). Gone. |
| `--disable-programs --disable-doc` | Not needed (libpostproc no longer exists at the pinned commit). |
| no muxers; encoders only `png`,`mjpeg` | mpv's `screenshot` writes png/jpeg through libavcodec encoders, no muxer. Nothing else is written. |
| external libs: only `zlib`, `libdav1d` | Everything else has a native ffmpeg decoder (vp8/vp9/opus/vorbis/mp3/aac/flac/webp/png/exr/...). Dropped: libvpx, libwebp, libopus, libvorbis, lame, speex, soxr, bs2b, aom, svt-av1, jxl, zimg(in ffmpeg), vpl, amf, vaapi, openssl, libssh, libsrt, libxml2, x264/x265, bluray, dvd*, rubberband, openal, fontconfig/freetype/harfbuzz/libass(in ffmpeg), libplacebo(in ffmpeg), lcms2(in ffmpeg), modplug, openmpt, mysofa, zvbi, aribcaption, uavs3d, davs2, avisynth, vapoursynth. |
| hwaccels: `*_d3d11va`, `*_d3d11va2`, `*_dxva2`, `*_nvdec` (+ `--enable-d3d11va --enable-dxva2 --enable-ffnvcodec --enable-cuda --enable-nvdec`) | Hardware decode. nv-codec-headers are MIT headers; `nvcuda`/`nvcuvid` are `dlopen`ed at runtime. No QSV/AMF/Vulkan/VAAPI. |
| no `--enable-version3` | Nothing we enable needs it => plain LGPL-2.1+. |
| `--enable-filters`, `--enable-parsers`, `--enable-bsfs` (all) | mpv requires libavfilter, many of its features (`scale`, `format`, `aformat`, `yadif`, `hwdownload`, user `--vf=lavfi=`) use filters; parsers/bsfs are tiny and needed by mpv's hwdec paths. Filters that need a missing external library or GPL are dropped by configure automatically. |

Decoders: h264 hevc av1(libdav1d + native hwaccel) vp8 vp9 mpeg1/2/4 msmpeg4 h263 vc1 wmv theora flv svq1/3 rv10-40 cinepak dvvideo;
prores prores_raw dnxhd cfhd ffv1 ffvhuff huffyuv utvideo qtrle magicyuv hap lagarith apv aic dxv cllc mjpeg jpegls jpeg2000;
rawvideo v210 r210 r10k avrp avui y41p yuv4; png apng exr dpx tiff bmp targa gif webp pnm family sgi pcx qoi hdr psd sunrast xbm xwd dds;
audio aac mp1/2/3 ac3 eac3 truehd mlp dca flac opus vorbis alac wma* ape wavpack tta tak shorten amr dst cook pcm_* adpcm_* dsd_* atrac* gsm* ra_*;
subtitles ass ssa subrip webvtt movtext text dvdsub pgssub dvbsub.
Demuxers: mov(mp4) matroska(webm) mxf avi mpegts mpegps mpegvideo image2 image2pipe image_*_pipe wav w64 flac mp3 ogg aac ac3 eac3 dts truehd flv gif caf aiff amr ape asf au dv dsf iff ivf h264 hevc av1 obu y4m rawvideo dnxhd mjpeg vc1 tak tta voc wv xwma rm + text subtitle formats.
The exact enabled lists end up in `CONFIG.txt` of each release (taken from ffmpeg's `config_components.h`).

### mpv (`overlay/packages/mpv.cmake`)

| Setting | Why |
|---|---|
| `-Dgpl=false` | LGPL build. Also removes every GPL-only feature (x11, jack, oss, caca, dvdnav, cdda, dvbin, direct3d vo ...). |
| `-Dlibmpv=true -Dcplayer=false` | Only the library. |
| `-Dlibcurl=disabled` | Removes the curl stream backend (http/https/ftp...), WLDAP32, CRYPT32, Secur32, WS2_32. |
| `-Dlua=disabled -Djavascript=disabled` | No script engine, no `lua_`/`mujs` strings, no `ytdl_hook`, no `osc.lua`. |
| `-Dvapoursynth=disabled` | The reference DLL could load VapourSynth scripts. |
| `-Dlibarchive=disabled -Dlibbluray=disabled -Ddvdnav=disabled -Ddvda=disabled -Dcdda=disabled -Ddvbin=disabled` | Archive/disc/tuner readers. |
| `-Dlibavdevice=disabled` | No capture devices (matches ffmpeg `--disable-avdevice`). |
| `-Dcplugins=disabled` | No loading of C plugin DLLs. |
| `-Dwin32-smtc=disabled` | No Windows media-transport controls (drops C++/WinRT and the winrt imports). |
| `-Drubberband -Dopenal -Dsdl2-gamepad -Dsdl2-audio -Dsdl2-video -Dsubrandr -Dsixel -Duchardet -Djpeg = disabled` | Not needed; `jpeg` screenshots use ffmpeg's mjpeg encoder. |
| `-Dvulkan=disabled` | The Vulkan path is not used (no vulkan-1.dll, no Vulkan loader). libplacebo still compiles its Vulkan *stubs* against the header-only `vulkan-header` pin. |
| `-Dd3d11=enabled -Dshaderc=enabled -Dspirv-cross=enabled` | **Direct3D 11 GPU output** (`vo=gpu-next`/`gpu` with `gpu-api=d3d11`, `gpu-context=d3d11`, `d3d11-flip`, ...) for embedding via `wid`. It needs a GLSL->SPIR-V compiler (shaderc, bundles glslang + SPIRV-Tools) and SPIRV-Cross (SPIR-V->HLSL); libplacebo is built with `-Dd3d11=enabled -Dshaderc=enabled -Dglslang=disabled` against the same libraries. All statically linked; this is what makes the DLL effectively LGPL-3.0-or-later (Apache-2.0 parts). `d3d11.dll`/`dxgi.dll` are loaded by the DLL at runtime; `d3dcompiler_47.dll` (system) is loaded by mpv when it compiles HLSL. |
| `-Degl-angle-lib=disabled -Degl-angle-win32=disabled` | No ANGLE as GL context, no `libEGL.dll` link. (`-Degl-angle=enabled` stays: headers only, needed for the d3d11->EGL interop code, which dlopens ANGLE only if an ANGLE context is used.) |
| `-Dmanpage/html/pdf-build=disabled`, `-Dtests=false`, `-Dbuild-date=false` | Reproducibility / nothing to build. |
| **kept**: `gl`, `plain-gl`, `gl-win32`, `gl-dxinterop(+d3d9)`, `egl-angle`(headers), `d3d-hwaccel`, `d3d9-hwaccel`, `cuda-hwaccel`, `cuda-interop`, `wasapi`, `iconv`, `zlib`, `lcms2`, `zimg` | Render API + hwdec interop + audio output + colour management / high quality sw conversion (parity with the verified reference build). |

Other components removed from the superbuild: vulkan loader (only the headers are kept), luajit, mujs,
libarchive, libbluray, libudfread, libdvd*, rubberband, libsamplerate, openal-soft, libsdl2, vapoursynth, curl/openssl/mbedtls/nettle/libssh/libsrt/nghttp*/ngtcp2/c-ares/libpsl,
x264/x265/aom/svtav1/libvpx/libwebp/libjxl/highway/brotli/uavs3d/davs2, opus/vorbis/ogg/lame/speex/soxr/bs2b/libopenmpt/modplug/gme, libva/libvpl/amf,
fontconfig/expat/libxml2/libunibreak, libpng/libjpeg/bzip2/xz/lzo/zstd, uchardet, libsixel, subrandr (rust), cppwinrt, gcc toolchain, rustup, widl, openmp.

### Toolchain edits (3 exact-match edits in `tools/apply_pins.py`)

LLVM builds only the **X86** backend (was `AArch64,X86,NVPTX`; NVPTX was only for `--enable-cuda-llvm`) with `LLVM_PARALLEL_LINK_JOBS=2`
(avoids OOM on 7 GB runners); `cppwinrt`, `gcc`, `gcc-binutils`, `widl`, `rustup`, `llvm-openmp` are dropped from the toolchain list.

## What could NOT be removed (and why)

* **libass, libplacebo, libavfilter** are unconditional `dependency()` calls in mpv's `meson.build`. libass pulls freetype + harfbuzz + fribidi
  (we dropped fontconfig/libunibreak: libass uses DirectWrite on Windows). Subtitles/OSD text can therefore not be compiled out.
  Runtime mitigation is in the app: no subtitle tracks selected / `sid=no`.
* `osdep/w32_register.c` (registry), `input/ipc-win.c` (named pipe IPC server), `player/clipboard/clipboard-win.c`, `video/out/w32_common.c`
  (window/keyboard hooks) and the win32-desktop import libraries are compiled into every Windows desktop build of libmpv. So the imports
  `SetWindowsHookExW`, `RegSetValueExW`/`RegCreateKeyExW`, `ShellExecuteW`, `ConnectNamedPipe`, `OpenProcess` etc. **remain**. They are
  only reachable through mpv commands/options (`input-ipc-server`, file association registration, `--ontop`-style window code) that the app does not
  use; set `config=no`, `input-ipc-server` unset, `load-scripts=no`, `input-default-bindings=no`, `osc=no` in the app. The policy
  list that makes CI fail is exactly: ws2_32, wldap32, winhttp, wininet, urlmon.
* `bcrypt.dll` (ffmpeg `av_random_bytes`) stays; it is local entropy only.

## Expected imports of the new DLL (prediction; the first run confirms)

Reference (zhongfly LGPL build) had 47 DLLs incl. WS2_32, WLDAP32, CRYPT32, Secur32, Normaliz, IPHLPAPI, SETUPAPI, AVICAP32, vulkan-1, d2d1, winrt, WINMM.
Expected now: `KERNEL32`, `api-ms-win-crt-*` (UCRT), `api-ms-win-core-synch-l1-2-0`, `api-ms-win-core-path-l1-1-0`, `ADVAPI32`, `USER32`, `GDI32`, `IMM32`, `SHELL32`, `SHCORE`,
`SHLWAPI`(maybe), `ole32`, `OLEAUT32`(maybe), `OPENGL32`, `dwmapi`, `UxTheme`, `VERSION`, `AVRT`, `ntdll`, `bcrypt`, `bcryptprimitives`, `WINMM`, `DWrite`(libass DirectWrite).
**Gone:** WS2_32, WLDAP32, CRYPT32, Secur32, Normaliz, IPHLPAPI, SETUPAPI, AVICAP32, vulkan-1, the winrt api-sets, (d2d1 should go too: it came from the C++/WinRT/SMTC or capture code; if it stays it is a local GPU API).
Dynamic (`LoadLibrary`) only: `d3d11`, `dxgi`, `d3dcompiler_47`, `d3d9`, `nvcuda`, `nvcuvid`, `libEGL` (only if an ANGLE context is requested).

## Using it from the app

### Direct3D 11 output through `wid` (preferred on Windows)

Give mpv a child window of the Qt widget and let it render itself: `wid=<HWND>`, `vo=gpu-next`, `gpu-api=d3d11`, `gpu-context=d3d11`
(`d3d11-flip=yes` is the default flip-model swap chain; `no` falls back to the blt model, which some NVIDIA/driver setups need for
fullscreen). Hardware decode is zero-copy with `hwdec=d3d11va` (or `d3d11va-copy`, `nvdec`). Check at run time with
`option-info/gpu-api/choices` and `option-info/gpu-context/choices` that `d3d11` is listed (the CI release gate does this headless with `vo=null`).

### OpenGL render API (Qt/WGL context)

Still built and unchanged. Working hardware decode paths with a normal desktop-GL Qt context: `hwdec=d3d11va-copy`, `dxva2-copy`, `dxva2` (zero-copy through WGL_NV_DX_interop),
`nvdec` (CUDA-GL interop). Zero-copy `d3d11va` needs an ANGLE EGL context, which Qt-with-desktop-GL does not provide.
Recommended defensive options: `config=no`, `load-scripts=no`, `input-default-bindings=no`, `input-vo-keyboard=no`, `osc=no`,
`terminal=no`, `ytdl=no`, `load-unsafe-playlists=no`, `access-references=no`, `sub-auto=no`, `audio-display=no`, `autoload-files=no`.

## Reading the first CI run

* The build job prints the last 150 lines of the newest package logs when a step fails (`LAST LOGS`). All per-package logs
  (`<pkg>-configure.log`, `-build.log`, ...) and ffmpeg's `ffbuild/config.log` are in artifact `logs-64`.
* Typical first-run failures, in the order they would occur:
  1. `pacman` sandbox/landlock error inside the container -> add `--disable-sandbox` to the `pacman` calls (workflow + `tools/setup_host.sh`).
  2. `apply_pins.py: ... sha256 ... != reviewed` -> the upstream checkout is not the pinned commit / a file changed; read the message.
  3. `fetch_sources.py` timeouts: re-run (it retries 3x). `git fetch --depth 1 origin <sha>` needs the commit to be reachable from a ref (all pins are).
  4. LLVM stage: out of disk (needs ~15-20 GB) or OOM -> use a larger runner (`runner` input); a missing sparse directory -> adjust `sparse` of `llvm` in `pins.json`.
  5. mingw-w64-crt `autoreconf` errors -> `mingw-w64` master moved on a toolchain assumption; pin `v14.0.0` (`9b3dd0125792fe94d16cacdc596dbd42fca1b369`) instead.
  6. `libiconv` download: ftp.gnu.org slow/unreachable -> change `url` to `https://ftpmirror.gnu.org/libiconv/libiconv-1.18.tar.gz` (same sha256) in `pins.json` (see "bump a tarball").
  7. Meson "Unknown option"/"not one of the available choices" for a pinned library (freetype/harfbuzz/libass/libplacebo): the message names the option; fix in the matching `overlay/packages/*.cmake`.
  8. libplacebo/glad: "jinja2 not found" -> `python-jinja` missing from the Arch snapshot; check `tools/setup_host.sh`.
  9. ffmpeg configure: read the **tail of `ffbuild/config.log`**; lines `Option --enable-... did not match anything` mean a renamed decoder/demuxer (harmless but then the format is missing).
  10. mpv meson: "feature X is required but not found" for an `enabled` option (e.g. `gl-dxinterop`, `wasapi`) -> change that single option to `auto`/`disabled` after checking whether the app needs it.
  11. `check_dll.py` FAIL: a forbidden import/string is present. `lua_` / `mujs` hits are the only likely false positives (a substring in a symbol name); inspect with `strings`.

Estimated time (see report): first run 2-3 h on a 4-core runner (3.5-4.5 h on 2 cores), later runs with toolchain cache ~30-45 min.
Private-repo minutes: ~200-300 min for the first run (Free plan: 2000 min/month), ~40 min afterwards; `include_v3` doubles that.
