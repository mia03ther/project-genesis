param([int]$Port = 8000, [switch]$SmokeTest, [switch]$WithPet, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Run the README setup first: uv venv --python 3.12 .venv'
}
$foundry = Get-Command anvil -ErrorAction SilentlyContinue
$anvilPath = if ($foundry) { $foundry.Source } else { Join-Path $env:USERPROFILE '.foundry\bin\anvil.exe' }
if (-not (Test-Path -LiteralPath $anvilPath)) { throw 'Install Foundry first (see README).' }
$launchArguments = @('-m', 'genesis.launch', '--port', "$Port", '--anvil', $anvilPath)
if ($SmokeTest) { $launchArguments += '--smoke-test' }
if ($WithPet) { $launchArguments += '--pet' }
if ($NoBrowser) { $launchArguments += '--no-browser' }
& $python @launchArguments
exit $LASTEXITCODE
