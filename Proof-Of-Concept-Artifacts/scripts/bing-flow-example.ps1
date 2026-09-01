# Referencyjny przepływ end-to-end: launch Bing → FRE → home → search → wyniki
# usage: .\bing-flow-example.ps1 -Query "hello"
param([string]$Query = "hello")
$RepoRoot = Split-Path (Split-Path $PSScriptRoot)
$S = "127.0.0.1:15555"
$ADB = Join-Path $RepoRoot "bin/platform-tools/adb.exe"
function Adb { & $ADB -s $S @args }

function Get-Focus {
    (Adb shell dumpsys window | Select-String "mCurrentFocus").Line.Trim()
}
function Wait-ForActivity([string]$Activity, [int]$TimeoutSec = 20) {
    for ($i = 0; $i -lt ($TimeoutSec * 2); $i++) {
        if ((Get-Focus) -match [regex]::Escape($Activity)) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}
function Get-Bounds([string]$ResourceId) {
    Adb shell uiautomator dump /sdcard/window.xml | Out-Null
    Adb pull /sdcard/window.xml "$env:TEMP\window.xml" | Out-Null
    $xml = [xml](Get-Content "$env:TEMP\window.xml" -Raw)
    $node = $xml.hierarchy.SelectSingleNode("//*[@resource-id='$ResourceId']")
    if (-not $node) { throw "Nie znaleziono: $ResourceId" }
    $b = ($node.bounds -replace '[\[\]]',' ') -split '\s+' | Where-Object { $_ }
    return "$(([int]$b[0]+[int]$b[2])/2) $(([int]$b[1]+[int]$b[3])/2)"
}
Write-Host "== Launch =="
Adb shell am start -n "com.microsoft.bing/com.microsoft.sapphire.app.main.SapphireMainActivity"
Start-Sleep 5
Get-Focus

Write-Host "== FRE =="
if (Wait-ForActivity "BingAppGlobalFreActivity" 8) {
    $maybe = Get-Bounds "com.microsoft.bing:id/sapphire_fre_bing_no_button"
    Adb shell input tap $maybe
    Start-Sleep 8
    Write-Host "FRE pominięty"
}
if (Wait-ForActivity "MainSapphireActivity" 20) { Write-Host "== Home OK ==" } else { throw "Nie dotarłem do home" }

# Wróć do home: jeśli apka siedzi na sub-ekranie (np. Rewards/Profile), relaunch + ewentualny BACK
Adb shell uiautomator dump /sdcard/window.xml | Out-Null
Adb pull /sdcard/window.xml "$env:TEMP\w.xml" | Out-Null
if (-not (Select-String -Path "$env:TEMP\w.xml" -Pattern 'sa_search_box' -Quiet)) {
    Adb shell am start -n "com.microsoft.bing/com.microsoft.sapphire.app.main.SapphireMainActivity"
    Start-Sleep 8
}
Write-Host "== Search =="
$box = Get-Bounds "com.microsoft.bing:id/sa_search_box"
Adb shell input tap $box

Start-Sleep 3
Adb shell input text $Query
Start-Sleep 2
Adb shell input keyevent 66   # ENTER
Start-Sleep 8
New-Item -ItemType Directory -Force -Path "artifacts/screenshots","artifacts/ui" | Out-Null
Adb shell "screencap -p /sdcard/flow-results.png"
Adb pull /sdcard/flow-results.png "artifacts/screenshots/flow-results.png" | Out-Null
Adb shell uiautomator dump /sdcard/window.xml | Out-Null
Adb pull /sdcard/window.xml "artifacts/ui/flow-results.xml" | Out-Null
Write-Host "== Done =="
