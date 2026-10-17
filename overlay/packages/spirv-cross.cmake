# libmpv-build overlay: packages/spirv-cross.cmake
# SPIRV-Cross (Apache-2.0 / MIT parts), needed by libplacebo's D3D11 backend and by mpv's d3d11 VO
# to translate SPIR-V to HLSL. Only the C API library (spirv-cross-c-shared + its .pc file) is built,
# as a STATIC archive: patches/spirv-cross-0001-static-c-api.patch. No CLI, no tests.
ExternalProject_Add(spirv-cross
    GIT_REPOSITORY https://github.com/KhronosGroup/SPIRV-Cross.git
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    UPDATE_COMMAND ""
    PATCH_COMMAND ${EXEC} git am --3way ${CMAKE_SOURCE_DIR}/../patches/spirv-cross-0001-static-c-api.patch
    CONFIGURE_COMMAND ${EXEC} CONF=1 cmake -H<SOURCE_DIR> -B<BINARY_DIR>
        -G Ninja
        -DCMAKE_BUILD_TYPE=Release
        -DCMAKE_TOOLCHAIN_FILE=${TOOLCHAIN_FILE}
        -DCMAKE_INSTALL_PREFIX=${MINGW_INSTALL_PREFIX}
        -DCMAKE_FIND_ROOT_PATH=${MINGW_INSTALL_PREFIX}
        -DBUILD_SHARED_LIBS=OFF
        -DSPIRV_CROSS_SHARED=ON
        -DSPIRV_CROSS_CLI=OFF
        -DSPIRV_CROSS_ENABLE_TESTS=OFF
        -DCMAKE_CXX_FLAGS='${CMAKE_CXX_FLAGS} -D__USE_MINGW_ANSI_STDIO'
    BUILD_COMMAND ${EXEC} ninja -C <BINARY_DIR>
    INSTALL_COMMAND ${EXEC} ninja -C <BINARY_DIR> install
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

force_rebuild_git(spirv-cross)
cleanup(spirv-cross install)
