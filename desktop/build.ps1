# Builds V&V Lab Studio and its Windows installer from a repository checkout.
#
#   powershell -ExecutionPolicy Bypass -File desktop\build.ps1            # release build + NSIS installer
#   powershell -ExecutionPolicy Bypass -File desktop\build.ps1 -StageOnly # build and stage the domain hosts only
#
# Build-time requirements: the Rust toolchain pinned in rust-toolchain.toml and Node.js (for the
# Tauri CLI in desktop/studio/node_modules). The first bundle downloads NSIS once. The installed
# application needs none of these.

param([switch]$StageOnly)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $repo "desktop"
$stage = Join-Path $desktop "target\release\domains"

function Step($text) { Write-Host "==> $text" }
function Run($exe, [string[]]$arguments, $cwd) {
    Push-Location $cwd
    # Native tools write progress to stderr; only the exit code decides failure.
    $ErrorActionPreference = "Continue"
    try {
        & $exe @arguments
        if ($LASTEXITCODE -ne 0) { throw "$exe $($arguments -join ' ') failed with exit code $LASTEXITCODE" }
    } finally { Pop-Location }
}

Step "Ground-vehicle simulator (vv-lab, root package, bundled copy)"
# Built from desktop/ so desktop/.cargo/config.toml links the VC runtime statically, into its own
# target directory so the developer build in target/ is untouched. The sources are the same.
$vvlab = Join-Path $desktop "target\root-static\release\vv-lab.exe"
Run "cargo" @("build", "--release", "--bin", "vv-lab", "--manifest-path", (Join-Path $repo "Cargo.toml"), "--target-dir", (Join-Path $desktop "target\root-static")) $desktop

Step "Domain hosts (desktop workspace)"
Run "cargo" @("build", "--release", "-p", "vv-domain-rocket", "-p", "vv-domain-ground", "-p", "vv-domain-reference") $desktop

Step "Staging domains into $stage"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
$domains = @(
    @{ id = "rocket-landing"; crate = "domain-rocket"; exe = "vv-domain-rocket.exe"; extra = @() },
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
if ($StageOnly) { exit 0 }

Step "Tauri bundle (NSIS installer)"
$studio = Join-Path $desktop "studio"
if (-not (Test-Path (Join-Path $studio "node_modules\@tauri-apps\cli"))) {
    Run "npm" @("ci", "--no-audit", "--no-fund") $studio
}
# Called through node directly: the npm command shim breaks on paths that contain '&'.
Run "node" @((Join-Path $studio "node_modules\@tauri-apps\cli\tauri.js"), "build") $studio

$bundle = Join-Path $desktop "target\release\bundle\nsis"
Step "Installer:"
Get-ChildItem $bundle -Filter *.exe | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    Write-Host "    $($_.FullName)"
    Write-Host "    sha256 $hash"
}
