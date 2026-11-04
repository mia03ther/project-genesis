$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Install a current Node.js LTS release first: https://nodejs.org/' }
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    uv venv --python 3.12 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python 3.12 environment.' }
}
uv pip install --python $python -e '.[lab,dev]'
if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
npm --prefix frontend ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed.' }
npm --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
Write-Output 'Setup complete. Install Foundry if needed, then run: .\scripts\Start-Genesis.ps1'
