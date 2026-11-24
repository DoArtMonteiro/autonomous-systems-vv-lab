# Builds V&V Lab Studio and its Windows installer from a repository checkout.
#
#   powershell -ExecutionPolicy Bypass -File desktop\build.ps1 -Release   # release build + NSIS installer, identifier org.vvlab.studio
#   powershell -ExecutionPolicy Bypass -File desktop\build.ps1            # development build, no installer, identifier org.vvlab.devstudio
#   powershell -ExecutionPolicy Bypass -File desktop\build.ps1 -StageOnly # build and stage the domain hosts only
#
# Identity. tauri.conf.json carries the development identifier; only tauri.release.conf.json, applied
# by -Release, carries the identifier of the installed application, so a build made any other way can
# never share the installed profile (docs/incidents/2026-11-23-webview2-profile.md). The script checks
# the merged identifier before building and the identifier compiled into vv-studio.exe after.
#
# Build-time requirements: the Rust toolchain pinned in rust-toolchain.toml and Node.js (for the
# Tauri CLI in desktop/studio/node_modules). The first bundle downloads NSIS once. The installed
# application needs none of these.

param([switch]$StageOnly, [switch]$Release)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $repo "desktop"
$stage = Join-Path $desktop "target\release\domains"

$DevIdentifier = "org.vvlab.devstudio"
$ReleaseIdentifier = "org.vvlab.studio"
$studio = Join-Path $desktop "studio"
$baseConfig = Join-Path $studio "tauri.conf.json"
$releaseConfig = Join-Path $studio "tauri.release.conf.json"

function Step($text) { Write-Host "==> $text" }
function Get-ConfigValue($path, $name) {
    $json = Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json
    return $json.$name
}
# Identifiers that appear, as UTF-8, in a compiled executable (Tauri compiles the identifier in).
# org.vvlab.devstudio does not contain org.vvlab.studio, so the two cannot match each other.
function Get-EmbeddedIdentifiers($exe) {
    $text = [System.Text.Encoding]::GetEncoding(28591).GetString([System.IO.File]::ReadAllBytes($exe))
    return @($DevIdentifier, $ReleaseIdentifier | Where-Object { $text.Contains($_) })
}
$wanted = if ($Release) { $ReleaseIdentifier } else { $DevIdentifier }
function Run($exe, [string[]]$arguments, $cwd) {
    Push-Location $cwd
    # Native tools write progress to stderr; only the exit code decides failure.
    $ErrorActionPreference = "Continue"
    try {
        & $exe @arguments
        if ($LASTEXITCODE -ne 0) { throw "$exe $($arguments -join ' ') failed with exit code $LASTEXITCODE" }
    } finally { Pop-Location }
}

# The identity of this build, checked before anything is compiled. -Release: the overlay must name
# the installed application exactly. Any other build: the merged identifier must not.
$mergedIdentifier = Get-ConfigValue $baseConfig "identifier"
if ($Release) {
    $overlayIdentifier = Get-ConfigValue $releaseConfig "identifier"
    if ($overlayIdentifier) { $mergedIdentifier = $overlayIdentifier }
}
if ($mergedIdentifier -cne $wanted) { throw "identity check failed: the merged Tauri identifier is '$mergedIdentifier', expected '$wanted'" }
# An inherited TAURI_CONFIG would merge on top of both files.
if ($env:TAURI_CONFIG) { throw "TAURI_CONFIG is set in this environment; unset it, the build identity comes from the two config files only" }
Step "Build identity: $mergedIdentifier ($(if ($Release) { 'release' } else { 'development' }))"

Step "Ground-vehicle simulator (vv-lab, root package, bundled copy)"
# Built from desktop/ so desktop/.cargo/config.toml links the VC runtime statically, into its own
# target directory so the developer build in target/ is untouched. The sources are the same.
$vvlab = Join-Path $desktop "target\root-static\release\vv-lab.exe"
Run "cargo" @("build", "--release", "--bin", "vv-lab", "--manifest-path", (Join-Path $repo "Cargo.toml"), "--target-dir", (Join-Path $desktop "target\root-static")) $desktop

Step "Domain hosts (desktop workspace)"
Run "cargo" @("build", "--release", "-p", "vv-domain-rocket", "-p", "vv-domain-ascent", "-p", "vv-domain-ground", "-p", "vv-domain-reference") $desktop

Step "Staging domains into $stage"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
$domains = @(
    @{ id = "rocket-landing"; crate = "domain-rocket"; exe = "vv-domain-rocket.exe"; extra = @() },
    @{ id = "launch-ascent"; crate = "domain-ascent"; exe = "vv-domain-ascent.exe"; extra = @() },
    @{ id = "ground-vehicle"; crate = "domain-ground"; exe = "vv-domain-ground.exe"; extra = @($vvlab) },
    @{ id = "reference-oscillator"; crate = "domain-reference"; exe = "vv-domain-reference.exe"; extra = @() }
)
foreach ($d in $domains) {
    $dir = Join-Path $stage $d.id
    New-Item -ItemType Directory -Force $dir | Out-Null
    Copy-Item (Join-Path $desktop "$($d.crate)\domain.json") $dir
    Copy-Item (Join-Path $desktop "target\release\$($d.exe)") $dir
    foreach ($f in $d.extra) { Copy-Item $f $dir }
}
Get-ChildItem -Recurse $stage | Where-Object { -not $_.PSIsContainer } | ForEach-Object {
    Write-Host ("    {0,-60} {1,10:N0} bytes" -f $_.FullName.Substring($stage.Length + 1), $_.Length)
}
Step "Investigation engine (vv-exec) and bundled claims (M13 Discovery Lab)"
# Built from desktop/ so desktop/.cargo/config.toml links the VC runtime statically, into its own
# target directory. Studio runs it as a child process; it never links it.
$execTarget = Join-Path $desktop "target\exec-static"
Run "cargo" @("build", "--release", "--locked", "--bin", "vv-exec", "--manifest-path", (Join-Path $repo "exec\Cargo.toml"), "--target-dir", $execTarget) $desktop
$engines = Join-Path (Join-Path $desktop "target") "release/engines"
$discovery = Join-Path (Join-Path $desktop "target") "release/discovery"
foreach ($d in @($engines, $discovery)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
New-Item -ItemType Directory -Force $engines | Out-Null
Copy-Item (Join-Path (Join-Path $execTarget "release") "vv-exec.exe") $engines
# Claims name their base cases by relative path (../../cases/...), so the two folders keep the
# layout they have under exec/.
New-Item -ItemType Directory -Force $discovery | Out-Null
Copy-Item -Recurse (Join-Path $repo "exec\claims") (Join-Path $discovery "claims")
Copy-Item -Recurse (Join-Path $repo "exec\cases") (Join-Path $discovery "cases")
Get-ChildItem -Recurse $engines, $discovery | Where-Object { -not $_.PSIsContainer } | ForEach-Object {
    Write-Host ("    {0,-60} {1,10:N0} bytes" -f $_.FullName.Substring($desktop.Length + 1), $_.Length)
}
if ($StageOnly) { exit 0 }

if (-not (Test-Path (Join-Path $studio "node_modules\@tauri-apps\cli"))) {
    Run "npm" @("ci", "--no-audit", "--no-fund") $studio
}
# Called through node directly: the npm command shim breaks on paths that contain '&'.
$tauri = Join-Path $studio "node_modules\@tauri-apps\cli\tauri.js"
if ($Release) {
    Step "Tauri bundle (NSIS installer), release identity from tauri.release.conf.json"
    Run "node" @($tauri, "build", "--config", $releaseConfig) $studio
} else {
    Step "Tauri build, development identity, no installer"
    Run "node" @($tauri, "build", "--no-bundle") $studio
}
$studioExe = Join-Path $desktop "target\release\vv-studio.exe"
$embedded = @(Get-EmbeddedIdentifiers $studioExe)
Write-Host "    vv-studio.exe carries: $($embedded -join ', ')"
if ($embedded.Count -ne 1 -or $embedded[0] -cne $wanted) { throw "identity check failed: vv-studio.exe carries '$($embedded -join ', ')', expected only '$wanted'" }
if (-not $Release) { Step "Development build: $studioExe (no installer; use -Release for one)"; exit 0 }

$bundle = Join-Path $desktop "target\release\bundle\nsis"
Step "Installer:"
Get-ChildItem $bundle -Filter *.exe | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    Write-Host "    $($_.FullName)"
    Write-Host "    sha256 $hash"
}
