# Optional, user-launched driver help. Windows PowerShell 5.1; no global policy changes.
[CmdletBinding()]
param(
    [Alias('SourceRoot')][string]$Root = '',
    [switch]$Plan,
    [switch]$DefinitionsOnly,
    [string]$ElevatedStage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-Cp210xChild {
    param([string]$Base, [string]$Relative)
    if ([string]::IsNullOrWhiteSpace($Relative) -or
        [IO.Path]::IsPathRooted($Relative) -or $Relative.Contains(':') -or
        $Relative -match '(^|[\\/])\.\.([\\/]|$)') {
        throw 'Driver path must be relative and remain inside its working folder.'
    }
    $basePath = [IO.Path]::GetFullPath($Base).TrimEnd('\', '/')
    $path = [IO.Path]::GetFullPath((Join-Path $basePath $Relative))
    if (-not $path.StartsWith($basePath + [IO.Path]::DirectorySeparatorChar,
                             [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Driver path escapes its working folder.'
    }
    # Refuse redirected working folders instead of writing through junctions.
    $probe = $path
    while ($probe) {
        if (Test-Path -LiteralPath $probe) {
            $item = Get-Item -LiteralPath $probe -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Driver working paths cannot contain junctions or symbolic links.'
            }
        }
        $parent = Split-Path -Parent $probe
        if ($parent -eq $probe) { break }
        $probe = $parent
    }
    return $path
}

function Get-Cp210xConfiguration {
    param([string]$InstallRoot)
    $file = Resolve-Cp210xChild $InstallRoot 'packaging/driver-config.json'
    $config = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
    if ($config.schema_version -ne 1 -or $config.available -isnot [bool] -or
        $config.url -cne 'https://www.silabs.com/documents/public/software/CP210x_Universal_Windows_Driver.zip' -or
        $config.support_url -cne 'https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers') {
        throw 'Unrecognized CP210x driver configuration. Use the official vendor page.'
    }
    foreach ($relative in @($config.inf_path, $config.catalog_path)) {
        $null = Resolve-Cp210xChild $InstallRoot $relative
    }
    if ([IO.Path]::GetFileName($config.inf_path) -ine 'silabser.inf' -or
        [IO.Path]::GetFileName($config.catalog_path) -ine 'silabser.cat') {
        throw 'Expected the specific Silicon Labs INF and catalog.'
    }
    return $config
}

function Assert-Cp210xPin {
    param($Config)
    if (-not $Config.available -or [string]$Config.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw 'No verified driver archive is pinned in this release. Use the official vendor page or ask IT.'
    }
}

function Get-Cp210xSha256 {
    param([string]$File)
    $stream = [IO.File]::OpenRead($File)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Assert-Cp210xArchive {
    param([string]$Archive, $Config)
    Assert-Cp210xPin $Config
    $hash = Get-Cp210xSha256 $Archive
    if ($hash -ine $Config.sha256) {
        throw 'Driver SHA256 mismatch. Nothing will be installed; obtain a reviewed release or use the official vendor page.'
    }
}

function Expand-Cp210xArchive {
    param([string]$Archive, [string]$Destination)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        if ($zip.Entries.Count -gt 200) { throw 'Driver archive has too many entries.' }
        $names = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        [long]$expandedBytes = 0
        foreach ($entry in $zip.Entries) {
            $target = Resolve-Cp210xChild $Destination $entry.FullName
            if (-not $names.Add($target)) { throw 'Duplicate driver archive path.' }
            $expandedBytes += $entry.Length
            if ($expandedBytes -gt 41943040) { throw 'Driver archive is too large.' }
            if ($entry.FullName -match '[\\/]$') { continue }
            if (Test-Path -LiteralPath $target) { throw 'Driver extraction destination is not empty.' }
        }
        foreach ($entry in $zip.Entries) {
            $target = Resolve-Cp210xChild $Destination $entry.FullName
            if ($entry.FullName -match '[\\/]$') {
                $null = New-Item -ItemType Directory -Path $target -Force
            } else {
                $null = New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
            }
        }
    } finally { $zip.Dispose() }
}

function Assert-Cp210xPackage {
    param([string]$Stage, $Config)
    $archive = Resolve-Cp210xChild $Stage 'driver.zip'
    Assert-Cp210xArchive $archive $Config
    $expanded = Resolve-Cp210xChild $Stage 'expanded'
    $inf = Resolve-Cp210xChild $expanded $Config.inf_path
    $catalog = Resolve-Cp210xChild $expanded $Config.catalog_path
    if (-not (Test-Path -LiteralPath $inf -PathType Leaf) -or
        -not (Test-Path -LiteralPath $catalog -PathType Leaf)) {
        throw 'The pinned archive does not have the reviewed INF/catalog layout.'
    }
    # Recheck extracted bytes against the pinned archive, including after elevation.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        if ($null -eq $zip.GetEntry($Config.inf_path.Replace('\', '/')) -or
            $null -eq $zip.GetEntry($Config.catalog_path.Replace('\', '/'))) {
            throw 'The reviewed INF and catalog must both be present in the pinned archive.'
        }
        foreach ($entry in $zip.Entries) {
            if ($entry.FullName -match '[\\/]$') { continue }
            $target = Resolve-Cp210xChild $expanded $entry.FullName
            $stream = $entry.Open()
            $sha = [Security.Cryptography.SHA256]::Create()
            try { $expected = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
            finally { $sha.Dispose(); $stream.Dispose() }
            if ((Get-Cp210xSha256 $target) -ine $expected) {
                throw 'Extracted driver file differs from the pinned archive.'
            }
        }
    } finally { $zip.Dispose() }
    if (-not (Get-Command Get-AuthenticodeSignature -ErrorAction SilentlyContinue)) {
        Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1')
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $catalog
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch '(^|,\s*)CN=(Microsoft Windows Hardware Compatibility Publisher|Silicon Laboratories Inc\.?)(,|$)') {
        throw 'Driver catalog signature is not valid for the expected publisher. Nothing will be installed.'
    }
    $infText = Get-Content -LiteralPath $inf -Raw
    if ($infText -notmatch '(?im)^\s*CatalogFile(?:\.[\w.]+)?\s*=\s*silabser\.cat\s*(?:;.*)?$') {
        throw 'Driver INF does not reference the reviewed signed catalog.'
    }
    return $inf
}

function Install-Cp210xVerified {
    param([string]$InstallRoot, [string]$Stage, $Config)
    $cache = Resolve-Cp210xChild $InstallRoot 'driver-cache'
    $stagePath = [IO.Path]::GetFullPath($Stage)
    if (-not $stagePath.StartsWith($cache + [IO.Path]::DirectorySeparatorChar,
                                  [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Elevated driver stage must be inside this installation driver-cache.'
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal $identity
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Driver installation requires Windows administrator approval.'
    }
    $inf = Assert-Cp210xPackage $stagePath $Config
    $pnputil = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32/pnputil.exe'
    & $pnputil '/add-driver' $inf '/install'
    if ($LASTEXITCODE -notin @(0, 3010)) { throw "Windows driver installation failed (exit $LASTEXITCODE). Ask IT." }
    if ($LASTEXITCODE -eq 3010) { Write-Host 'Windows requests a restart before using the driver.' }
}

function Invoke-Cp210xHelp {
    param([string]$InstallRoot, [switch]$ShowPlan, [string]$VerifiedStage)
    $config = Get-Cp210xConfiguration $InstallRoot
    $ready = $config.available -and ([string]$config.sha256 -match '^[0-9a-fA-F]{64}$')
    if ($ShowPlan) {
        [ordered]@{ name=$config.name; mode=$(if ($ready) { 'optional_verified_install' } else { 'manual_only' });
            automatic_install=$false; archive_available=[bool]$ready; sha256=$config.sha256;
            support_url=$config.support_url; reason=$config.unavailable_reason;
            actions=@('No hardware ports are opened.', 'No driver, download, elevation or browser action in Plan mode.')
        } | ConvertTo-Json -Depth 4
        return
    }
    if (-not $ready) {
        Write-Host 'CP210x USB driver help: no driver is bundled or installed by this release.'
        Write-Host $config.unavailable_reason
        Write-Host 'First check Device Manager / Windows Update. If the CP2102 controller has no COM port, use the official Silicon Labs driver or ask IT.'
        Write-Host 'The scale adapter chipset is unknown: this helper does not choose or install its driver.'
        Write-Host $config.support_url
        if ($VerifiedStage) { throw 'Automatic driver installation is disabled for this release.' }
        $answer = Read-Host 'Open the official Silicon Labs driver page in your browser? [y/N]'
        if ($answer -match '^(?i:y|yes)$') { Start-Process -FilePath $config.support_url }
        return
    }
    if ($VerifiedStage) {
        Install-Cp210xVerified $InstallRoot $VerifiedStage $config
        return
    }
    Write-Host 'Optional CP210x driver setup for a confirmed Silicon Labs CP2102/CP210x controller only. Not for an unidentified scale adapter.'
    Write-Host 'This downloads the official package, checks its pinned SHA256 and signed catalog, then requests Windows administrator approval.'
    $answer = Read-Host 'Download and verify the CP210x driver package? [y/N]'
    if ($answer -notmatch '^(?i:y|yes)$') { Write-Host 'No driver changes requested.'; return }
    $stage = Resolve-Cp210xChild $InstallRoot ('driver-cache/' + [Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $stage
    $archive = Resolve-Cp210xChild $stage 'driver.zip'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $config.url -OutFile $archive -UseBasicParsing -TimeoutSec 60 -MaximumRedirection 0
    Assert-Cp210xArchive $archive $config
    Expand-Cp210xArchive $archive (Resolve-Cp210xChild $stage 'expanded')
    $null = Assert-Cp210xPackage $stage $config
    $answer = Read-Host 'Verified package ready. Request Windows administrator approval to install this CP210x driver? [y/N]'
    if ($answer -notmatch '^(?i:y|yes)$') { Write-Host 'Driver verified; installation cancelled.'; return }
    # Encode quoted literals rather than assembling a shell command line from paths.
    $scriptPath = Resolve-Cp210xChild $InstallRoot 'packaging/install_cp210x.ps1'
    $command = "& '" + $scriptPath.Replace("'", "''") + "' -Root '" +
        $InstallRoot.Replace("'", "''") + "' -ElevatedStage '" + $stage.Replace("'", "''") + "'"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $powershell = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $process = Start-Process -FilePath $powershell -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded) -Verb RunAs -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Elevated driver helper exited $($process.ExitCode). Ask IT or use the official vendor page." }
    Write-Host 'Driver setup finished. Reconnect the controller and check its COM port in Device Manager.'
}

if ($DefinitionsOnly) { return }
if ([string]::IsNullOrWhiteSpace($Root)) { $Root = Split-Path -Parent $PSScriptRoot }
try { Invoke-Cp210xHelp -InstallRoot $Root -ShowPlan:$Plan -VerifiedStage $ElevatedStage }
catch {
    Write-Error ("CP210x setup stopped: " + $_.Exception.Message + "`nOfficial help: https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers`nNo unverified driver is installed. Use the vendor instructions or ask IT.") -ErrorAction Continue
    exit 1
}
