# libmpv-build overlay: packages/mpv.cmake
#
# libmpv only (no mpv.exe), LGPL (-Dgpl=false), OpenGL render API, local files only.
# Every optional feature is stated explicitly (enabled or disabled) so that the result does not
# depend on what happens to be installed in the build environment ("auto" is never used for
# anything that matters).
#
# Hard facts about mpv 0.41.x that cannot be configured away (see README "What could not be removed"):
#   * libass, libplacebo, libavfilter, libavcodec/format/util, libswscale, libswresample are
#     unconditional dependencies.
#   * osdep/w32_register.c, input/ipc-win.c, player/clipboard/clipboard-win.c, video/out/w32_common.c
#     and the win32-desktop import libs (avrt dwmapi gdi32 imm32 ntdll ole32 pathcch shcore user32
#     uuid uxtheme version) are compiled for every win32-desktop build.

ExternalProject_Add(mpv
    DEPENDS
        angle-headers
        ffmpeg
        lcms2
        libass
        libiconv
        libplacebo
        libzimg
        nvcodec-headers
        zlib
    GIT_REPOSITORY https://github.com/mpv-player/mpv.git
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    UPDATE_COMMAND ""
    # With d3d11 VO, ANGLE and Vulkan all off, mpv never runs its DXGI_DEBUG_D3D11
    # header check, yet d3d-hwaccel still builds vf_d3d11vpp.c -> the GUID is defined
    # twice against current mingw-w64 (CI run 5). Our patch runs the check for
    # d3d-hwaccel too. Generated against the pinned commit (blob c49aa3c).
    PATCH_COMMAND ${EXEC} git am --3way ${CMAKE_SOURCE_DIR}/../patches/mpv-0001-dxgi-debug-check-with-d3d-hwaccel.patch
    CONFIGURE_COMMAND ${EXEC} CONF=1 meson setup <BINARY_DIR> <SOURCE_DIR>
        --prefix=${MINGW_INSTALL_PREFIX}
        --libdir=${MINGW_INSTALL_PREFIX}/lib
        --cross-file=${MESON_CROSS}
        --default-library=shared
        --prefer-static
        -Ddebug=true
        -Db_ndebug=true
        -Doptimization=3
        -Db_lto=true
        ${mpv_lto_mode}
        # ---- what we build
        -Dgpl=false
        -Dlibmpv=true
        -Dcplayer=false
        -Dbuild-date=false
        -Dtests=false
        # ---- network / scripting / extra input sources: OFF
        -Dlibcurl=disabled
        -Dlua=disabled
        -Djavascript=disabled
        -Dvapoursynth=disabled
        -Dlibarchive=disabled
        -Dlibbluray=disabled
        -Ddvdnav=disabled
        -Ddvda=disabled
        -Dcdda=disabled
        -Ddvbin=disabled
        -Dlibavdevice=disabled
        -Dcplugins=disabled
        -Dwin32-smtc=disabled
        # ---- audio/video output + helper libs we do not use: OFF
        -Drubberband=disabled
        -Dopenal=disabled
        -Dsdl2-gamepad=disabled
        -Dsdl2-audio=disabled
        -Dsdl2-video=disabled
        -Dsubrandr=disabled
        -Dsixel=disabled
        -Duchardet=disabled
        -Djpeg=disabled
        -Dvulkan=disabled
        -Dshaderc=disabled
        -Dspirv-cross=disabled
        -Dd3d11=disabled
        -Degl-angle-lib=disabled
        -Degl-angle-win32=disabled
        -Dmanpage-build=disabled
        -Dhtml-build=disabled
        -Dpdf-build=disabled
        # ---- what the OpenGL render API path needs: ON
        -Dgl=enabled
        -Dplain-gl=enabled
        -Dgl-win32=enabled
        -Dgl-dxinterop=enabled
        -Dgl-dxinterop-d3d9=enabled
        -Degl-angle=enabled
        -Dd3d-hwaccel=enabled
        -Dd3d9-hwaccel=enabled
        -Dcuda-hwaccel=enabled
        -Dcuda-interop=enabled
        -Dwasapi=enabled
        -Diconv=enabled
        -Dzlib=enabled
        -Dlcms2=enabled
        -Dzimg=enabled
        -Dc_args='-Wno-error=int-conversion'
    BUILD_COMMAND ${EXEC} LTO_JOB=1 PDB=1 ninja -C <BINARY_DIR>
    INSTALL_COMMAND ""
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

# Collect the distributable pieces. The build dir is wiped right after the last step
# (cleanup() below), so everything we need must be copied here.
set(LIBMPV_DIST ${CMAKE_BINARY_DIR}/libmpv-dist)
ExternalProject_Add_Step(mpv copy-dist
    DEPENDEES build
    COMMAND ${CMAKE_COMMAND} -E remove_directory ${LIBMPV_DIST}
    COMMAND ${CMAKE_COMMAND} -E make_directory ${LIBMPV_DIST}/include/mpv
    COMMAND ${CMAKE_COMMAND} -E copy <BINARY_DIR>/libmpv-2.dll   ${LIBMPV_DIST}/libmpv-2.dll
    COMMAND ${CMAKE_COMMAND} -E copy <BINARY_DIR>/libmpv.dll.a   ${LIBMPV_DIST}/libmpv.dll.a
    COMMAND ${CMAKE_COMMAND} -E copy_directory <SOURCE_DIR>/include/mpv ${LIBMPV_DIST}/include/mpv
    COMMAND ${CMAKE_COMMAND} -E copy_directory <BINARY_DIR>/meson-info ${LIBMPV_DIST}/meson-info
    COMMAND ${CMAKE_COMMAND} -E copy <BINARY_DIR>/meson-logs/meson-log.txt ${LIBMPV_DIST}/meson-log.txt
    # PDB only exists when the linker wrapper produced one; do not fail if it did not.
    COMMAND bash -c "cp <BINARY_DIR>/libmpv-2.pdb ${LIBMPV_DIST}/ 2>/dev/null || true"
    COMMENT "Collecting libmpv-2.dll, headers and meson build info into ${LIBMPV_DIST}"
    LOG 1
)

force_rebuild_git(mpv)
force_meson_configure(mpv)
cleanup(mpv copy-dist)
