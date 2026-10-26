[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [string]$Port = '',
    [ValidateSet('esp32-dry-run', 'esp32-relay-bench')]
    [string]$Firmware = 'esp32-dry-run',
    [switch]$Plan,
    [switch]$DefinitionsOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Get-DryRunFlashPlan {
    param([string]$Root, [string]$ComPort,
        [ValidateSet('esp32-dry-run', 'esp32-relay-bench')][string]$Firmware = 'esp32-dry-run')
    # ValidateSet is case-insensitive in Windows PowerShell 5.1; PlatformIO
    # environment names must still receive their canonical spelling.
    $Firmware = $Firmware.ToLowerInvariant()
    $name = $ComPort.Trim().ToUpperInvariant()
    if ($name -notmatch '^COM[1-9][0-9]{0,3}$') { throw 'Enter a Windows COM port such as COM3. No other text or command is accepted.' }
    $destination = [IO.Path]::GetFullPath($Root)
    $python = Join-Path $destination 'tools/.venv/Scripts/python.exe'
    $firmwareRoot = Join-Path $destination 'firmware'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $firmwareRoot 'platformio.ini') -PathType Leaf)) {
        throw 'The installed firmware tools are missing. Run Membrane Control Setup again first.'
    }
    return [PSCustomObject]@{ python=$python; core=(Join-Path $destination 'tools/platformio'); port=$name;
        arguments=@('-I', '-m', 'platformio', 'run', '-d', $firmwareRoot, '-e', $Firmware, '-t', 'upload', '--upload-port', $name);
        environment=$Firmware; selected_firmware=$Firmware; replaces_existing_firmware=$true }
}

function Invoke-DryRunFlash {
    param([string]$Root, [string]$ComPort, [switch]$PlanOnly,
        [ValidateSet('esp32-dry-run', 'esp32-relay-bench')][string]$Firmware = 'esp32-dry-run')
    if ($PlanOnly) {
        Get-DryRunFlashPlan -Root $Root -ComPort $ComPort -Firmware $Firmware | ConvertTo-Json -Depth 4
        return
    }
    Write-Host ("This uploads " + $Firmware + " and REPLACES the selected board's existing program.") -ForegroundColor Yellow
    if ($Firmware -eq 'esp32-relay-bench') {
        Write-Host 'RELAY BOARD TEST OPERATES REAL RELAYS. Disconnect every external wire from all relay COM, NO and NC contacts.' -ForegroundColor Yellow
        Write-Host 'Use only the standalone Srliya 16-channel relay board, not the Freenove camera board. Sensors and pump interfaces are not needed for this bench test.'
    } else {
        Write-Host 'Dry-run firmware uses generated measurements and does not operate relay GPIO.'
    }
    Write-Host 'Keep the pump and valve loads disconnected. Confirm the actual board supply rating before powering it.'
    Write-Host 'Close Arduino Serial Monitor/Plotter, the app''s controller connection and any other program using this COM port.'
    Write-Host 'For an external-UART board without automatic reset: hold IO0, press and release EN/RESET, then release IO0 before continuing.'
    if ([string]::IsNullOrWhiteSpace($ComPort)) { $ComPort = Read-Host 'Controller COM port from Windows Device Manager (for example COM3)' }
    $flash = Get-DryRunFlashPlan -Root $Root -ComPort $ComPort -Firmware $Firmware
    if ((Read-Host ("Type FLASH to upload " + $Firmware + ' to ' + $flash.port + ', or anything else to cancel')) -cne 'FLASH') {
        Write-Host 'Cancelled. No board was opened or flashed.'
        return
    }
    $logRoot = Join-Path $Root 'logs'
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $log = Join-Path $logRoot ('flash-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
    $savedCore = $env:PLATFORMIO_CORE_DIR
    try {
        $env:PLATFORMIO_CORE_DIR = $flash.core
        $savedPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $uploadArguments = [string[]]$flash.arguments
            & $flash.python @uploadArguments 2>&1 | ForEach-Object { Write-Host ([string]$_); Add-Content -LiteralPath $log -Value ([string]$_) -Encoding UTF8 }
            $code = $LASTEXITCODE
        } finally { $ErrorActionPreference = $savedPreference }
        if ($code -ne 0) { throw "Upload failed (exit $code). Close other COM-port programs, verify the port and retry. Log: $log" }
        Write-Host ($Firmware + ' upload completed. With IO0 released, press EN/RESET to run the program if the adapter cannot reset the board automatically.')
        if ($Firmware -eq 'esp32-relay-bench') {
            Write-Host 'Open Connections and settings, then Relay board test. Keep all relay contacts disconnected and follow the rest-pattern check before testing individual bits.'
            Write-Host 'This tool switches unloaded relays. It does not verify valve movement, commission the rig or enable an experiment.'
        } else {
            Write-Host 'Open the app, turn Simulation mode off and select this controller port. It must report Connected (dry run).'
            Write-Host 'This does not commission the relay wiring or enable physical equipment.'
        }
    } finally { $env:PLATFORMIO_CORE_DIR = $savedCore }
}

if (-not $DefinitionsOnly) {
    if ([string]::IsNullOrWhiteSpace($InstallRoot)) { $InstallRoot = Split-Path -Parent $PSScriptRoot }
    try {
        Invoke-DryRunFlash -Root $InstallRoot -ComPort $Port -Firmware $Firmware -PlanOnly:$Plan
        if (-not $Plan) { [void](Read-Host 'Press Enter to close this window') }
    } catch {
        Write-Host ("Flash failed: " + $_.Exception.Message) -ForegroundColor Red
        if (-not $Plan) { [void](Read-Host 'Press Enter to close this window') }
        exit 1
    }
}
