# libmpv-build overlay: packages/libzimg.cmake
# zimg release-3.0.6 (no graphengine submodule at this tag; the upstream recipe's graphengine
# package is only needed for zimg master). Autotools, in-source build.
ExternalProject_Add(libzimg
    GIT_REPOSITORY https://github.com/sekrit-twc/zimg.git
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    GIT_SUBMODULES ""
    UPDATE_COMMAND ""
    # Upstream commit 67e0603271c0 "Add missing includes for libcxx-23" on top of
    # release-3.0.6: libc++ 23 no longer pulls <exception> in transitively and
    # zimg.cpp uses std::exception_ptr (first CI run failed exactly there). We stay
    # on 3.0.6 instead of master because master also changes colour defaults
    # (chromatic adaptation off by default).
    PATCH_COMMAND ${EXEC} git am --3way ${CMAKE_CURRENT_SOURCE_DIR}/libzimg-*.patch
    CONFIGURE_COMMAND ${EXEC} <SOURCE_DIR>/autogen.sh && CONF=1 <SOURCE_DIR>/configure
        --host=${TARGET_ARCH}
        --prefix=${MINGW_INSTALL_PREFIX}
        --disable-shared
    BUILD_COMMAND ${MAKE}
    INSTALL_COMMAND ${MAKE} install
    BUILD_IN_SOURCE 1
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

force_rebuild_git(libzimg)
cleanup(libzimg install)
