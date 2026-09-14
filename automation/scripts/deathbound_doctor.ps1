<#
Read-only Deathbound dependency validation. It changes no files, settings, or services.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = 'D:\Deathbound'
$results = [System.Collections.Generic.List[object]]::new()

function Add-Result {
    param([string]$Name, [ValidateSet('PASS','WARN','FAIL')][string]$Status, [string]$Detail)
    $script:results.Add([pscustomobject]@{ Check = $Name; Status = $Status; Detail = $Detail })
}

function Test-PathCheck {
    param([string]$Name, [string]$Path, [bool]$Required = $true)
    if (Test-Path -LiteralPath $Path) {
        Add-Result $Name 'PASS' $Path
    } elseif ($Required) {
        Add-Result $Name 'FAIL' "Missing: $Path"
    } else {
        Add-Result $Name 'WARN' "Not installed: $Path"
    }
}

Test-PathCheck 'Deathbound root' $root
Test-PathCheck 'FreeLLMAPI' 'C:\freellmapi-0.9.8\freellmapi-0.9.8'
Test-PathCheck 'ComfyUI' 'C:\ComfyUI'

$ffmpeg = Join-Path $root 'tools\ffmpeg\bin\ffmpeg.exe'
if (Test-Path -LiteralPath $ffmpeg) {
    $version = (& $ffmpeg -version 2>$null | Select-Object -First 1)
    Add-Result 'FFmpeg' 'PASS' "$ffmpeg — $version"
} else { Add-Result 'FFmpeg' 'FAIL' "Missing: $ffmpeg" }

$blender = Join-Path $root 'tools\blender\blender.exe'
if (Test-Path -LiteralPath $blender) {
    $version = (& $blender --version 2>$null | Select-Object -First 1)
    Add-Result 'Blender' 'PASS' "$blender — $version"
} else { Add-Result 'Blender' 'FAIL' "Missing: $blender" }

$pythonCandidates = @(
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    'C:\Users\bhavy\AppData\Local\Programs\Python\Python311\python.exe',
    'C:\Users\bhavy\AppData\Local\Programs\Python\Python313\python.exe'
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
if ($pythonCandidates) { Add-Result 'Python' 'PASS' ($pythonCandidates -join '; ') } else { Add-Result 'Python' 'FAIL' 'No Python executable found.' }

foreach ($tool in @('node', 'git')) {
    $command = Get-Command $tool -ErrorAction SilentlyContinue
    if ($command) {
        $version = (& $command.Source --version 2>$null | Select-Object -First 1)
        Add-Result $tool.ToUpper() 'PASS' "$($command.Source) — $version"
    } else { Add-Result $tool.ToUpper() 'FAIL' 'Not found on PATH.' }
}

$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    $gpu = (& $nvidiaSmi.Source --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null | Select-Object -First 1)
    if ($gpu) { Add-Result 'GPU' 'PASS' $gpu } else { Add-Result 'GPU' 'WARN' 'nvidia-smi is present but did not return GPU data.' }
} else { Add-Result 'GPU' 'FAIL' 'nvidia-smi not found on PATH.' }

$results | Format-Table -AutoSize
if ($results.Status -contains 'FAIL') { exit 1 }
