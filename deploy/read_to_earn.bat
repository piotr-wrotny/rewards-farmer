@echo off
REM Read to Earn — uruchomienie przeplywu na VM
REM Ustaw, jesli adb server jest na innej maszynie:
REM set ADB_SERVER_SOCKET=tcp:10.x.x.x:5037
cd /d "%~dp0"
python read_to_earn.py emulator-5554 >> read_to_earn.log 2>&1
