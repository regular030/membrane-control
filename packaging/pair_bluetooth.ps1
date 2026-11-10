[CmdletBinding()]
param([string]$Port = '')

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

try {
    if (!$Port) { $Port = Read-Host 'Wired USB-to-UART COM port (COM5 on the lab PC)' }
    $Port = $Port.Trim().ToUpperInvariant()
    if ($Port -notmatch '^COM[1-9][0-9]{0,3}$') { throw 'Enter a wired COM port such as COM5.' }
    $serial = New-Object IO.Ports.SerialPort($Port, 115200)
    try {
        $serial.DtrEnable = $false
        $serial.RtsEnable = $false
        $serial.ReadTimeout = 500
        $serial.WriteTimeout = 1000
        Write-Host 'Stop the rig and disconnect Membrane Control before pairing.'
        Write-Host 'Isolate the valve and pump loads. Pairing restarts the ESP32. Leave the board running with BOOT released.'
        $serial.Open()
        if ((Read-Host 'Type PAIR to replace the controller pairing') -cne 'PAIR') { return }
        $serial.DiscardInBuffer()
        $serial.WriteLine('')
        $serial.WriteLine('PAIR')
        Write-Host 'Waiting for the controller to start pairing mode.'
        $deadline = [DateTime]::UtcNow.AddSeconds(140)
        while ([DateTime]::UtcNow -lt $deadline) {
            try { $line = $serial.ReadLine().Trim() }
            catch [TimeoutException] { continue }
            if ($line -eq 'Bluetooth: pairing ready (120 seconds)') {
                Write-Host 'In Windows, open Bluetooth & devices, choose Add device, then select MembraneControl-Bench.'
            } elseif ($line -match '^Bluetooth pairing code: ([0-9]{6})$') {
                $code = $Matches[1]
                Write-Host "ESP32 pairing code: $code"
                $confirmation = Read-Host 'If Windows shows the same code, accept it there and type the six digits here'
                if ($confirmation -cne $code) { throw 'Code was not confirmed. Wait for pairing mode to expire before retrying.' }
                $serial.WriteLine("CONFIRM $confirmation")
            } elseif ($line -eq 'Bluetooth: pairing saved; restarting normal mode') {
                Write-Host 'Pairing saved. Close Windows Settings and connect through the outgoing port in Membrane Control.'
                return
            } elseif ($line -eq 'Bluetooth: stop the controller before USB pairing' -or
                      $line -match '^Bluetooth: pairing (failed|timed out|refused|requires)') {
                throw $line
            } elseif ($line -match '^(Bluetooth|Pairing)') {
                Write-Host $line
            }
        }
        throw 'Pairing was not confirmed. Check that the board is running the normal firmware with USB pairing support.'
    } finally {
        $serial.Dispose()
    }
} catch {
    Write-Host $_.Exception.Message
} finally {
    [void](Read-Host 'Press Enter to close')
}
