# screenshot.ps1 — zrzut ekranu do artifacts/screenshots
# usage: .\screenshot.ps1 06-moje-zrzut.png
# Uwaga: NIE używamy `exec-out screencap >` — PowerShell psuje binarną transmisję (UTF-16 BOM).
# Bezpieczna droga: screencap na urządzeniu, potem adb pull.
param([string]$Name = "shot.png")
$ADB = "./bin/platform-tools/adb.exe"
$SERIAL = "127.0.0.1:15555"
New-Item -ItemType Directory -Force -Path "artifacts/screenshots" | Out-Null
& $ADB -s $SERIAL shell "screencap -p /sdcard/_shot.png"
& $ADB -s $SERIAL pull /sdcard/_shot.png "artifacts/screenshots/$Name" | Out-Null
& $ADB -s $SERIAL shell rm /sdcard/_shot.png
Write-Host "Zapisano artifacts/screenshots/$Name"
