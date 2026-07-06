param(
    [ValidateSet("web", "desktop", "test", "build-windows", "install")]
    [string]$Action = "web",
    [switch]$UseSystemPython,
    [switch]$DesktopDeps,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Show-Help {
    @"
ADB Device Manager runner

Usage:
  powershell -ExecutionPolicy Bypass -File scripts/run.ps1 [-Action web|desktop|test|build-windows|install] [-UseSystemPython] [-DesktopDeps]

Examples:
  powershell -ExecutionPolicy Bypass -File scripts/run.ps1
  powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Action desktop -DesktopDeps
  powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Action test
  powershell -ExecutionPolicy Bypass -File scripts/run.ps1 -Action build-windows -DesktopDeps

Defaults to a managed .venv. Use -UseSystemPython to run with the active/system Python.
"@
}

function Find-SystemPython {
    $candidates = @(
        @("py", "-3"),
        @("python", ""),
        @("python3", "")
    )
    foreach ($candidate in $candidates) {
        $cmd = $candidate[0]
        $arg = $candidate[1]
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            $probeArgs = @()
            if ($arg) { $probeArgs += $arg }
            $probeArgs += "--version"
            $oldPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                & $cmd @probeArgs > $null 2> $null
                $code = $LASTEXITCODE
            } catch {
                $code = 1
            } finally {
                $ErrorActionPreference = $oldPreference
            }
            if ($code -eq 0) {
                if ($arg) { return @($cmd, $arg) }
                return @($cmd)
            }
        }
    }
    throw "Python was not found. Install Python 3.10+ or use an existing virtual environment."
}

function Invoke-SystemPython {
    param([string[]]$Arguments)
    $py = Find-SystemPython
    $cmd = $py[0]
    $prefix = @()
    if ($py.Length -gt 1) {
        $prefix = $py[1..($py.Length - 1)]
    }
    & $cmd @prefix @Arguments
}

function Invoke-Python {
    param([string[]]$Arguments)
    if ($UseSystemPython) {
        Invoke-SystemPython -Arguments $Arguments
    } else {
        Ensure-Venv
        & $VenvPython @Arguments
    }
}

function Ensure-Venv {
    if (Test-Path $VenvPython) { return }
    Write-Host "Creating .venv..."
    Invoke-SystemPython -Arguments @("-m", "venv", $VenvDir)
    if (-not (Test-Path $VenvPython)) {
        throw "Failed to create .venv. Install Python 3.10+ with the venv module enabled."
    }
}

function Install-Dependencies {
    if (-not $UseSystemPython) { Ensure-Venv }
    Invoke-Python -Arguments @("-m", "pip", "install", "--upgrade", "pip")
    if ($DesktopDeps) {
        Invoke-Python -Arguments @("-m", "pip", "install", "-r", "requirements-desktop.txt")
    } else {
        Invoke-Python -Arguments @("-m", "pip", "install", "-r", "requirements.txt")
    }
}

function Invoke-Action {
    Set-Location $RepoRoot
    switch ($Action) {
        "install" {
            Install-Dependencies
        }
        "web" {
            Install-Dependencies
            Invoke-Python -Arguments @("app.py")
        }
        "desktop" {
            $script:DesktopDeps = $true
            Install-Dependencies
            Invoke-Python -Arguments @("desktop.py")
        }
        "test" {
            Install-Dependencies
            Invoke-Python -Arguments @("-m", "pytest", "-q")
        }
        "build-windows" {
            if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
                throw "The Windows desktop build must be run on Windows."
            }
            $script:DesktopDeps = $true
            Install-Dependencies
            Invoke-Python -Arguments @("-m", "PyInstaller", "build/windows.spec", "--noconfirm")
        }
    }
}

if ($Help) {
    Show-Help
    exit 0
}

Invoke-Action
