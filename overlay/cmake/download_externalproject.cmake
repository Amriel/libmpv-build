# libmpv-build overlay: replaces cmake/download_externalproject.cmake of
# shinchiro/mpv-winbuild-cmake.
#
# Upstream downloads CMake's ExternalProject.cmake from a mutable *tag* on every fresh
# configure. We fetch the same file by immutable *commit* and verify its sha256
# (values come from pins.json -> cmake_externalproject; keep them in sync).
#
# The patched ExternalProject modules (GIT_CLONE_FLAGS / GIT_CLONE_POST_COMMAND / GIT_RESET)
# are the upstream recipe's own cmake-0001-ExternalProject-changes.patch applied on top.
set(version "v3.31.6")
set(cmake_commit "859ca5c4d7396a011a462878179bc173e1283731")
set(externalproject_sha256 "303d2222b3b39df5e94997ec64a07f6877bbf5297978bf3134347389200da695")

if(NOT EXISTS "${CMAKE_CURRENT_BINARY_DIR}/cmake/Modules/setup_done")
    file(MAKE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/cmake/Modules/ExternalProject)

    execute_process(
        COMMAND unzip -o ${CMAKE_CURRENT_SOURCE_DIR}/cmake/CMake-${version}-Modules-ExternalProject.zip -d ${CMAKE_CURRENT_BINARY_DIR}/cmake/Modules/ExternalProject
        RESULT_VARIABLE unzip_result
    )
    if(NOT unzip_result EQUAL 0)
        message(FATAL_ERROR "unzip of the ExternalProject helper modules failed (${unzip_result})")
    endif()

    set(ep_url "https://raw.githubusercontent.com/Kitware/CMake/${cmake_commit}/Modules/ExternalProject.cmake")
    set(ep_file "${CMAKE_CURRENT_BINARY_DIR}/cmake/Modules/ExternalProject.cmake")
    execute_process(
        COMMAND curl -fsSL --retry 5 --retry-delay 3 -o ${ep_file} ${ep_url}
        RESULT_VARIABLE curl_result
    )
    if(NOT curl_result EQUAL 0)
        message(FATAL_ERROR "Could not download ${ep_url} (${curl_result})")
    endif()
    file(SHA256 ${ep_file} ep_actual_sha256)
    if(NOT ep_actual_sha256 STREQUAL externalproject_sha256)
        message(FATAL_ERROR "ExternalProject.cmake sha256 mismatch: expected ${externalproject_sha256}, got ${ep_actual_sha256}")
    endif()

    execute_process(
        COMMAND patch -p1 -i ${CMAKE_CURRENT_SOURCE_DIR}/packages/cmake-0001-ExternalProject-changes.patch
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/cmake
        RESULT_VARIABLE patch_result
    )
    if(NOT patch_result EQUAL 0)
        message(FATAL_ERROR "patching ExternalProject.cmake failed (${patch_result})")
    endif()

    file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/cmake/Modules/setup_done "")
endif()

include(${CMAKE_CURRENT_BINARY_DIR}/cmake/Modules/ExternalProject.cmake)
