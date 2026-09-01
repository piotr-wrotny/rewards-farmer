# ui-dump.ps1 — UI hierarchy do artifacts/ui
# usage: .\ui-dump.ps1 window-moj.xml
param([string]$Name = "window.xml")
$ADB = "./bin/platform-tools/adb.exe"
$SERIAL = "127.0.0.1:15555"
New-Item -ItemType Directory -Force -Path "artifacts/ui" | Out-Null
& $ADB -s $SERIAL shell uiautomator dump /sdcard/window.xml | Out-Null
& $ADB -s $SERIAL pull /sdcard/window.xml "artifacts/ui/$Name" | Out-Null
Write-Host "Zapisano artifacts/ui/$Name"
