@echo off
REM Tao shortcut "Tien Len Bot" tren Desktop.
REM Chay 1 lan. Double-click shortcut de khoi dong bot.

set "SCRIPT_DIR=%~dp0"
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\Tien Len Bot.lnk"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$sc = $ws.CreateShortcut('%SHORTCUT%'); " ^
  "$sc.TargetPath = '%SCRIPT_DIR%run.bat'; " ^
  "$sc.WorkingDirectory = '%SCRIPT_DIR%'; " ^
  "$sc.Description = 'Khoi dong Bot Tien Len Mien Nam'; " ^
  "$sc.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo === DA TAO SHORTCUT THANH CONG ===
    echo Shortcut: %SHORTCUT%
    echo Double-click "Tien Len Bot" tren Desktop de chay bot.
    echo.
) else (
    echo [LOI] Khong tao duoc shortcut. Thu chay voi quyen Admin.
)
pause
