# Removes Freakyyy Desktop. Add -RemoveData to also delete settings, history and paired-device keys.
param([switch]$RemoveData)
Get-Process Freakyyy -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -Recurse -Force (Join-Path $env:LOCALAPPDATA "Programs\Freakyyy") -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Freakyyy.lnk") -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path ([Environment]::GetFolderPath("Desktop")) "Freakyyy.lnk") -ErrorAction SilentlyContinue
Remove-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Freakyyy" -ErrorAction SilentlyContinue
if ($RemoveData) {
    Remove-Item -Recurse -Force (Join-Path $env:APPDATA "Freakyyy") -ErrorAction SilentlyContinue
    cmdkey /list | Select-String "Freakyyy" | ForEach-Object {
        $target = ($_ -split "Target: ")[1]
        if ($target) { cmdkey /delete:$target | Out-Null }
    }
}
Write-Host "Freakyyy removed."
