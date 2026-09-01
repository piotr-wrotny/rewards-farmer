# Bing profile factory: interactive login via scrcpy + snapshot back into variants.
# Runs on the Windows dev machine. The AGENT NEVER SEES CREDENTIALS — you type them
# into the scrcpy window. Server side: redroid-factory container (127.0.0.1:5556).
param(
  [Parameter(Position=0)][string]$Cmd,
  [Parameter(Position=1)][string]$Name
)
$ErrorActionPreference = "Stop"
$Server = "piotr.wrotny@10.17.103.115"
$Adb    = "bin/platform-tools/adb.exe"
$Scrcpy = "bin/scrcpy/scrcpy.exe"

function Ensure-Tunnel([int]$Local, [int]$Remote) {
  if (Get-NetTCPConnection -LocalPort $Local -State Listen -ErrorAction SilentlyContinue) { return }
  Start-Process -WindowStyle Hidden ssh -ArgumentList "-N","-L","${Local}:127.0.0.1:${Remote}",$Server
  Start-Sleep 2
}

switch ($Cmd) {
  login {
    if (-not $Name) { Write-Host "usage: factory.ps1 login <profile-name>"; exit 2 }
    Ensure-Tunnel 15556 5556
    & $Adb connect 127.0.0.1:15556 | Out-Null
    # every profile starts from the same clean baseline
    ssh $Server "adb -s 127.0.0.1:5556 shell pm clear com.microsoft.bing"
    Write-Host ">> scrcpy will open: log into the Microsoft account for profile '$Name'."
    & $Scrcpy -s 127.0.0.1:15556 --window-title "bing-factory login: $Name"
    Write-Host ">> when the account is visible in Bing (profile tab), run: .\scripts\factory.ps1 save $Name"
  }
  save {
    if (-not $Name) { Write-Host "usage: factory.ps1 save <profile-name>"; exit 2 }
    Ensure-Tunnel 15556 5556
    # freeze order force-stop -> sync -> stop -> tar -> start lives in bing.sh snapshot
    ssh $Server "cd ~/rewards-farmer-main && ./bing.sh snapshot $Name"
    New-Item -ItemType Directory -Force profile-snapshots | Out-Null
    scp "${Server}:profile-snapshots/$Name.tar.gz" "profile-snapshots/"
    # reset factory to baseline for the next profile
    ssh $Server "adb -s 127.0.0.1:5556 shell pm clear com.microsoft.bing"
    Write-Host "saved '$Name': server snapshot + local copy under profile-snapshots/."
    Write-Host "next: create the variant + add a row to profiles/README.md (see registry header for the one-liner)."
  }
  default { Write-Host "usage: factory.ps1 login|save <profile-name>"; exit 2 }
}
