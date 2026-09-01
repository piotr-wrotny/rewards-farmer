# tap.ps1 — tapnięcie po współrzędnych
# usage: .\tap.ps1 360 746
param([int]$X, [int]$Y)
$ADB = "./bin/platform-tools/adb.exe"
$SERIAL = "127.0.0.1:15555"
& $ADB -s $SERIAL shell input tap $X $Y
