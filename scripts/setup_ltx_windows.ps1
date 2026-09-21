# Deathbound LTX setup — RTX 3050 Windows target machine.
# Idempotent: safe to run repeatedly; skips completed work.
# Installs ONLY LTX dependencies. Never Blender, never ComfyUI, no paid APIs,
# no alternative video models.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Fail($message) {
    Write-Host ""
    Write-Host "SETUP BLOCKED: $message" -ForegroundColor Red
    exit 1
}
function Ok($message) { Write-Host "  [OK] $message" -ForegroundColor Green }
function Info($message) { Write-Host "  --   $message" }

Write-Host "=== DEATHBOUND LTX SETUP (RTX 3050 target) ==="

# ---------------------------------------------------------------- P1: Python 3.11
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Fail "python not found on PATH. Install Python 3.11.x first." }
$pyVersion = (& python --version) 2>&1
if ($pyVersion -notmatch "3\.11") {
    Fail "Python 3.11.x required, found: $pyVersion. Install Python 3.11 and put it first on PATH."
}
Ok "Python: $pyVersion"

# ---------------------------------------------------------------- P2: NVIDIA GPU + driver
$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $nvidiaSmi) {
    $smi = "C:\Windows\System32\nvidia-smi.exe"
    if (Test-Path $smi) { $nvidiaSmi = $smi } else { Fail "nvidia-smi not found. Install/repair the NVIDIA driver." }
}
$gpuLine = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader) 2>&1
if (-not $gpuLine -or $gpuLine -match "error") { Fail "nvidia-smi failed: $gpuLine" }
Ok "GPU: $gpuLine"
$vramGb = [double](($gpuLine -split ",")[1] -replace "[^0-9.]", "") / 1024
if ($vramGb -lt 3.5) { Fail "Insufficient VRAM: $vramGb GB (need >= 3.5 GB)." }
Ok ("VRAM: {0:N1} GB" -f $vramGb)

# ---------------------------------------------------------------- P3: FFmpeg
$ffmpeg = "D:\Deathbound\tools\ffmpeg\bin\ffmpeg.exe"
if (Test-Path $ffmpeg) {
    Ok "FFmpeg found at $ffmpeg"
    $env:DEATHBOUND_FFMPEG = $ffmpeg
    $env:DEATHBOUND_FFPROBE = "D:\Deathbound\tools\ffmpeg\bin\ffprobe.exe"
} elseif (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Ok "FFmpeg found on PATH"
} else {
    Fail "FFmpeg not found at D:\Deathbound\tools\ffmpeg and not on PATH."
}

# ---------------------------------------------------------------- P4: Disk space
$downloadDrive = "D:"
$freeGb = [math]::Round((Get-PSDrive D).Free / 1GB, 1)
if ($freeGb -lt 25) { Fail "Insufficient disk on ${downloadDrive}: $freeGb GB free (need >= 25 GB for env + weights)." }
Ok "Disk: $freeGb GB free on $downloadDrive"

# ---------------------------------------------------------------- P5: Isolated venv OUTSIDE the repo
$envDir = "D:\Deathbound\tools\ltx-env"
if (Test-Path "$envDir\Scripts\python.exe") {
    Ok "Existing LTX venv found at $envDir (idempotent reuse)"
} else {
    Info "Creating isolated venv at $envDir ..."
    python -m venv $envDir
    if ($LASTEXITCODE -ne 0) { Fail "venv creation failed." }
    Ok "Created $envDir"
}
$LtxPy = "$envDir\Scripts\python.exe"

# ---------------------------------------------------------------- P6: CUDA torch + deps (skip if present)
& $LtxPy -c "import torch" 2>$null
if ($LASTEXITCODE -ne 0) {
    Info "Installing PyTorch CUDA 12.1 wheels (~2.5 GB, one-time)..."
    & $LtxPy -m pip install --upgrade pip
    & $LtxPy -m pip install torch --index-url https://download.pytorch.org/whl/cu121
    if ($LASTEXITCODE -ne 0) { Fail "torch install failed." }
} else { Ok "torch already installed" }

& $LtxPy -c "import diffusers, transformers, accelerate, imageio, sentencepiece" 2>$null
if ($LASTEXITCODE -ne 0) {
    Info "Installing LTX inference dependencies..."
    & $LtxPy -m pip install diffusers transformers accelerate "imageio[ffmpeg]" sentencepiece
    if ($LASTEXITCODE -ne 0) { Fail "dependency install failed." }
} else { Ok "LTX dependencies already installed" }

# ---------------------------------------------------------------- P7: Torch CUDA visibility
$cudaCheck = & $LtxPy -c "import torch; print('CUDA_OK' if torch.cuda.is_available() else 'CUDA_MISSING')" 2>&1
if ("$cudaCheck" -notmatch "CUDA_OK") { Fail "torch CUDA not visible inside the venv: $cudaCheck" }
Ok "torch CUDA visible"

# ---------------------------------------------------------------- P8: HF cache on D: (weights land on D:, not C:)
$hfCache = "D:\Deathbound\cache\huggingface"
New-Item -ItemType Directory -Force -Path $hfCache | Out-Null
$env:HF_HOME = $hfCache
[Environment]::SetEnvironmentVariable("HF_HOME", $hfCache, "User")
Ok "HF cache pinned to $hfCache (set for this session and persisted for the user)"

# ---------------------------------------------------------------- P9: Repo env sanity
$env:DEATHBOUND_ROOT = "D:\Deathbound"
& $LtxPy -c "import sys; sys.path.insert(0, r'D:\Deathbound'); from automation.video.diagnostics import run_diagnostics; import json; r = run_diagnostics(); print(json.dumps({'ready_for_smoke_test': r['ready_for_smoke_test'], 'blocking_errors': r['blocking_errors'], 'warnings': r['warnings']}, indent=2))" 2>&1
if ($LASTEXITCODE -ne 0) { Fail "diagnostics run failed inside the venv." }

Write-Host ""
Write-Host "=== SETUP COMPLETE ===" -ForegroundColor Cyan
Write-Host "Next step:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\test_ltx_local.ps1"
Write-Host "(first generation downloads ~15.5 GB total: 5.9 GB LTX checkpoint + 9.5 GB city96 T5 encoder;"
Write-Host " NEVER google/t5-v1_1-xxl 44.54 GB; Riven test needs the reference images in RIVEN_REFERENCE_BLOCKER.md)"
