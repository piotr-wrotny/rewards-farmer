# connect.ps1 — otwiera tunel SSH i łączy adb
# usage: .\connect.ps1 [-Host_ user@10.17.103.115]
param([string]$Host_ = "piotr.wrotny@10.17.103.115")
$ADB = "./bin/platform-tools/adb.exe"
$SERIAL = "127.0.0.1:15555"
Start-Process ssh -ArgumentList "-N","-L","15555:127.0.0.1:5555",$Host_ -WindowStyle Hidden
Start-Sleep 2
& $ADB connect $SERIAL
& $ADB devices
