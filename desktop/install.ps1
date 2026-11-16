# Installs Freakyyy Desktop for the current user (no admin rights needed).
#   powershell -ExecutionPolicy Bypass -File install.ps1 [-StartWithWindows]
param([switch]$StartWithWindows)
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
# Run from the project folder: install the built app, never the source tree.
if (-not (Test-Path (Join-Path $src "Freakyyy.exe"))) { $src = Join-Path $PSScriptRoot "dist\Freakyyy" }
if (-not (Test-Path (Join-Path $src "Freakyyy.exe"))) { throw "Freakyyy.exe not found. Run build.ps1 first." }
$dst = Join-Path $env:LOCALAPPDATA "Programs\Freakyyy"

Get-Process Freakyyy -ErrorAction SilentlyContinue | Stop-Process -Force
Wait-Process -Name Freakyyy -Timeout 20 -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $dst | Out-Null
# The exe can stay locked for a moment after exit (or while antivirus scans it): retry, then verify.
for ($i = 1; $i -le 10; $i++) {
    try { Copy-Item -Recurse -Force (Join-Path $src "*") $dst -ErrorAction Stop; break }
    catch { if ($i -eq 10) { throw }; Start-Sleep 3 }
}
if ((Get-FileHash (Join-Path $src "Freakyyy.exe")).Hash -ne (Get-FileHash (Join-Path $dst "Freakyyy.exe")).Hash) {
    throw "Freakyyy.exe didn't update. Close Freakyyy and run the installer again."
}

# The app used to be called Dexter: remove that copy, its shortcuts and its startup entry.
# (Settings, memory and pairing are copied to %APPDATA%\Freakyyy on first run; %APPDATA%\Dexter is left as a backup.)
Get-Process Dexter -ErrorAction SilentlyContinue | Stop-Process -Force
Wait-Process -Name Dexter -Timeout 20 -ErrorAction SilentlyContinue
$old = Join-Path $env:LOCALAPPDATA "Programs\Dexter"
if (Test-Path (Join-Path $old "Dexter.exe")) { Remove-Item -Recurse -Force $old -ErrorAction SilentlyContinue }
foreach ($l in @((Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Dexter.lnk"),
                 (Join-Path ([Environment]::GetFolderPath("Desktop")) "Dexter.lnk"))) {
    if (Test-Path $l) { Remove-Item -Force $l }
}
$run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$hadStartup = $null -ne (Get-ItemProperty $run -Name "Dexter" -ErrorAction SilentlyContinue)
if ($hadStartup) { Remove-ItemProperty $run -Name "Dexter"; $StartWithWindows = $true }

$shell = New-Object -ComObject WScript.Shell
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Freakyyy.lnk"
$lnk = $shell.CreateShortcut($startMenu)
$lnk.TargetPath = Join-Path $dst "Freakyyy.exe"
$lnk.WorkingDirectory = $dst
$lnk.Description = "Freakyyy - voice-first personal AI assistant"
$lnk.Save()
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "Freakyyy.lnk"
Copy-Item -Force $startMenu $desktop

if ($StartWithWindows) {
    Set-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Freakyyy" -Value "`"$dst\Freakyyy.exe`" --background"
}

Write-Host "Freakyyy installed to $dst. Start it from the Start menu or the desktop shortcut."
Write-Host "When Windows Firewall asks, allow Freakyyy on PRIVATE networks so your phone can connect."
