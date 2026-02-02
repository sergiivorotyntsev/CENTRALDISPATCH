# =============================================================================
# START DEVELOPMENT SERVERS (Windows PowerShell)
# Starts both backend (FastAPI) and frontend (Vite) in parallel
#
# Usage:
#   .\scripts\start_dev.ps1
#   .\scripts\start_dev.ps1 -BackendOnly
#   .\scripts\start_dev.ps1 -FrontendOnly
# =============================================================================

param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"

# Get project root (parent of scripts folder)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# Activate virtual environment
if (Test-Path ".venv\Scripts\Activate.ps1") {
    & .\.venv\Scripts\Activate.ps1
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  CENTRALDISPATCH - Development Server   " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

if ($FrontendOnly) {
    Write-Host "Starting frontend only..." -ForegroundColor Green
    Write-Host "  -> http://localhost:5173"
    Write-Host ""
    Push-Location web
    npm run dev
    Pop-Location
}
elseif ($BackendOnly) {
    Write-Host "Starting backend only..." -ForegroundColor Green
    Write-Host "  -> http://localhost:8000"
    Write-Host "  -> http://localhost:8000/docs (API docs)"
    Write-Host ""
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
}
else {
    Write-Host "Starting both backend and frontend..." -ForegroundColor Green
    Write-Host ""
    Write-Host "Backend:" -ForegroundColor Yellow
    Write-Host "  -> http://localhost:8000"
    Write-Host "  -> http://localhost:8000/docs (API docs)"
    Write-Host ""
    Write-Host "Frontend:" -ForegroundColor Yellow
    Write-Host "  -> http://localhost:5173"
    Write-Host ""
    Write-Host "Press Ctrl+C to stop all servers" -ForegroundColor Cyan
    Write-Host ""

    # Start backend as background job
    $backendJob = Start-Job -ScriptBlock {
        param($projectRoot)
        Set-Location $projectRoot
        if (Test-Path ".venv\Scripts\Activate.ps1") {
            & .\.venv\Scripts\Activate.ps1
        }
        uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    } -ArgumentList $ProjectRoot

    # Give backend time to start
    Start-Sleep -Seconds 2

    # Start frontend as background job
    $frontendJob = Start-Job -ScriptBlock {
        param($projectRoot)
        Set-Location "$projectRoot\web"
        npm run dev
    } -ArgumentList $ProjectRoot

    # Wait and handle Ctrl+C
    try {
        Write-Host "Backend job: $($backendJob.Id)" -ForegroundColor Gray
        Write-Host "Frontend job: $($frontendJob.Id)" -ForegroundColor Gray
        Write-Host ""

        # Monitor jobs
        while ($true) {
            $backendState = (Get-Job -Id $backendJob.Id).State
            $frontendState = (Get-Job -Id $frontendJob.Id).State

            if ($backendState -eq "Failed" -or $frontendState -eq "Failed") {
                Write-Host "A server failed. Check output:" -ForegroundColor Red
                if ($backendState -eq "Failed") {
                    Write-Host "Backend error:" -ForegroundColor Red
                    Receive-Job -Id $backendJob.Id
                }
                if ($frontendState -eq "Failed") {
                    Write-Host "Frontend error:" -ForegroundColor Red
                    Receive-Job -Id $frontendJob.Id
                }
                break
            }

            Start-Sleep -Seconds 2
        }
    }
    finally {
        Write-Host ""
        Write-Host "Stopping servers..." -ForegroundColor Yellow
        Stop-Job -Id $backendJob.Id -ErrorAction SilentlyContinue
        Stop-Job -Id $frontendJob.Id -ErrorAction SilentlyContinue
        Remove-Job -Id $backendJob.Id -Force -ErrorAction SilentlyContinue
        Remove-Job -Id $frontendJob.Id -Force -ErrorAction SilentlyContinue
        Write-Host "Servers stopped." -ForegroundColor Green
    }
}
