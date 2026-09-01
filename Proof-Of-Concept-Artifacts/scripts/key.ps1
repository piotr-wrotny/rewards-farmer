# key.ps1 — klawisze systemowe
# usage: .\key.ps1 BACK   (BACK|HOME|ENTER)
param([ValidateSet("BACK","HOME","ENTER")][string]$Key = "BACK")
$ADB = "./bin/platform-tools/adb.exe"
$SERIAL = "127.0.0.1:15555"
$map = @{ BACK = 4; HOME = 3; ENTER = 66 }
& $ADB -s $SERIAL shell input keyevent $map[$Key]
