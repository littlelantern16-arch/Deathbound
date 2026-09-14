# Deathbound LTX local test — RTX 3050 target machine.
# Diagnostic preparation ONLY, then the smallest REAL generation via the
# existing provider (python -m automation.video.smoke_test). No fake success:
# every check below must pass before the GPU is touched, and the smoke test
# itself classifies and reports any failure.
# Idempotent: running twice never deletes or redownloads anything.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Fail($message) {
    Write-Host ""
    Write-Host "TEST BLOCKED: $message" -ForegroundColor Red
    exit 1
}
function Ok($message) { Write-Host "  [OK] $message" -ForegroundColor Green }
function Info($message) { Write-Host "  --   $message" }

Write-Host "=== DEATHBOUND LTX LOCAL TEST (RTX 3050 target) ==="

# Repo location: scripts/ sits one level below the repo root.
$repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$repo\automation\video\ltx_provider.py")) {
    Fail "repo layout unexpected: automation/video not found under $repo"
}
$env:DEATHBOUND_ROOT = $repo

# Isolated venv created by setup_ltx_windows.ps1 (outside the repo).
$envDir = "D:\Deathbound\tools\ltx-env"
$LtxPy = "$envDir\Scripts\python.exe"
if (-not (Test-Path $LtxPy)) {
    Fail "LTX venv missing at $envDir. Run scripts\setup_ltx_windows.ps1 first."
}
Ok "venv: $envDir"

# ---------------------------------------------------------------- T1: GPU + VRAM
$gpuLine = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader) 2>&1
if (-not $gpuLine -or $gpuLine -match "error") { Fail "nvidia-smi failed: $gpuLine" }
Ok "GPU: $gpuLine"
$vramMb = [int](($gpuLine -split ",")[1] -replace "[^0-9]", "")
if ($vramMb -lt 3500) { Fail "VRAM ${vramMb} MB below the 3500 MB minimum for the smallest test." }
Ok ("VRAM: {0} MB" -f $vramMb)

# ---------------------------------------------------------------- T2: PyTorch CUDA inside the venv
$torchCheck = & $LtxPy -c "import torch; v=torch.__version__; ok=torch.cuda.is_available(); dev=torch.cuda.get_device_name(0) if ok else '-'; total=torch.cuda.get_device_properties(0).total_memory/1024**3 if ok else 0; print(f'torch={v} cuda_ok={ok} device={dev} vram={total:.1f}GB')" 2>&1
if ("$torchCheck" -notmatch "cuda_ok=True") {
    Fail "PyTorch CUDA unavailable inside the venv: $torchCheck. Re-run scripts\setup_ltx_windows.ps1."
}
Ok "PyTorch: $torchCheck"

# ---------------------------------------------------------------- T3: LTX imports (diffusers pipelines)
$ltxImport = & $LtxPy -c "import diffusers; from diffusers import LTXPipeline, LTXConditionPipeline; print(f'LTX_IMPORT_OK diffusers={diffusers.__version__}')" 2>&1
if ("$ltxImport" -notmatch "LTX_IMPORT_OK") { Fail "LTX diffusers pipelines not importable: $ltxImport" }
Ok "$ltxImport"

# ---------------------------------------------------------------- T4: Model availability (local scan, no download)
$modelCheck = & $LtxPy -c "import sys; sys.path.insert(0, r'$repo'); from automation.video.diagnostics import model_present; m = model_present(); print('MODEL_PRESENT=' + str(m['present']) + ' size_gb=' + str(m['size_gb']))" 2>&1
if ("$modelCheck" -notmatch "MODEL_PRESENT=True") {
    Info "LTX weights not found in the HF cache yet ($modelCheck)."
    Info "First generation will download ~13-15 GB into D:\Deathbound\cache\huggingface (one-time)."
} else {
    Ok "LTX weights present: $modelCheck"
}

# ---------------------------------------------------------------- T5: Full machine diagnostics gate
$env:HF_HOME = "D:\Deathbound\cache\huggingface"
& $LtxPy -c "import sys; sys.path.insert(0, r'$repo'); from automation.video.diagnostics import run_diagnostics; import json; r = run_diagnostics(); print(json.dumps(r, indent=2, default=str)); sys.exit(0 if r['ready_for_smoke_test'] else 1)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Fail "machine diagnostics not ready (see blocking errors above). Fix them before generating."
}
Ok "machine diagnostics: ready"

# ---------------------------------------------------------------- T6: Smallest REAL generation + validation
# smoke_test performs: diagnostics gate -> provider.generate() -> ffprobe
# validation -> real final-frame extraction -> timing/VRAM report.
Write-Host ""
Write-Host "=== SMOKE TEST: one real 2s 512x320 clip (no fake success) ==="
& $LtxPy -m automation.video.smoke_test --shot-id LTX-SMOKE-001
exit $LASTEXITCODE
