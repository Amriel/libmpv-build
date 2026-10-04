# libmpv-build overlay: packages/ffmpeg.cmake
#
# FFmpeg configured as an LGPL-2.1+, local-files-only, whitelist build.
# Philosophy: --disable-everything, then enable ONLY what a video/image-sequence reviewer needs.
# Anything not listed here cannot be reached at runtime, no matter what a media file asks for.
#
# configure semantics we rely on (checked against FFmpeg f1a000d41 `configure`):
#   * --enable-<component>=a,b,c  takes a comma list of names / shell globs; a name that matches
#     nothing only prints "Option ... did not match anything" (it does NOT abort), so always grep
#     ffbuild/config.log / the configure output for that message when changing the lists.
#   * --disable-autodetect also covers the hwaccel libs (d3d11va, dxva2, ffnvcodec, cuda, nvdec),
#     so those are enabled explicitly below.
#   * --disable-network skips the whole winsock probe => no ws2_32 link.
#
# Argument quoting: the recipe runs configure through `exec` (`eval $*`), so any value that
# contains a glob character is wrapped in '...' to survive one round of shell parsing.

# ---- decoders --------------------------------------------------------------------------------
set(ffmpeg_video_decoders
    # camera / delivery codecs
    h264 hevc av1 libdav1d vp8 vp9 vp6 vp6a vp6f vp7 mpeg1video mpeg2video mpeg4
    msmpeg4v1 msmpeg4v2 msmpeg4v3 h263 h263i h263p vc1 wmv1 wmv2 wmv3 theora flv svq1 svq3
    rv10 rv20 rv30 rv40 cinepak dvvideo
    # production / intermediate codecs
    prores prores_raw dnxhd cfhd ffv1 ffvhuff huffyuv utvideo qtrle magicyuv hap lagarith
    apv aic dxv cllc mjpeg mjpegb jpegls jpeg2000
    # raw / uncompressed
    rawvideo v210 v210x r210 r10k avrp avui y41p yuv4
    # still images / image-sequence frames
    png apng exr dpx tiff bmp targa gif webp pbm pgm pgmyuv ppm pam pfm phm sgi pcx qoi hdr
    psd sunrast xbm xwd dds
)
set(ffmpeg_audio_decoders
    aac aac_latm mp1 mp1float mp2 mp2float mp3 mp3float mp3adu mp3adufloat
    ac3 eac3 truehd mlp dca flac opus vorbis alac wmav1 wmav2 wmapro wmalossless
    ape wavpack tta tak shorten amrnb amrwb dst cook sipr qcelp nellymoser
    "pcm_*" "adpcm_*" "dsd_*" "atrac*" "gsm*" "ra_*"
)
set(ffmpeg_subtitle_decoders
    ass ssa subrip srt webvtt movtext text dvdsub pgssub dvbsub
)
list(APPEND ffmpeg_decoders ${ffmpeg_video_decoders} ${ffmpeg_audio_decoders} ${ffmpeg_subtitle_decoders})
list(JOIN ffmpeg_decoders "," ffmpeg_decoders_arg)

# ---- demuxers (container formats + image sequences) --------------------------------------------
set(ffmpeg_demuxers
    mov matroska mxf avi mpegts mpegps mpegvideo
    image2 image2pipe "image_*_pipe"
    wav w64 flac mp3 ogg aac ac3 eac3 dts dtshd truehd mlp flv gif caf aiff amr ape asf au dv dsf
    iff ivf m4v h264 hevc av1 obu yuv4mpegpipe rawvideo dnxhd mjpeg vc1 tak tta voc wv xwma rm
    # external text subtitles
    ass srt webvtt microdvd sami subviewer subviewer1 mpl2 vplayer realtext jacosub pjs stl aqtitle lrc
)
list(JOIN ffmpeg_demuxers "," ffmpeg_demuxers_arg)

# ---- hwaccels (decode only; ffmpeg hwaccel names are <codec>_<api>) -----------------------------
#  d3d11va / d3d11va2 / dxva2 = Microsoft DirectX Video Acceleration, nvdec = NVIDIA via ffnvcodec
set(ffmpeg_hwaccels "*_d3d11va" "*_d3d11va2" "*_dxva2" "*_nvdec")
list(JOIN ffmpeg_hwaccels "," ffmpeg_hwaccels_arg)

ExternalProject_Add(ffmpeg
    DEPENDS
        nvcodec-headers
        zlib
        dav1d
    GIT_REPOSITORY https://github.com/FFmpeg/FFmpeg.git
    SOURCE_DIR ${SOURCE_LOCATION}
    GIT_CLONE_FLAGS "--filter=tree:0"
    UPDATE_COMMAND ""
    CONFIGURE_COMMAND ${EXEC} CONF=1 <SOURCE_DIR>/configure
        --cross-prefix=${TARGET_ARCH}-
        --prefix=${MINGW_INSTALL_PREFIX}
        --arch=${TARGET_CPU}
        --target-os=mingw32
        --pkg-config-flags=--static
        --enable-cross-compile
        --enable-runtime-cpudetect
        # --- licence: LGPL-2.1-or-later. Deliberately NO --enable-gpl / --enable-version3 / --enable-nonfree.
        # --- reachability: nothing is on unless listed.
        --disable-autodetect
        --disable-everything
        --disable-network
        --disable-programs
        --disable-doc
        --disable-avdevice
        --disable-postproc
        # --- the only external libraries
        --enable-zlib
        --enable-libdav1d
        # --- hardware decode (explicit because --disable-autodetect)
        --enable-d3d11va
        --enable-dxva2
        --enable-ffnvcodec
        --enable-cuda
        --enable-nvdec
        # --- components
        "--enable-decoder='${ffmpeg_decoders_arg}'"
        "--enable-demuxer='${ffmpeg_demuxers_arg}'"
        "--enable-hwaccel='${ffmpeg_hwaccels_arg}'"
        --enable-parsers
        --enable-bsfs
        --enable-filters
        # mpv's `screenshot` writes png/jpeg through libavcodec encoders (no muxer involved).
        --enable-encoder=png,mjpeg
        # The ONLY protocol. No http/tcp/udp/rtp/tls/ftp/pipe/fd/... are compiled in.
        --enable-protocol=file
        ${ffmpeg_lto}
        --extra-cflags='-Wno-error=int-conversion'
    BUILD_COMMAND ${MAKE}
    INSTALL_COMMAND ${MAKE} install
    LOG_DOWNLOAD 1 LOG_UPDATE 1 LOG_CONFIGURE 1 LOG_BUILD 1 LOG_INSTALL 1
)

# The final DLL does NOT contain FFMPEG_CONFIGURATION / FFMPEG_LICENSE (LTO drops
# avcodec_configuration()/avcodec_license(); the verified reference DLL has neither). So we keep
# the evidence from the ffmpeg build tree, before cleanup() deletes it:
#   config.h            -> FFMPEG_CONFIGURATION, FFMPEG_LICENSE
#   config_components.h -> the exact list of enabled decoders/demuxers/protocols/...
#   ffbuild/config.log  -> full configure log (all "did not match anything" warnings)
set(LIBMPV_META ${CMAKE_BINARY_DIR}/libmpv-meta/ffmpeg)
ExternalProject_Add_Step(ffmpeg save-config
    DEPENDEES install
    COMMAND ${CMAKE_COMMAND} -E make_directory ${LIBMPV_META}
    COMMAND ${CMAKE_COMMAND} -E copy <BINARY_DIR>/config.h              ${LIBMPV_META}/config.h
    COMMAND ${CMAKE_COMMAND} -E copy <BINARY_DIR>/config_components.h   ${LIBMPV_META}/config_components.h
    COMMAND ${CMAKE_COMMAND} -E copy <BINARY_DIR>/ffbuild/config.log    ${LIBMPV_META}/config.log
    COMMENT "Saving ffmpeg configuration evidence"
    LOG 1
)

force_rebuild_git(ffmpeg)
cleanup(ffmpeg save-config)
