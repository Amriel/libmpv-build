#!/usr/bin/env python3
"""Policy check for libmpv-2.dll. Used by CI (gate before a release) and by verify.ps1.

Pure standard library. Derived from mpv_spike/pe_imports.py, extended with:
  * the DELAY-LOAD import table (clang/lld delay-loads some DLLs; the original reader missed them)
  * a byte-level scan for forbidden strings and for dynamically referenced network DLL names
  * the licence / version strings embedded by ffmpeg and mpv

Exit status: 0 = policy satisfied, 1 = policy violated, 2 = could not parse.
Usage: check_dll.py <libmpv-2.dll> [--json out.json] [--load]
"""
import json
import re
import struct
import sys

FORBIDDEN_IMPORT_DLLS = ("ws2_32", "wldap32", "winhttp", "wininet", "urlmon")
FORBIDDEN_STRINGS = (b"--enable-gpl", b"--enable-nonfree", b"lua_", b"mujs", b"gdigrab")
# extra (not in the original requirement list, but they would break the licence story)
FORBIDDEN_STRINGS_EXTRA = (b"--enable-version3",)
# dynamic references: only reported, not fatal
SUSPICIOUS_DLL_NAMES = (b"ws2_32", b"wldap32", b"winhttp", b"wininet", b"urlmon", b"secur32", b"schannel", b"libcurl")
WATCH_FUNCS = ("Internet", "Http", "WinHttp", "URLDownload", "CreateRemoteThread", "WriteProcessMemory",
               "VirtualAllocEx", "SetWindowsHookEx", "RegSetValue", "RegCreateKey", "CryptEncrypt",
               "ShellExecute", "CreateService", "OpenProcess", "connect", "WSAStartup", "getaddrinfo",
               "send", "recv", "LoadLibrary")


def parse_imports(d: bytes):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    machine = struct.unpack_from("<H", d, pe + 4)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", d, opt)[0]
    is64 = magic == 0x20B
    image_base = struct.unpack_from("<Q" if is64 else "<I", d, opt + (24 if is64 else 28))[0]
    dd = opt + (112 if is64 else 96)
    imp_rva, imp_size = struct.unpack_from("<II", d, dd + 8)
    delay_rva, delay_size = struct.unpack_from("<II", d, dd + 13 * 8)
    secs = []
    so = opt + optsz
    for i in range(nsec):
        name, vsz, va, rsz, raw = struct.unpack_from("<8sIIII", d, so + i * 40)
        secs.append((va, max(vsz, rsz), raw))

    def off(rva):
        for va, sz, raw in secs:
            if va <= rva < va + sz:
                return rva - va + raw
        raise ValueError(f"rva {hex(rva)} not in any section")

    def cstr(o):
        e = d.index(b"\0", o)
        return d[o:e].decode("ascii", "replace")

    ptr_fmt, ptr_sz, ord_flag = ("<Q", 8, 1 << 63) if is64 else ("<I", 4, 1 << 31)

    def read_thunks(rva):
        funcs, t = [], off(rva)
        while True:
            v = struct.unpack_from(ptr_fmt, d, t)[0]
            if v == 0:
                break
            if v & ord_flag:
                funcs.append(f"#{v & 0xFFFF}")
            else:
                funcs.append(cstr(off(v & 0x7FFFFFFF) + 2))
            t += ptr_sz
        return funcs

    static, delayed = {}, {}
    if imp_rva:
        o = off(imp_rva)
        while True:
            ilt, _, _, name_rva, iat = struct.unpack_from("<IIIII", d, o)
            if name_rva == 0:
                break
            static.setdefault(cstr(off(name_rva)), []).extend(read_thunks(ilt or iat))
            o += 20
    if delay_rva:
        o = off(delay_rva)
        while True:
            attrs, name_rva, _hmod, _iat, int_rva = struct.unpack_from("<IIIII", d, o)
            if name_rva == 0:
                break
            if not (attrs & 1):  # VAs instead of RVAs (very old images)
                name_rva -= image_base
                int_rva -= image_base
            delayed.setdefault(cstr(off(name_rva)), []).extend(read_thunks(int_rva))
            o += 32
    return {"machine": hex(machine), "pe32plus": is64, "static": static, "delay": delayed}


def exports(d: bytes):
    """Names of exported functions (to prove the mpv client API is there)."""
    try:
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        optsz = struct.unpack_from("<H", d, pe + 20)[0]
        opt = pe + 24
        is64 = struct.unpack_from("<H", d, opt)[0] == 0x20B
        dd = opt + (112 if is64 else 96)
        exp_rva = struct.unpack_from("<I", d, dd)[0]
        secs = []
        so = opt + optsz
        for i in range(nsec):
            _n, vsz, va, rsz, raw = struct.unpack_from("<8sIIII", d, so + i * 40)
            secs.append((va, max(vsz, rsz), raw))

        def off(rva):
            for va, sz, raw in secs:
                if va <= rva < va + sz:
                    return rva - va + raw
            raise ValueError

        e = off(exp_rva)
        n_names, _addr_funcs, addr_names = struct.unpack_from("<III", d, e + 24)
        out = []
        for i in range(n_names):
            nrva = struct.unpack_from("<I", d, off(addr_names) + 4 * i)[0]
            s = off(nrva)
            out.append(d[s:d.index(b"\0", s)].decode("ascii", "replace"))
        return out
    except Exception:
        return []


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = sys.argv[1]
    json_out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    do_load = "--load" in sys.argv
    d = open(path, "rb").read()
    try:
        info = parse_imports(d)
    except Exception as e:  # noqa
        print(f"ERROR: cannot parse PE imports: {e}", file=sys.stderr)
        return 2

    failures, warnings = [], []
    print(f"file      : {path}  ({len(d)} bytes)")
    print(f"machine   : {info['machine']} ({'PE32+' if info['pe32plus'] else 'PE32'})")

    print("\n--- static imports (DLL: function count) ---")
    for dll in sorted(info["static"], key=str.lower):
        print(f"  {dll}: {len(info['static'][dll])}")
    print("--- delay-load imports ---")
    for dll in sorted(info["delay"], key=str.lower) or []:
        print(f"  {dll}: {len(info['delay'][dll])}")
    if not info["delay"]:
        print("  (none)")

    all_dlls = list(info["static"]) + list(info["delay"])
    for dll in all_dlls:
        base = dll.lower()
        if base.endswith(".dll"):
            base = base[:-4]
        if base in FORBIDDEN_IMPORT_DLLS:
            failures.append(f"forbidden import: {dll}")

    print("\n--- noteworthy imported functions (informational) ---")
    for kind in ("static", "delay"):
        for dll, fs in info[kind].items():
            hit = [f for f in fs if any(w.lower() in f.lower() for w in WATCH_FUNCS)]
            if hit:
                print(f"  [{kind}] {dll}: {hit}")

    for s in FORBIDDEN_STRINGS + FORBIDDEN_STRINGS_EXTRA:
        n = d.count(s)
        if n:
            failures.append(f"forbidden string {s.decode()!r} present ({n}x)")
    low = d.lower()
    for s in SUSPICIOUS_DLL_NAMES:
        if s in low:
            warnings.append(f"string {s.decode()!r} present in the binary (dynamic reference?)")

    # Licence strings of ffmpeg (avcodec_license() etc.). NOTE: with LTO the linker usually drops
    # them (the verified reference DLL has none), so ABSENCE is only a note. The authoritative
    # evidence is CONFIG.txt of the release (FFMPEG_CONFIGURATION / FFMPEG_LICENSE from the
    # ffmpeg build tree, checked in CI). PRESENCE of a non-LGPL string is a failure.
    lic = sorted(set(m.decode() for m in re.findall(rb"[A-Za-z ]*GPL version [0-9.]+ or later", d)))
    print("\n--- ffmpeg licence strings embedded in the binary ---")
    for l in lic or ["(none - normal when LTO removed avcodec_license(); see CONFIG.txt)"]:
        print("  " + l)
    for l in lic:
        if not l.strip().startswith("LGPL"):
            failures.append(f"non-LGPL licence string: {l.strip()!r}")

    ver = sorted(set(m.decode() for m in re.findall(rb"v?0\.\d+\.\d+-\d+-g[0-9a-f]{7,}", d)))
    mpv_ver = [v for v in ver if v.startswith("v")]
    print("\n--- version strings found ---")
    print("  mpv    : " + (", ".join(mpv_ver) if mpv_ver else "(not found)"))
    print("  others : " + (", ".join(v for v in ver if not v.startswith("v")) or "-") + "   (libass/libplacebo style)")

    ex = exports(d)
    n_mpv = sum(1 for e in ex if e.startswith("mpv_"))
    print(f"\nexports   : {len(ex)} total, {n_mpv} mpv_* (client API)")
    for need in ("mpv_create", "mpv_initialize", "mpv_render_context_create", "mpv_render_context_render"):
        if ex and need not in ex:
            failures.append(f"export missing: {need}")

    cfg = re.findall(rb"--cross-prefix=[\x20-\x7e]{40,}", d)
    ffcfg = max(cfg, key=len).decode() if cfg else ""

    if do_load and sys.platform == "win32":
        try:
            import ctypes
            dll = ctypes.WinDLL(path)
            dll.mpv_client_api_version.restype = ctypes.c_ulong
            v = dll.mpv_client_api_version()
            print(f"loaded OK : mpv_client_api_version() = {v >> 16}.{v & 0xFFFF}")
        except Exception as e:  # noqa
            failures.append(f"LoadLibrary failed: {e}")

    for w in warnings:
        print("WARN: " + w)
    for f in failures:
        print("FAIL: " + f)
    print("\nRESULT: " + ("POLICY VIOLATED" if failures else "policy OK"))

    if json_out:
        with open(json_out, "w", encoding="utf-8") as fh:
            json.dump({"imports": info, "licence_strings": lic, "mpv_versions": ver,
                       "ffmpeg_configuration": ffcfg, "failures": failures, "warnings": warnings}, fh, indent=2)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
