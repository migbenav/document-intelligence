# dev.ps1 - Start backend and frontend simultaneously
# Usage: .\dev.ps1
# Press Ctrl+C to stop both processes

Write-Host "Starting Document Intelligence..." -ForegroundColor Cyan
Write-Host ""

# Start backend
Write-Host "[Backend]  Starting on http://localhost:8000" -ForegroundColor Green
$backend = Start-Process -NoNewWindow -PassThru -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.run:app", "--reload", "--port", "8000" `
    -WorkingDirectory "$PSScriptRoot\src\backend"

# Start frontend
Write-Host "[Frontend] Starting on http://localhost:5173" -ForegroundColor Green
$frontend = Start-Process -NoNewWindow -PassThru -FilePath "npm" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory "$PSScriptRoot\src\frontend"

Write-Host ""
Write-Host "Both services running. Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

# Wait and handle shutdown
try {
    # Keep script alive until interrupted
    while ($true) {
        if ($backend.HasExited -or $frontend.HasExited) {
            Write-Host "A process exited unexpectedly. Shutting down..." -ForegroundColor Red
            break
        }
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host ""
    Write-Host "Stopping services..." -ForegroundColor Yellow

    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
        Write-Host "[Backend]  Stopped" -ForegroundColor Gray
    }
    if (-not $frontend.HasExited) {
        Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
        Write-Host "[Frontend] Stopped" -ForegroundColor Gray
    }

    Write-Host "Done." -ForegroundColor Cyan
}
