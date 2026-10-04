#!/usr/bin/env bash
# Install the host packages of the Arch container from the dated Arch Linux Archive snapshot
# that pins.json names. The workflow already pointed pacman at the snapshot and ran -Syyuu
# (it needs git+python before checkout); this script re-asserts that and installs the rest.
set -euo pipefail
cd "$(dirname "$0")/.."

want_snap="$(python3 tools/pins_info.py get build_host.arch_archive_snapshot)"
if [ "${ARCH_SNAPSHOT:-}" != "$want_snap" ]; then
    echo "ERROR: workflow ARCH_SNAPSHOT='${ARCH_SNAPSHOT:-}' != pins.json '$want_snap'" >&2
    exit 1
fi
if ! grep -q "archive.archlinux.org/repos/$want_snap/" /etc/pacman.d/mirrorlist; then
    echo "ERROR: /etc/pacman.d/mirrorlist is not pointed at the $want_snap snapshot" >&2
    exit 1
fi

# Package -> why:
#   git ninja cmake meson python        build drivers (meson >= 1.3 required by the recipe)
#   clang lld libc++                    host compiler that builds LLVM (LLVM_ENABLE_LIBCXX=ON, lld)
#   nasm yasm                           x86 asm for ffmpeg / dav1d / libass / zimg
#   python-jinja python-markupsafe      libplacebo generates its OpenGL loader with glad (needs jinja2)
#   unzip curl patch                    used by the recipe's download_externalproject.cmake
#   pkgconf autoconf automake libtool m4 make ragel   autotools packages (mingw-w64-crt, zimg, libiconv)
#   zstd tar xz                         actions/cache
pacman -S --noconfirm --needed \
    git ninja cmake meson python \
    clang lld libc++ \
    nasm yasm \
    python-jinja python-markupsafe \
    unzip curl patch \
    pkgconf autoconf automake libtool m4 make ragel \
    zstd tar xz

git config --global --add safe.directory '*'
git config --global user.name "libmpv-build"
git config --global user.email "libmpv-build@users.noreply.github.com"
git config --global advice.detachedHead false

echo "---- host tool versions ----"
cmake --version | head -1
meson --version
ninja --version
clang --version | head -1
nasm --version
git --version
python3 --version
nproc
df -h / | tail -1
