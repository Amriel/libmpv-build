# libmpv-build overlay: packages/libplacebo.cmake
# libplacebo is a hard dependency of mpv. For the OpenGL render API we only need its OpenGL
# backend: Vulkan, D3D11, glslang, shaderc (=> no vulkan loader/headers, shaderc, glslang,
# spirv-tools/headers/cross packages at all) are OFF.
#
# vulkan-header: HEADERS ONLY (upstream's unmodified vulkan-header.cmake, pinned). Even with
# -Dvulkan=disabled libplacebo compiles src/vulkan/stubs.c, which includes <vulkan/vulkan.h>
# (libplacebo/vulkan.h is public API). No Vulkan loader/driver code ends up in the DLL;
# stubs.c only returns "compiled without Vulkan support".
#
# Submodules: GIT_SUBMODULES "" => none are cloned. 3rdparty/glad and 3rdparty/fast_float are
# replaced by symlinks to our own pinned checkouts of exactly the commits that libplacebo
# v7.360.1 references (pins.json: glad, fast_float). jinja2/markupsafe (needed by glad) come
# from the Arch packages python-jinja / python-markupsafe of the pinned Arch snapshot.
get_property(src_glad TARGET glad PROPERTY _EP_SOURCE_DIR)
get_property(src_fast_float TARGET fast_float PROPERTY _EP_SOURCE_DIR)
ExternalProject_Add(libplacebo
    DEPENDS
        lcms2
        glad
        fast_float
        xxhash
        vulkan-header
    GIT_REPOSITORY https://github.com/haasn/libplacebo.git
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    GIT_SUBMODULES ""
    UPDATE_COMMAND ""
    CONFIGURE_COMMAND ""
    COMMAND bash -c "rm -rf <SOURCE_DIR>/3rdparty/glad"
    COMMAND bash -c "rm -rf <SOURCE_DIR>/3rdparty/fast_float"
    COMMAND bash -c "ln -s ${src_glad} <SOURCE_DIR>/3rdparty/glad"
    COMMAND bash -c "ln -s ${src_fast_float} <SOURCE_DIR>/3rdparty/fast_float"
    COMMAND ${EXEC} CONF=1 meson setup <BINARY_DIR> <SOURCE_DIR>
        --prefix=${MINGW_INSTALL_PREFIX}
        --libdir=${MINGW_INSTALL_PREFIX}/lib
        --cross-file=${MESON_CROSS}
        --default-library=static
        -Dopengl=enabled
        -Dvulkan=disabled
        -Dd3d11=disabled
        -Dglslang=disabled
        -Dshaderc=disabled
        -Dlcms=enabled
        -Dunwind=disabled
        -Ddemos=false
        -Dtests=false
        -Ddebug=true
        -Db_ndebug=true
        -Doptimization=3
    BUILD_COMMAND ${EXEC} ninja -C <BINARY_DIR>
    INSTALL_COMMAND ${EXEC} ninja -C <BINARY_DIR> install
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

force_rebuild_git(libplacebo)
force_meson_configure(libplacebo)
cleanup(libplacebo install)
