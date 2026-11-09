[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [string]$Port = '',
    [ValidateSet('esp32-dry-run', 'esp32-bluetooth-dry-run', 'esp32-relay-bench', 'esp32-valve-test', 'esp32-physical', 'esp32-bluetooth-physical')]
    [string]$Firmware = 'esp32-dry-run',
    [switch]$Plan,
    [switch]$DefinitionsOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Get-DryRunFlashPlan {
    param([string]$Root, [string]$ComPort,
        [ValidateSet('esp32-dry-run', 'esp32-bluetooth-dry-run', 'esp32-relay-bench', 'esp32-valve-test', 'esp32-physical', 'esp32-bluetooth-physical')][string]$Firmware = 'esp32-dry-run')
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
    $normalController = $Firmware -in @('esp32-physical', 'esp32-bluetooth-physical')
    return [PSCustomObject]@{ python=$python; core=(Join-Path $destination 'tools/platformio'); port=$name;
        arguments=@('-I', '-m', 'platformio', '--no-ansi', 'run', '-d', $firmwareRoot, '-e', $Firmware, '-t', 'upload', '--upload-port', $name);
        environment=$Firmware; selected_firmware=$Firmware; replaces_existing_firmware=$true;
        requires_existing_bluetooth_bond=($Firmware -eq 'esp32-bluetooth-physical');
        commissioning_required=($normalController -or $Firmware -eq 'esp32-valve-test');
        physical_outputs_locked_by_default=($Firmware -eq 'esp32-valve-test');
        manual_valve_count=$(if ($normalController) { 6 } else { 0 });
        manual_valve_control_ready_by_default=$normalController }
}

function Invoke-DryRunFlash {
    param([string]$Root, [string]$ComPort, [switch]$PlanOnly,
        [ValidateSet('esp32-dry-run', 'esp32-bluetooth-dry-run', 'esp32-relay-bench', 'esp32-valve-test', 'esp32-physical', 'esp32-bluetooth-physical')][string]$Firmware = 'esp32-dry-run')
    if ($PlanOnly) {
        Get-DryRunFlashPlan -Root $Root -ComPort $ComPort -Firmware $Firmware | ConvertTo-Json -Depth 4
        return
    }
    $bluetoothTest = $Firmware -eq 'esp32-bluetooth-dry-run'
    $bluetoothNormal = $Firmware -eq 'esp32-bluetooth-physical'
    $normalController = $bluetoothNormal -or $Firmware -eq 'esp32-physical'
    Write-Host ("This uploads " + $Firmware + " and REPLACES the selected board's existing program.") -ForegroundColor Yellow
    if ($bluetoothTest) {
        Write-Host 'BLUETOOTH DRY RUN uses simulated measurements and never operates the pump or valves.'
        Write-Host 'This optional firmware builds on demand. Upload through the wired ESP32 USB-UART COM port. Pair Bluetooth after the upload.'
    } elseif ($Firmware -eq 'esp32-relay-bench') {
        Write-Host 'RELAY BOARD TEST OPERATES REAL RELAYS. Disconnect every external wire from all relay COM, NO and NC contacts.' -ForegroundColor Yellow
        Write-Host 'Use only the standalone Srliya 16-channel relay board, not the Freenove camera board. Sensors and pump interfaces are not needed for this bench test.'
    } elseif ($Firmware -eq 'esp32-valve-test') {
        Write-Host 'VALVE TEST (SETUP REQUIRED): the shipped valve profile is unverified and physical outputs are locked.' -ForegroundColor Yellow
        Write-Host 'This is a separate physical valve-test program, not dry run or the unloaded raw relay test. It has no sensor, DAC, pump or experiment controls.'
        Write-Host 'Disconnect every external wire from all relay COM, NO and NC contacts for this initial upload. Read docs/valve-test.md before preparing a reviewed valve profile or connecting loads.'
    } elseif ($normalController) {
        Write-Host 'NORMAL CONTROLLER: V1,V2,V3,V4,V5,V7 = relay bits 0,1,2,3,5,6. No V6; bit4 unused.'
        if ($bluetoothNormal) {
            Write-Host 'BLUETOOTH NORMAL CONTROLLER CAN OPERATE REAL EQUIPMENT.' -ForegroundColor Yellow
            Write-Host 'Keep a working pairing. For a new pairing, use Pair Bluetooth controller after the upload.'
            Write-Host 'This optional firmware builds on demand using the same installed BoardProfile.h as the wired controller. Upload through wired USB-UART and retain the existing Bluetooth bond. Do not erase the ESP32 flash or remove the Windows pairing.'
        }
        Write-Host 'Dashboard valve ON/OFF controls do not need pressure, flow, scale, a DAC or the separate valve-test profile.'
        Write-Host 'Pump/experiment operation remains separate and requires its configured inputs and pump interface.'
    } else {
        Write-Host 'Dry-run firmware uses generated measurements and does not operate relay GPIO.'
    }
    if ($Firmware -ne 'esp32-physical') { Write-Host 'Keep the pump and valve loads disconnected. Confirm the actual board supply rating before powering it.' }
    Write-Host 'Close Arduino Serial Monitor/Plotter, the app''s controller connection and any other program using this COM port.'
    Write-Host 'For an external-UART board without automatic reset: hold IO0, press and release EN/RESET, then release IO0 before continuing.'
    if ([string]::IsNullOrWhiteSpace($ComPort)) { $ComPort = Read-Host 'Wired controller USB-UART COM port from Windows Device Manager (for example COM3)' }
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
        if ($bluetoothTest) {
            Write-Host 'In Windows Settings, open Bluetooth & devices, add a Bluetooth device, and pair MembraneControl-Bench.'
            Write-Host 'In More Bluetooth settings, open the COM Ports tab. Use the Outgoing COM port for MembraneControl-Bench. Add an Outgoing port for that device if Windows has not listed one.'
            Write-Host 'Open Membrane Control in hardware mode, refresh the controller port list, and connect to that Outgoing Bluetooth COM port. The app must report Connected (dry run).'
        } elseif ($Firmware -eq 'esp32-relay-bench') {
            Write-Host 'Open Connections and settings, then Relay board test. Keep all relay contacts disconnected and follow the rest-pattern check before testing individual bits.'
            Write-Host 'This tool switches unloaded relays. It does not verify valve movement, commission the rig or enable an experiment.'
        } elseif ($Firmware -eq 'esp32-valve-test') {
            Write-Host 'Follow docs/valve-test.md in the installation folder. The shipped valve-test profile must report unverified and keep physical outputs locked.'
            Write-Host 'A reviewed valve profile and its commissioning checks are required before connecting loads. This target does not use sensors or control the pump, DAC or an experiment.'
        } elseif ($normalController) {
            if ($bluetoothNormal) {
                Write-Host 'The ESP32 keeps the Bluetooth name MembraneControl-Bench. Keep the existing Windows pairing.'
                Write-Host 'Open Membrane Control in hardware mode, refresh the controller port list, and connect to the existing Outgoing Bluetooth COM port. The app must report Connected.'
                Write-Host 'If the saved pairing is missing, use Pair Bluetooth controller with the board running. You can restore the pairing without another upload.'
            } else {
                Write-Host 'Open the app in hardware mode and connect this controller port.'
            }
            Write-Host 'Use Dashboard V1-V5 and V7 ON/OFF. No sensor connection or extra profile form is required for manual valves.'
            Write-Host 'Finish the reviewed hardware profile, sensor calibration, pump interface and process-safe wiring before real operation. Uploading this target alone does not commission the rig.'
        } else {
            Write-Host 'Open the app in hardware mode and select this controller port. It must report Connected (dry run).'
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
