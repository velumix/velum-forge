<#
.SYNOPSIS
Velum Forge 1-command visual & geometric 10-view QA gate (CAD scripts, Blender scripts, .blend, GLB/FBX/OBJ/STL/STEP).

.EXAMPLE
.\engine\cad\run_qa.ps1 -Asset examples\mahi_mahi\build_mahi_mahi.py -Profile roblox -ForwardAxis "+Y"
.\engine\cad\run_qa.ps1 -Asset engine\cad\templates\cad_part_template.py -Profile render
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [Alias("Path", "File", "InputPath")]
    [string]$Asset,

    [string]$OutDir = "",
    [string]$Collection = "",
    [string[]]$Objects = @(),

    [ValidateSet("auto", "roblox", "game", "render", "print")]
    [string]$Profile = "auto",

    [ValidateSet("auto", "cycles", "workbench")]
    [string]$Renderer = "auto",

    [int]$MaxTris = -1,
    [switch]$HighPoly,
    [switch]$Fast,
    [string]$Ref = "",
    [switch]$OrthoGrid,
    [switch]$SnapshotIteration,
    [int]$Threads = 0,
    [ValidateSet("auto", "gpu", "optix", "cuda", "hip", "oneapi", "metal", "cpu")]
    [string]$Device = "auto",
    [switch]$UserAddons,
    [switch]$KeepTiles,
    [switch]$NoFailExit,

    [ValidateSet("auto", "blender", "cad")]
    [string]$Mode = "auto",

    [ValidateSet("-Y", "+Y")]
    [string]$ForwardAxis = "-Y"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$CadBridge = Join-Path $RepoRoot "engine\cad\cad_bridge.py"
$ComposeScript = Join-Path $RepoRoot "engine\cad\compose_sheet.py"
$QaPipeline = Join-Path $RepoRoot "engine\blender\qa_pipeline.py"

# Locate CAD/Studio Python venv (checks .venv, ~/.velum-forge/config.json, py.exe, and off-PATH installs)
$CfgFile = Join-Path $HOME ".velum-forge\config.json"
$SavedPy = $null
$SavedBlender = $null
if (Test-Path $CfgFile) {
    try {
        $CfgJson = Get-Content $CfgFile -Raw | ConvertFrom-Json
        if ($CfgJson.PSObject.Properties["python_exe"]) { $SavedPy = $CfgJson.python_exe }
        if ($CfgJson.PSObject.Properties["blender_exe"]) { $SavedBlender = $CfgJson.blender_exe }
    } catch {}
}

$CadPythonCandidates = @(
    @(
        (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
        (Join-Path $RepoRoot "engine\cad\.venv\Scripts\python.exe"),
        $SavedPy
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
)

$CadPython = if (@($CadPythonCandidates).Count -gt 0) { $CadPythonCandidates[0] } else { $null }
if (-not $CadPython) {
    throw "Velum Forge .venv not found. Run .\install.ps1 or double-click Setup-VelumForge.cmd first."
}

# Locate Blender 5.2+ via saved config, VELUM_BLENDER_EXE, or velum_forge.doctor 10-source scanner!
$BlenderExe = $null
foreach ($bc in @($env:VELUM_BLENDER_EXE, $SavedBlender)) {
    if ($bc -and (Test-Path -LiteralPath $bc)) { $BlenderExe = $bc; break }
}
if (-not $BlenderExe) {
    $probed = (& $CadPython -c "import sys; sys.path.insert(0, r'$RepoRoot'); from velum_forge.doctor import find_blender_exe; print(find_blender_exe() or '')" 2>$null | Select-Object -Last 1)
    if ($LASTEXITCODE -eq 0 -and $probed -and (Test-Path -LiteralPath $probed.Trim())) {
        $BlenderExe = $probed.Trim()
    }
}
if (-not $BlenderExe -or -not (Test-Path -LiteralPath $BlenderExe)) {
    throw "Blender executable not found. Run 'vforge set-blender ""D:\Path\To\blender.exe""' or click 'Locate blender.exe' in Velum Forge Studio."
}

$AssetPath = (Resolve-Path $Asset).Path
$AssetStem = [System.IO.Path]::GetFileNameWithoutExtension($AssetPath)
$Ext = [System.IO.Path]::GetExtension($AssetPath).ToLowerInvariant()

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path $RepoRoot (Join-Path ".qa-out" $AssetStem)
} elseif (-not [System.IO.Path]::IsPathRooted($OutDir)) {
    $OutDir = Join-Path (Get-Location).Path $OutDir
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path

function Invoke-NativeQuiet {
    param([string]$Exe, [string[]]$ArgList, [string]$LogFile = "")
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($LogFile) {
            & $Exe @ArgList 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath $LogFile -Encoding utf8
        } else {
            & $Exe @ArgList 2>&1 | ForEach-Object { "$_" } | Out-Host
        }
        return [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
}

$AssetParentDir = Split-Path $AssetPath -Parent
$AutoSpecPath = Join-Path $AssetParentDir "asset_spec.json"
$AutoRefDir = Join-Path $AssetParentDir "references"
$AutoReviewHist = Join-Path $AssetParentDir "reviews\review_history.json"

$SafeThreads = if ($Threads -gt 0) { $Threads } else { [Math]::Min(8, [Math]::Max(2, [int]([Environment]::ProcessorCount / 2))) }
$env:VELUM_BLENDER_THREADS = "$SafeThreads"
$env:VELUM_BAKE_THREADS = "$SafeThreads"
$env:VELUM_CYCLES_DEVICE = "$Device"
$env:OMP_NUM_THREADS = "$SafeThreads"
$env:TBB_NUM_THREADS = "$SafeThreads"
$env:OPENBLAS_NUM_THREADS = "$SafeThreads"
$env:MKL_NUM_THREADS = "$SafeThreads"

$BlenderArgs = @("-b")
if (-not $UserAddons) { $BlenderArgs += "--factory-startup" }
$BlenderArgs += @("-t", "$SafeThreads")
$PipelineArgs = @("--out-dir", $OutDir, "--profile", $Profile, "--max-tris", "$MaxTris", "--renderer", $Renderer, "--asset-name", $AssetStem, "--forward-axis", $ForwardAxis)
if ($HighPoly) { $PipelineArgs += "--high-poly" }
if ($Fast) { $PipelineArgs += "--fast" }
if ($OrthoGrid) { $PipelineArgs += "--ortho-grid" }
if (Test-Path -LiteralPath $AutoSpecPath) { $PipelineArgs += @("--spec", $AutoSpecPath) }
if (-not [string]::IsNullOrWhiteSpace($Collection)) { $PipelineArgs += @("--collection", $Collection) }
if (@($Objects).Count -gt 0) { $PipelineArgs += "--objects"; $PipelineArgs += $Objects }

if ($Ext -eq ".blend") {
    $BlenderArgs += @($AssetPath, "--python-exit-code", "1", "-P", $QaPipeline, "--") + $PipelineArgs
} elseif ($Ext -in @(".step", ".stp")) {
    $ConvertedGlb = Join-Path $OutDir "_converted.glb"
    Write-Host "[vforge-qa] Converting STEP -> GLB via cad_bridge..." -ForegroundColor Cyan
    $ec = Invoke-NativeQuiet $CadPython @($CadBridge, "step-to-glb", $AssetPath, $ConvertedGlb)
    if ($ec -ne 0) { throw "STEP conversion failed for $AssetPath" }
    $PipelineArgs = @("--input", $ConvertedGlb) + $PipelineArgs
    $BlenderArgs += @("--python-exit-code", "1", "-P", $QaPipeline, "--") + $PipelineArgs
} elseif ($Ext -eq ".py") {
    $RunAsCad = $false
    if ($Mode -eq "cad") { $RunAsCad = $true }
    elseif ($Mode -eq "auto") {
        $RawSrc = Get-Content -Raw -Path $AssetPath
        if ($RawSrc -match "\bbuild123d\b" -and $RawSrc -notmatch "\bbpy\b") { $RunAsCad = $true }
    }
    if ($RunAsCad) {
        $CadBuildDir = Join-Path $OutDir "_cad_build"
        New-Item -ItemType Directory -Force -Path $CadBuildDir | Out-Null
        Write-Host "[vforge-qa] Running build123d CAD script..." -ForegroundColor Cyan
        $ec = Invoke-NativeQuiet $CadPython @($AssetPath, "--out-dir", $CadBuildDir)
        if ($ec -ne 0) { throw "CAD script failed: $AssetPath" }
        $NewestGlb = Get-ChildItem -Path $CadBuildDir -Filter "*.glb" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $NewestGlb) { throw "CAD script produced no .glb output in $CadBuildDir" }
        $PipelineArgs = @("--input", $NewestGlb.FullName) + $PipelineArgs
        $BlenderArgs += @("--python-exit-code", "1", "-P", $QaPipeline, "--") + $PipelineArgs
    } else {
        $PipelineArgs = @("--input", $AssetPath) + $PipelineArgs
        $BlenderArgs += @("--python-exit-code", "1", "-P", $QaPipeline, "--") + $PipelineArgs
    }
} else {
    $PipelineArgs = @("--input", $AssetPath) + $PipelineArgs
    $BlenderArgs += @("--python-exit-code", "1", "-P", $QaPipeline, "--") + $PipelineArgs
}

Write-Host "[vforge-qa] Running headless Blender 5.2+ QA & multi-angle renders..." -ForegroundColor Cyan
$BlenderLog = Join-Path $OutDir "blender_qa.log"
$ecBlender = Invoke-NativeQuiet $BlenderExe $BlenderArgs $BlenderLog
if ($ecBlender -ne 0) {
    Get-Content $BlenderLog -Tail 40
    throw "Blender QA pipeline failed (exit $ecBlender). Full log: $BlenderLog"
}

$QaJson = Join-Path $OutDir "qa_report.json"
$ManifestJson = Join-Path $OutDir "render_manifest.json"
$OutMaterial = Join-Path $OutDir "contact_sheet_material.png"
$OutDiagnostic = Join-Path $OutDir "contact_sheet_diagnostic.png"
$OutRef = Join-Path $OutDir "ref_comparison.png"

$ComposeArgs = @(
    $ComposeScript,
    "--manifest", $ManifestJson,
    "--qa-json", $QaJson,
    "--out-material", $OutMaterial,
    "--out-diagnostic", $OutDiagnostic,
    "--out-ref", $OutRef
)
if ($OrthoGrid) { $ComposeArgs += "--ortho-grid" }
if (Test-Path -LiteralPath $AutoReviewHist) { $ComposeArgs += @("--review-history", $AutoReviewHist) }
if (-not [string]::IsNullOrWhiteSpace($Ref)) {
    $RefPath = (Resolve-Path $Ref).Path
    $ComposeArgs += @("--ref", $RefPath)
}
if (Test-Path -LiteralPath $AutoRefDir) {
    $ComposeArgs += @("--ref-dir", $AutoRefDir)
}

Write-Host "[vforge-qa] Composing labeled contact sheets & multi-angle reference comparisons..." -ForegroundColor Cyan
$ecCompose = Invoke-NativeQuiet $CadPython $ComposeArgs
if ($ecCompose -ne 0) { throw "Contact sheet composition failed." }

# Mirror QA contact sheets, qa_report.json, matched perspective cameras (+ ref_comparison.png) into <asset_dir>/renders/!
$AssetRendersDir = Join-Path $AssetParentDir "renders"
if (Test-Path -LiteralPath $AssetParentDir) {
    New-Item -ItemType Directory -Force -Path $AssetRendersDir | Out-Null
    Copy-Item -LiteralPath $OutMaterial -Destination (Join-Path $AssetRendersDir "qa_contact_material.png") -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath $OutDiagnostic -Destination (Join-Path $AssetRendersDir "qa_contact_diagnostic.png") -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath $QaJson -Destination (Join-Path $AssetRendersDir "qa_report.json") -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $OutRef) {
        Copy-Item -LiteralPath $OutRef -Destination (Join-Path $AssetRendersDir "ref_comparison.png") -Force -ErrorAction SilentlyContinue
    }
    Get-ChildItem -Path $OutDir -Filter "tile_refcam_*.png" -ErrorAction SilentlyContinue | ForEach-Object {
        $dstName = $_.Name -replace "^tile_", ""
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $AssetRendersDir $dstName) -Force -ErrorAction SilentlyContinue
    }
}

if ($SnapshotIteration -and (Test-Path -LiteralPath $AssetParentDir)) {
    Write-Host "[vforge-qa] Archiving iteration render snapshot into reviews/..." -ForegroundColor Cyan
    $snapPy = "import sys, json; sys.path.insert(0, r'$RepoRoot'); from velum_forge.review import snapshot_iteration_renders; print(json.dumps(snapshot_iteration_renders(r'$AssetParentDir')))"
    Invoke-NativeQuiet $CadPython @("-c", $snapPy) | Out-Null
}

if (-not $KeepTiles) {
    Get-ChildItem -Path $OutDir -Filter "tile_*.png" -ErrorAction SilentlyContinue | Remove-Item -Force
    if (Test-Path $ManifestJson) { Remove-Item $ManifestJson -Force }
}

$Qa = Get-Content -Raw -Path $QaJson | ConvertFrom-Json
$PassFlag = [bool]$Qa.pass
$Badge = if ($PassFlag) { "PASS" } else { "FAIL" }
$Color = if ($PassFlag) { "Green" } else { "Red" }

Write-Host ""
Write-Host "=== Velum Forge Visual QA [$Badge] ===" -ForegroundColor $Color
Write-Host ("Asset:      {0} (profile={1}, renderer={2})" -f $Qa.asset_name, $Qa.profile, $Qa.renderer)
Write-Host ("Geometry:   {0} tris across {1} mesh(es) | ground_z={2} m" -f $Qa.total_tris, $Qa.object_count, $Qa.ground_z)
Write-Host ("Size (m):   {0} x {1} x {2}" -f $Qa.size_m[0], $Qa.size_m[1], $Qa.size_m[2])
Write-Host ("Studs(3/m): {0} x {1} x {2}" -f $Qa.size_studs_sclib[0], $Qa.size_studs_sclib[1], $Qa.size_studs_sclib[2])
Write-Host ("Material:   $OutMaterial")
Write-Host ("Diagnostic: $OutDiagnostic")
if (Test-Path $OutRef) { Write-Host ("Ref Sheet:  $OutRef") }
Write-Host ("Report:     $QaJson")

if (@($Qa.errors).Count -gt 0) {
    Write-Host "Errors:" -ForegroundColor Red
    foreach ($e in @($Qa.errors)) { Write-Host "  - $e" -ForegroundColor Red }
}
if (@($Qa.warnings).Count -gt 0) {
    Write-Host "Warnings:" -ForegroundColor Yellow
    foreach ($w in @($Qa.warnings)) { Write-Host "  - $w" -ForegroundColor Yellow }
}

if ((-not $PassFlag) -and (-not $NoFailExit)) { exit 1 }
exit 0
