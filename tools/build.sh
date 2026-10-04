#!/usr/bin/env bash
# Our own build driver (replaces upstream build.sh, which downloads zhongfly's packaging zip,
# runs `ninja update` (= git fetch of newer sources!) and runs cargo).
#
#   tools/build.sh <variant> <stage>
#     variant: 64      baseline x86-64  (works on every x86-64 CPU)
#              64-v3   x86-64-v3 (AVX2/BMI2/FMA, Haswell+/Excavator+)
#     stage:   toolchain   build clang/lld/libc++/compiler-rt + mingw-w64 CRT/headers/winpthreads
#                          (skipped if clang_root already holds a toolchain, e.g. from the cache)
#              libs        build all libraries and libmpv-2.dll  (needs the toolchain)
#
# Expects (done by the workflow before this runs):
#   - upstream recipe checked out in $UPSTREAM (default ./upstream) and already passed through
#     tools/apply_pins.py
#   - all sources fetched by tools/fetch_sources.py into $UPSTREAM/src_packages
set -euo pipefail

VARIANT="${1:?variant: 64 | 64-v3}"
STAGE="${2:?stage: toolchain | libs}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UP="$(cd "${UPSTREAM:-$ROOT/upstream}" && pwd)"
SRCDIR="$UP/src_packages"
BUILD="$UP/build$VARIANT"
CLANG_ROOT="$UP/clang_root_$VARIANT"
ARCH="x86_64"
TARGET="$ARCH-w64-mingw32"
MINGW_PREFIX="$BUILD/install/$TARGET"
LTO="${LTO:-ON}"            # ThinLTO for the libraries and libmpv (same as the upstream recipe)

case "$VARIANT" in
    64)     GCC_ARCH_OPT=() ;;
    64-v3)  GCC_ARCH_OPT=(-DGCC_ARCH=x86-64-v3) ;;
    *)      echo "unknown variant $VARIANT" >&2; exit 2 ;;
esac

configure() {
    mkdir -p "$UP/install_rustup"   # cargo_config.in is configure_file()d there; rust itself is NOT used
    cmake -Wno-dev --fresh \
        -DTARGET_ARCH="$TARGET" "${GCC_ARCH_OPT[@]}" \
        -DCOMPILER_TOOLCHAIN=clang \
        -DCMAKE_INSTALL_PREFIX="$CLANG_ROOT" \
        -DMINGW_INSTALL_PREFIX="$MINGW_PREFIX" \
        -DCLANG_PACKAGES_LTO="$LTO" \
        -DENABLE_CCACHE=OFF \
        -DSINGLE_SOURCE_LOCATION="$SRCDIR" \
        -DRUSTUP_LOCATION="$UP/install_rustup" \
        -G Ninja -H"$UP" -B"$BUILD"
}

dump_logs() {
    echo "::group::LAST LOGS (build failed)"
    # newest per-package logs of the superbuild + ffmpeg's config.log
    find "$BUILD" -type f \( -name '*-*.log' -o -path '*/ffbuild/config.log' \) -printf '%T@ %p\n' 2>/dev/null \
        | sort -n | tail -4 | cut -d' ' -f2- | while read -r f; do
            echo "======== $f"; tail -n 150 "$f"
        done
    echo "::endgroup::"
}
trap 'rc=$?; if [ $rc -ne 0 ]; then dump_logs; fi; exit $rc' EXIT

case "$STAGE" in
toolchain)
    configure
    if [ -x "$CLANG_ROOT/bin/clang" ] && [ -f "$MINGW_PREFIX/include/windows.h" ] && [ -f "$CLANG_ROOT/bin/$TARGET-clang" ]; then
        echo "toolchain already present (cache hit) - skipping LLVM/mingw build"
    else
        ninja -C "$BUILD" llvm
        ninja -C "$BUILD" llvm-clang
    fi
    # sanity: the cross compiler must produce a PE x86-64 object
    t="$(mktemp -d)"
    printf 'int main(void){return 0;}\n' > "$t/t.c"
    "$CLANG_ROOT/bin/$TARGET-clang" -c "$t/t.c" -o "$t/t.o"
    "$CLANG_ROOT/bin/clang" --version | head -2
    file "$t/t.o" || true
    rm -rf "$t"
    ;;
libs)
    [ -x "$CLANG_ROOT/bin/clang" ] || { echo "toolchain missing - run the toolchain stage first" >&2; exit 1; }
    configure     # again: GCC_ARCH_HAS_AVX* detection needs the toolchain to exist
    ninja -C "$BUILD" download      # only tarballs (libiconv) are fetched here; git sources are pre-fetched
    ninja -C "$BUILD" mpv
    test -f "$BUILD/libmpv-dist/libmpv-2.dll" || { echo "libmpv-2.dll was not produced" >&2; exit 1; }
    ls -l "$BUILD/libmpv-dist"
    ;;
*)
    echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
