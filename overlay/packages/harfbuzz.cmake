# libmpv-build overlay: packages/harfbuzz.cmake
# Needed only by libass. Text shaping only: no icu/glib/cairo/png/zlib, none of the newer
# raster/vector/gpu/subset helper libraries, no utilities.
ExternalProject_Add(harfbuzz
    DEPENDS
        freetype2
    GIT_REPOSITORY https://github.com/harfbuzz/harfbuzz.git
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    UPDATE_COMMAND ""
    CONFIGURE_COMMAND ${EXEC} CONF=1 meson setup <BINARY_DIR> <SOURCE_DIR>
        --prefix=${MINGW_INSTALL_PREFIX}
        --libdir=${MINGW_INSTALL_PREFIX}/lib
        --cross-file=${MESON_CROSS}
        --buildtype=release
        --default-library=static
        -Dfreetype=enabled
        -Dicu=disabled
        -Dglib=disabled
        -Dgobject=disabled
        -Dcairo=disabled
        -Dchafa=disabled
        -Dpng=disabled
        -Dzlib=disabled
        -Draster=disabled
        -Dvector=disabled
        -Dgpu=disabled
        -Dgpu_demo=disabled
        -Dsubset=disabled
        -Dutilities=disabled
        -Dtests=disabled
        -Ddocs=disabled
        -Dbenchmark=disabled
        -Dintrospection=disabled
    BUILD_COMMAND ${EXEC} ninja -C <BINARY_DIR>
    INSTALL_COMMAND ${EXEC} ninja -C <BINARY_DIR> install
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

force_rebuild_git(harfbuzz)
force_meson_configure(harfbuzz)
cleanup(harfbuzz install)
