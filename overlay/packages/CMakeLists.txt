# libmpv-build overlay: replaces packages/CMakeLists.txt of shinchiro/mpv-winbuild-cmake.
#
# Written by this project (see NOTICE). It only uses the macros that the upstream
# framework provides (ExternalProject_Add, cleanup(), force_rebuild_git(), ...).
#
# Differences from the upstream list (which has ~100 packages):
#   * only the packages needed for an LGPL, local-files-only, OpenGL-render-API libmpv;
#   * order matters: glad + fast_float must be defined before libplacebo, dav1d/nvcodec-headers
#     before ffmpeg, ffmpeg + libplacebo + libass before mpv;
#   * no `update` target (we never `git fetch` newer sources), no cargo/rust target.
set_property(DIRECTORY PROPERTY EP_STEP_TARGETS download)
include(${PROJECT_SOURCE_DIR}/cmake/packages_check.cmake)

list(APPEND ep
    zlib
    libiconv
    fribidi
    freetype2
    harfbuzz
    libass
    nvcodec-headers
    xxhash
    dav1d
    lcms2
    libzimg
    glad
    fast_float
    vulkan-header
    libplacebo
    angle-headers
    ffmpeg
    mpv
)

foreach(package IN LISTS ep)
    if(NOT ${SINGLE_SOURCE_LOCATION} STREQUAL "")
        set(SOURCE_LOCATION "${SINGLE_SOURCE_LOCATION}/${package}")
    endif()
    include(${CMAKE_CURRENT_SOURCE_DIR}/${package}.cmake)
    set(SOURCE_LOCATION "")
endforeach()
list(LENGTH ep ep_length)
message(STATUS "Parsing ${ep_length} packages")

list(TRANSFORM ep APPEND "-download" OUTPUT_VARIABLE download)
list(TRANSFORM ep APPEND "-fullclean" OUTPUT_VARIABLE fullclean)

add_custom_target(download
    COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR} --target ${download}
)

add_custom_target(package-fullclean
    COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR} --target ${fullclean}
    COMMENT "Remove all stamp files, reset git HEAD"
)
