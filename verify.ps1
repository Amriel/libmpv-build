<#
.SYNOPSIS
  Verify a downloaded libmpv-2.dll from a release of this repository (run locally on Windows).

.DESCRIPTION
  1. sha256 of the DLL against libmpv-2.dll.sha256 (or -ExpectedSha256)
  2. PE import table (static + delay-load) and byte scan via tools\check_dll.py (pure Python, stdlib only):
       FAIL on imports of ws2_32 / wldap32 / winhttp / wininet / urlmon
       FAIL on the strings --enable-gpl, --enable-nonfree, lua_, mujs, gdigrab (and --enable-version3)
       FAIL if an ffmpeg licence string other than LGPL is embedded
  3. loads the DLL (ctypes) and prints the mpv client API version, and prints the mpv version string
  4. if CONFIG.txt / SOURCES.txt are next to the DLL: checks that CONFIG.txt says LGPL and has no gpl/version3/nonfree
  Exit code 0 = everything OK, 1 = a check failed, 2 = could not run.

.EXAMPLE
  .\verify.ps1 -Dll C:\Downloads\libmpv-2.dll
#>
[CmdletBinding()]
param(
    [string]$Dll = (Join-Path (Get-Location) 'libmpv-2.dll'),
    [string]$ExpectedSha256 = '',
    [switch]$NoLoad
)

$ErrorActionPreference = 'Stop'
$failed = $false
function Fail([string]$m) { Write-Host ("FAIL: " + $m) -ForegroundColor Red; $script:failed = $true }
function Ok([string]$m)   { Write-Host ("OK:   " + $m) -ForegroundColor Green }

if (-not (Test-Path -LiteralPath $Dll)) { Write-Host "DLL not found: $Dll" -ForegroundColor Red; exit 2 }
$Dll = (Resolve-Path -LiteralPath $Dll).Path
$dir = Split-Path -Parent $Dll
Write-Host "== verify.ps1: $Dll"

# ---- 1. sha256 -------------------------------------------------------------------------------
$actual = (Get-FileHash -LiteralPath $Dll -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "sha256 (actual)  : $actual"
$expected = $ExpectedSha256.Trim().ToLowerInvariant()
if (-not $expected) {
    $shaFile = Join-Path $dir ((Split-Path -Leaf $Dll) + '.sha256')
    if (Test-Path -LiteralPath $shaFile) {
        $line = (Get-Content -LiteralPath $shaFile | Where-Object { $_ -match '^[0-9a-fA-F]{64}' } | Select-Object -First 1)
        if ($line) { $expected = $line.Substring(0, 64).ToLowerInvariant() }
    }
}
if ($expected) {
    Write-Host "sha256 (expected): $expected"
    if ($actual -eq $expected) { Ok 'sha256 matches' } else { Fail 'sha256 does NOT match' }
} else {
    Write-Host "WARN: no .sha256 file next to the DLL and no -ExpectedSha256 given; hash not compared" -ForegroundColor Yellow
}

# ---- 2/3. imports, strings, version via tools\check_dll.py ------------------------------------
$checker = Join-Path $PSScriptRoot 'tools\check_dll.py'
if (-not (Test-Path -LiteralPath $checker)) { Write-Host "tools\check_dll.py not found next to verify.ps1" -ForegroundColor Red; exit 2 }
$py = $null
foreach ($c in @('python', 'py')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
}
if (-not $py) { Write-Host "Python 3 not found in PATH (needed for the PE reader)" -ForegroundColor Red; exit 2 }

$argsList = @($checker, $Dll)
if (-not $NoLoad) { $argsList += '--load' }
Write-Host ""
& $py @argsList
$rc = $LASTEXITCODE
if ($rc -eq 0) { Ok 'imports / strings / licence policy' }
elseif ($rc -eq 1) { Fail 'policy violated (see FAIL lines above)' }
else { Fail "check_dll.py could not parse the file (exit $rc)"; }

# ---- 4. release metadata next to the DLL -------------------------------------------------------
$cfg = Join-Path $dir 'CONFIG.txt'
if (Test-Path -LiteralPath $cfg) {
    $txt = Get-Content -LiteralPath $cfg -Raw
    if ($txt -match 'FFMPEG_LICENSE\s*:\s*LGPL version 2\.1 or later') { Ok 'CONFIG.txt: ffmpeg is LGPL version 2.1 or later' } else { Fail 'CONFIG.txt: FFMPEG_LICENSE is not "LGPL version 2.1 or later"' }
    foreach ($bad in @('--enable-gpl', '--enable-version3', '--enable-nonfree')) {
        if ($txt.Contains($bad)) { Fail "CONFIG.txt: ffmpeg configured with $bad" }
    }
    if ($txt -match '(?m)^protocols\s*\[1\]:\s*file\s*$') { Ok 'CONFIG.txt: only the "file" protocol is compiled into ffmpeg' } else { Fail 'CONFIG.txt: protocol list is not exactly [file]' }
    if ($txt -match '-Dgpl=false') { Ok 'CONFIG.txt: mpv built with -Dgpl=false' } else { Fail 'CONFIG.txt: -Dgpl=false not found' }
} else {
    Write-Host "WARN: CONFIG.txt not next to the DLL - licence/protocol evidence not checked" -ForegroundColor Yellow
}
if (-not (Test-Path -LiteralPath (Join-Path $dir 'SOURCES.txt'))) {
    Write-Host "WARN: SOURCES.txt not next to the DLL (needed for the LGPL source offer)" -ForegroundColor Yellow
}

Write-Host ""
if ($failed) { Write-Host "RESULT: FAILED" -ForegroundColor Red; exit 1 }
Write-Host "RESULT: ALL CHECKS PASSED" -ForegroundColor Green
exit 0
