# Windows PowerShell 5.1. RapidOCR 1.4.4 requires Python < 3.13.
$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$backendRoot = Join-Path $repoRoot 'backend'
$venvPython = Join-Path $backendRoot '.venv\Scripts\python.exe'

Push-Location $repoRoot
try {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Host 'Creating backend/.venv with Python 3.11 or 3.12'
        $created = $false
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $installedVersions = (& py --list 2>&1) -join "`n"
            foreach ($version in @('3.11', '3.12')) {
                if ($installedVersions -notmatch ('-(?:V:)?' + [regex]::Escape($version) + '\b')) { continue }
                $selector = '-' + $version
                & py $selector -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)' 2>$null
                if ($LASTEXITCODE -eq 0) {
                    & py $selector -m venv (Join-Path $backendRoot '.venv')
                    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
                    $created = $true
                    break
                }
            }
        }
        if (-not $created -and (Get-Command python -ErrorAction SilentlyContinue)) {
            & python -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)'
            if ($LASTEXITCODE -eq 0) {
                & python -m venv (Join-Path $backendRoot '.venv')
                if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
                $created = $true
            }
        }
        if (-not $created) { throw 'Install Python 3.11 or 3.12, then rerun setup.' }
    }
    & $venvPython -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Existing venv must use Python 3.11 or 3.12 for the pinned OCR package.' }
    Write-Host 'Installing pinned backend and development requirements'
    $pipArgs = @('-m', 'pip', 'install', '-r', 'backend/requirements.txt', '-r', 'backend/requirements-dev.txt')
    if ($env:WHEELS_DIR) { $pipArgs += @('--find-links', $env:WHEELS_DIR) }
    & $venvPython @pipArgs
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    if (Test-Path -LiteralPath (Join-Path $repoRoot 'frontend\package-lock.json')) {
        Write-Host 'Installing frontend from package-lock.json'
        Push-Location (Join-Path $repoRoot 'frontend')
        try {
            & npm.cmd ci --prefer-offline
            if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed' }
        } finally { Pop-Location }
    } else {
        Write-Host 'Frontend lockfile is not present yet; npm step pending P3.'
    }
    Write-Host 'Worktree setup complete. Start servers only from Local Actions.'
} finally { Pop-Location }
