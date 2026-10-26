[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$Profile,
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][ValidatePattern('^COM[1-9][0-9]{0,3}$')][string]$Port,
    [switch]$Plan
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
try {
    $valveRoot = [IO.Path]::GetFullPath($InstallRoot)
    $valvePython = Join-Path $valveRoot 'tools/.venv/Scripts/python.exe'
    $valveCore = Join-Path $valveRoot 'tools/platformio'
    if (-not (Test-Path -LiteralPath $valvePython -PathType Leaf)) {
        $valvePython = Join-Path $valveRoot '.venv/Scripts/python.exe'
        $valveCore = Join-Path $valveRoot 'work/platformio'
    }
    if (-not (Test-Path -LiteralPath $valvePython -PathType Leaf)) {
        throw 'Private Python/build tools are missing. Run the latest Membrane Control Setup first.'
    }
    $valveHelper = Join-Path $valveRoot 'packaging/prepare_valve_test.py'
    if (-not (Test-Path -LiteralPath $valveHelper -PathType Leaf)) { throw 'Valve setup helper is missing. Install the latest Setup EXE.' }
    $valveArguments = @('-I', $valveHelper, '--source-firmware', (Join-Path $valveRoot 'firmware'),
        '--profile', [IO.Path]::GetFullPath($Profile), '--workspace', [IO.Path]::GetFullPath($Workspace),
        '--python', $valvePython, '--core', $valveCore, '--port', $Port.ToUpperInvariant())
    if ($Plan) { $valveArguments += '--plan' } else { $valveArguments += '--upload' }
    & $valvePython @valveArguments
    if ($LASTEXITCODE -ne 0) { throw "Valve setup ended with code $LASTEXITCODE. No experiment was enabled." }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    if (-not $Plan) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}
if (-not $Plan) {
    Write-Host 'Close this console, press EN/RESET with IO0 released, then reconnect in Valve test (no sensors).'
    Read-Host 'Press Enter to close' | Out-Null
}
