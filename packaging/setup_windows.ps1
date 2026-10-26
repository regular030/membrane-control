[CmdletBinding()]
param(
    [string]$SourceRoot = '',
    [string]$InstallRoot = '',
    [switch]$Plan,
    [switch]$DefinitionsOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:SetupLogPath = $null

function Get-SetupSha256 {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $hash.Dispose() }
}

function Get-SafeChildPath {
    param([string]$Root, [string]$RelativePath)
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or $RelativePath.Contains('\') -or
        [IO.Path]::IsPathRooted($RelativePath) -or $RelativePath -match '[:*?"<>|]') {
        throw "Unsafe manifest/archive path: $RelativePath"
    }
    foreach ($part in $RelativePath.Split('/')) {
        if ($part -eq '' -or $part -eq '.' -or $part -eq '..' -or $part -match '[. ]$' -or
            $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') {
            throw "Unsafe manifest/archive path: $RelativePath"
        }
    }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $path = [IO.Path]::GetFullPath((Join-Path $base $RelativePath))
    if (-not $path.StartsWith($base + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes its intended directory: $RelativePath"
    }
    return $path
}

function Assert-NoReparsePoint {
    param([string]$Path, [string]$Root)
    $current = [IO.Path]::GetFullPath($Path)
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    while ($current.Length -ge $base.Length) {
        if (Test-Path -LiteralPath $current) {
            if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Links/junctions are not allowed in the setup payload: $current"
            }
        }
        if ($current -eq $base) { break }
        $current = Split-Path -Parent $current
    }
}

function Get-CheckedSetup {
    param([string]$PayloadRoot, [string]$Destination)
    if ([string]::IsNullOrWhiteSpace($PayloadRoot)) { throw 'Payload root is required' }
    $source = [IO.Path]::GetFullPath($PayloadRoot).TrimEnd('\', '/')
    $manifestPath = Join-Path $source 'setup-manifest.json'
    Assert-NoReparsePoint -Path $manifestPath -Root $source
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($key in @('version', 'app', 'files', 'python')) {
        if ($null -eq $manifest.PSObject.Properties[$key]) { throw "Setup manifest is missing $key" }
    }
    if ($manifest.version -isnot [string] -or $manifest.version -notmatch '^\d+\.\d+\.\d+(?:[A-Za-z0-9.+-]*)$' -or
        $manifest.app -cne 'app/MembraneControl.exe') { throw 'Unsupported setup manifest version or application path' }
    if ($null -eq $manifest.files -or $manifest.files -isnot [PSCustomObject]) { throw 'Setup manifest files must be an object' }
    foreach ($key in @('version', 'kind', 'url', 'sha256')) {
        if ($null -eq $manifest.python.PSObject.Properties[$key]) { throw "Python manifest is missing $key" }
    }
    $python = $manifest.python
    if ($python.version -isnot [string] -or $python.version -notmatch '^3\.(12|13|14)\.\d+$' -or
        $python.kind -cne 'zip' -or $python.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or
        $python.url -cne "https://www.python.org/ftp/python/$($python.version)/python-$($python.version)-amd64.zip") {
        throw 'Python must be a pinned, hashed official x64 full-runtime ZIP from python.org'
    }
    $files = @()
    $targets = @{}
    foreach ($entry in $manifest.files.PSObject.Properties) {
        if ($entry.Value -isnot [string] -or $entry.Value -notmatch '^[a-fA-F0-9]{64}$') { throw "Invalid SHA256 for $($entry.Name)" }
        $path = Get-SafeChildPath -Root $source -RelativePath $entry.Name
        Assert-NoReparsePoint -Path $path -Root $source
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing payload file: $($entry.Name)" }
        if ((Get-SetupSha256 -Path $path) -ine $entry.Value) { throw "SHA256 mismatch: $($entry.Name). Download setup again." }
        $target = if ($entry.Name -ceq $manifest.app) { 'MembraneControl.exe' } else { $entry.Name }
        if ($targets.ContainsKey($target)) { throw "Duplicate installed path: $target" }
        $targets[$target] = $true
        $files += [PSCustomObject]@{ Source = $path; Relative = $entry.Name; Target = $target }
    }
    foreach ($required in @($manifest.app, 'packaging/setup_windows.ps1', 'packaging/flash_dry_run.ps1',
        'firmware/platformio.ini', 'firmware/src/main.cpp', 'firmware/include/BoardProfile.h', 'firmware/include/BoardConfig.h')) {
        if (-not @($files | Where-Object { $_.Relative -ceq $required }).Count) { throw "Required file is not authenticated: $required" }
    }
    if ([string]::IsNullOrWhiteSpace($Destination)) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'Windows LOCALAPPDATA is unavailable' }
        $Destination = Join-Path $env:LOCALAPPDATA 'Programs/MembraneControl'
    }
    if ($Destination -match '^[A-Za-z]:(?![\\/])') { throw 'A drive-relative installation target is not allowed' }
    $fullDestination = [IO.Path]::GetFullPath($Destination)
    $destinationPath = $fullDestination.TrimEnd('\', '/')
    if ($destinationPath -eq [IO.Path]::GetPathRoot($fullDestination).TrimEnd('\', '/')) { throw 'A drive root or network share root cannot be an installation target' }
    if ($destinationPath -eq $source -or $destinationPath.StartsWith($source + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $source.StartsWith($destinationPath + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Installation and extracted payload directories must be separate' }
    return [PSCustomObject]@{ SourceRoot = $source; InstallRoot = $destinationPath; Manifest = $manifest; Files = $files }
}

function Write-SetupLog {
    param([string]$Message)
    Write-Host $Message
    if ($script:SetupLogPath) { Add-Content -LiteralPath $script:SetupLogPath -Value $Message -Encoding UTF8 }
}

function Invoke-SetupCommand {
    param([string]$FilePath, [string[]]$ArgumentList, [switch]$Capture)
    Write-SetupLog ("Running: " + [IO.Path]::GetFileName($FilePath) + ' ' + ($ArgumentList -join ' '))
    $lines = New-Object 'System.Collections.Generic.List[string]'
    $savedPreference = $ErrorActionPreference
    try {
        # Native stderr is diagnostic output, not a terminating PowerShell error.
        $ErrorActionPreference = 'Continue'
        & $FilePath @ArgumentList 2>&1 | ForEach-Object { $lines.Add([string]$_); Write-SetupLog ([string]$_) }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($code -ne 0) { throw "Command failed with exit code $code. See the setup log and rerun setup after correcting the problem." }
    if ($Capture) { return ($lines -join "`n") }
}

function Test-SetupPython {
    param([string]$PythonPath, [string]$ExpectedVersion)
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { return $false }
    # Single-quoted Python literals survive Windows PowerShell 5.1 native argv
    # marshalling; embedded double quotes would be stripped from a -c argument.
    $probe = "import json,struct,sys; print(json.dumps({'version':'.'.join(map(str,sys.version_info[:3])),'bits':struct.calcsize('P')*8}))"
    try {
        $output = Invoke-SetupCommand -FilePath $PythonPath -ArgumentList @('-I', '-c', $probe) -Capture
        $info = ($output -split "`n" | Where-Object { $_.Trim() } | Select-Object -Last 1) | ConvertFrom-Json
        return $info.version -ceq $ExpectedVersion -and $info.bits -eq 64
    } catch { return $false }
}

function Expand-CheckedPython {
    param([string]$Archive, [string]$Destination)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.TrimEnd('/')
            if ($name) { [void](Get-SafeChildPath -Root $Destination -RelativePath $name) }
            if (($entry.ExternalAttributes -shr 16 -band 0xf000) -eq 0xa000) { throw 'Python archive contains a symbolic link' }
        }
    } finally { $zip.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Destination)
}

function Get-SetupPython {
    param($Checked)
    $tools = Join-Path $Checked.InstallRoot 'tools'
    $version = $Checked.Manifest.python.version
    $runtime = Get-SafeChildPath -Root $tools -RelativePath "python-$version"
    $executable = Join-Path $runtime 'python.exe'
    if (Test-Path -LiteralPath $runtime) {
        if (Test-SetupPython -PythonPath $executable -ExpectedVersion $version) { return $executable }
        throw "The existing dedicated Python runtime is incomplete or incompatible: $runtime. Rename that folder and rerun setup."
    }
    $archive = Get-SafeChildPath -Root $tools -RelativePath "python-$version-amd64.zip"
    $expected = $Checked.Manifest.python.sha256
    if (-not (Test-Path -LiteralPath $archive) -or (Get-SetupSha256 -Path $archive) -ine $expected) {
        Write-SetupLog 'Downloading the official dedicated Python runtime. This does not register Python or change PATH.'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri $Checked.Manifest.python.url -OutFile $archive
    }
    if ((Get-SetupSha256 -Path $archive) -ine $expected) { throw 'Python archive SHA256 mismatch. Nothing from the archive was executed.' }
    $stageName = 'python-partial-' + [guid]::NewGuid().ToString('N')
    $stage = Get-SafeChildPath -Root $tools -RelativePath $stageName
    try {
        Expand-CheckedPython -Archive $archive -Destination $stage
        if (-not (Test-SetupPython -PythonPath (Join-Path $stage 'python.exe') -ExpectedVersion $version)) { throw 'Downloaded Python did not report the expected x64 runtime version' }
        # Both resolved paths are explicitly bounded to this installation's tools directory.
        [void](Get-SafeChildPath -Root $tools -RelativePath $stageName)
        [void](Get-SafeChildPath -Root $tools -RelativePath "python-$version")
        [IO.Directory]::Move($stage, $runtime)
    } finally {
        if (Test-Path -LiteralPath $stage) {
            [void](Get-SafeChildPath -Root $tools -RelativePath $stageName)
            Remove-Item -LiteralPath $stage -Recurse -Force
        }
    }
    return $executable
}

function ConvertTo-ShortcutArgument {
    param([string]$Value)
    if ($Value.Contains('"')) { throw 'A shortcut path cannot contain a quote' }
    return '"' + $Value.TrimEnd('\') + '"'
}

function Get-SetupShortcutSpecs {
    param([string]$Destination)
    $powershell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    foreach ($item in @(@{Name='Membrane Control'; Script=$null; Firmware=$null},
        @{Name='Flash ESP32 dry run'; Script='flash_dry_run.ps1'; Firmware='esp32-dry-run'},
        @{Name='Flash relay board test'; Script='flash_dry_run.ps1'; Firmware='esp32-relay-bench'},
        @{Name='Flash valve test (setup required)'; Script='flash_dry_run.ps1'; Firmware='esp32-valve-test'},
        @{Name='Flash full controller (setup required)'; Script='flash_dry_run.ps1'; Firmware='esp32-physical'},
        @{Name='USB driver help'; Script='install_cp210x.ps1'; Firmware=$null})) {
        $scriptPath = if ($item.Script) { Join-Path $Destination ('packaging/' + $item.Script) } else { $null }
        $arguments = ''
        $target = Join-Path $Destination 'MembraneControl.exe'
        if ($scriptPath) {
            $target = $powershell
            $rootParameter = if ($item.Script -eq 'install_cp210x.ps1') { '-Root' } else { '-InstallRoot' }
            $arguments = '-NoProfile -ExecutionPolicy Bypass -File ' + (ConvertTo-ShortcutArgument $scriptPath) + ' ' + $rootParameter + ' ' + (ConvertTo-ShortcutArgument $Destination)
            if ($item.Firmware) { $arguments += ' -Firmware ' + $item.Firmware }
        }
        [PSCustomObject]@{Name=$item.Name;Target=$target;Arguments=$arguments;ScriptPath=$scriptPath}
    }
}

function New-SetupShortcuts {
    param([string]$Destination)
    $shell = New-Object -ComObject WScript.Shell
    $specs = @(Get-SetupShortcutSpecs -Destination $Destination)
    $menu = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs/Membrane Control'
    $locations = @($menu, [Environment]::GetFolderPath('DesktopDirectory')) | Select-Object -Unique
    foreach ($location in $locations) {
        if ([string]::IsNullOrWhiteSpace($location)) { throw 'Windows shortcut directory is unavailable' }
        New-Item -ItemType Directory -Path $location -Force | Out-Null
        foreach ($item in $specs) {
            if ($item.ScriptPath -and -not (Test-Path -LiteralPath $item.ScriptPath)) { continue }
            $shortcut = $shell.CreateShortcut((Join-Path $location ($item.Name + '.lnk')))
            $shortcut.WorkingDirectory = $Destination
            $shortcut.IconLocation = Join-Path $Destination 'MembraneControl.exe'
            $shortcut.TargetPath = $item.Target
            $shortcut.Arguments = $item.Arguments
            $shortcut.Save()
        }
    }
}

function Invoke-MembraneSetup {
    param([string]$PayloadRoot, [string]$Destination, [switch]$PlanOnly)
    # Authenticate every payload file and validate all paths BEFORE installation.
    $checked = Get-CheckedSetup -PayloadRoot $PayloadRoot -Destination $Destination
    if ($PlanOnly) {
        [PSCustomObject]@{ version=$checked.Manifest.version; installRoot=$checked.InstallRoot;
            app=(Join-Path $checked.InstallRoot 'MembraneControl.exe'); python=$checked.Manifest.python;
            pythonVersion=$checked.Manifest.python.version;
            files=$checked.Files.Count; flashes_board=$false; installs_drivers=$false;
            firmware_targets=@('esp32-dry-run', 'esp32-relay-bench', 'esp32-valve-test', 'esp32-physical');
            valve_test=[PSCustomObject]@{environment='esp32-valve-test';commissioning_required=$true;physical_outputs_locked_by_default=$true;shipped_profile_verified=$false};
            full_controller=[PSCustomObject]@{environment='esp32-physical';commissioning_required=$true;physical_outputs_locked_by_default=$true;shipped_profile_verified=$false};
            steps=@('Verify payload hashes', 'Copy application and firmware', 'Prepare dedicated Python and virtual environment',
                'Install PlatformIO 6.2.0 and pyserial 3.5', 'Build dry-run, relay-board test, locked valve test and locked full controller firmware without uploading', 'Create shortcuts') } | ConvertTo-Json -Depth 5
        return
    }
    New-Item -ItemType Directory -Path $checked.InstallRoot -Force | Out-Null
    $logRoot = Join-Path $checked.InstallRoot 'logs'
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $script:SetupLogPath = Join-Path $logRoot ('setup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
    Write-SetupLog 'Installing Membrane Control for the current user. No board will be flashed and no driver is installed automatically.'
    Write-SetupLog ("Setup log: " + $script:SetupLogPath)
    $savedCore = $env:PLATFORMIO_CORE_DIR
    try {
        foreach ($file in $checked.Files) {
            $target = Get-SafeChildPath -Root $checked.InstallRoot -RelativePath $file.Target
            Assert-NoReparsePoint -Path $target -Root $checked.InstallRoot
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            Copy-Item -LiteralPath $file.Source -Destination $target -Force
        }
        New-Item -ItemType Directory -Path (Join-Path $checked.InstallRoot 'tools') -Force | Out-Null
        $python = Get-SetupPython -Checked $checked
        $venvRoot = Join-Path $checked.InstallRoot 'tools/.venv'
        $venvPython = Join-Path $venvRoot 'Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
            Invoke-SetupCommand -FilePath $python -ArgumentList @('-I', '-m', 'venv', $venvRoot)
        }
        if (-not (Test-SetupPython -PythonPath $venvPython -ExpectedVersion $checked.Manifest.python.version)) { throw 'The dedicated Python virtual environment is incompatible. Rename tools/.venv and rerun setup.' }
        Invoke-SetupCommand -FilePath $venvPython -ArgumentList @('-I', '-m', 'pip', '--isolated', '--disable-pip-version-check',
            'install', '--index-url', 'https://pypi.org/simple', '--no-input', 'platformio==6.2.0', 'pyserial==3.5')
        $env:PLATFORMIO_CORE_DIR = Join-Path $checked.InstallRoot 'tools/platformio'
        Invoke-SetupCommand -FilePath $venvPython -ArgumentList @('-I', '-m', 'platformio', '--no-ansi', 'run', '-d',
            (Join-Path $checked.InstallRoot 'firmware'), '-e', 'esp32-dry-run', '-e', 'esp32-relay-bench', '-e', 'esp32-valve-test', '-e', 'esp32-physical')
        New-SetupShortcuts -Destination $checked.InstallRoot
        Copy-Item -LiteralPath (Join-Path $checked.SourceRoot 'setup-manifest.json') -Destination (Join-Path $checked.InstallRoot 'setup-manifest.json') -Force
        Write-SetupLog 'Setup complete. Open Membrane Control to use the app. Flash ESP32 dry run is the no-output test; Flash relay board test operates only unloaded relays. Upload separately when the board and COM port are ready.'
        Write-SetupLog 'Flash valve test (setup required) installs a separate sensor-free program with the valve outputs locked until a reviewed valve profile and commissioning checks are complete. Read docs/valve-test.md; keep loads disconnected for the initial upload.'
        Write-SetupLog 'Flash full controller (setup required) installs the full program with an unverified hardware profile. Physical outputs stay locked until a reviewed profile and rig commissioning are complete.'
        Write-SetupLog 'If Windows shows no controller COM port, use the optional USB driver help shortcut for the official driver instructions.'
    } catch {
        Write-SetupLog ("SETUP FAILED: " + $_.Exception.Message)
        Write-SetupLog 'Setup did not complete. Close the app if it is open, correct the reported problem and rerun this setup. Existing experiment data is not stored in this install folder.'
        throw
    } finally { $env:PLATFORMIO_CORE_DIR = $savedCore }
}

if (-not $DefinitionsOnly) {
    if ([string]::IsNullOrWhiteSpace($SourceRoot)) { $SourceRoot = Split-Path -Parent $PSScriptRoot }
    try { Invoke-MembraneSetup -PayloadRoot $SourceRoot -Destination $InstallRoot -PlanOnly:$Plan }
    catch { Write-Host ("Setup failed: " + $_.Exception.Message) -ForegroundColor Red; exit 1 }
}
