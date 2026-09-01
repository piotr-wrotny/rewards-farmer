# text.ps1 — wpisanie tekstu w aktywne pole
# usage: .\text.ps1 "hello"
param([string]$Text)
$ADB = "./bin/platform-tools/adb.exe"
$SERIAL = "127.0.0.1:15555"
& $ADB -s $SERIAL shell input text $Text
