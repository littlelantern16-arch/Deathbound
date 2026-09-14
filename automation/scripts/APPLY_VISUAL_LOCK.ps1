$ErrorActionPreference = "Stop"

Write-Host "=== DEATHBOUND VISUAL LOCK ===" -ForegroundColor Cyan

$root = "D:\Deathbound"
$config = "$root\config"
$script = "$root\automation\scripts\apply_visual_lock.py"
$workflow = "C:\ComfyUI\Deathbound_Riven_FaceID.json"
$checkpoint = "C:\ComfyUI\models\checkpoints\Realistic_Vision_V6.0_B1_pruned.safetensors"

if (!(Test-Path $checkpoint)) {
    throw "Realistic Vision checkpoint not found: $checkpoint"
}

if (!(Test-Path $workflow)) {
    throw "FaceID workflow not found: $workflow"
}

New-Item -ItemType Directory -Force "$config" | Out-Null
New-Item -ItemType Directory -Force "$root\automation\scripts" | Out-Null

$sourceDNA = Join-Path $PSScriptRoot "..\..\config\DEATHBOUND_VISUAL_STYLE_DNA.json"
$destDNA = "$config\DEATHBOUND_VISUAL_STYLE_DNA.json"

if (Test-Path $sourceDNA) {
}

python "$script"

Write-Host ""
Write-Host "VISUAL LOCK COMPLETE." -ForegroundColor Green
Write-Host "Open ComfyUI and reload the workflow." -ForegroundColor Yellow
Write-Host "Do not change the locked checkpoint/style settings unless the production pipeline explicitly overrides them."
