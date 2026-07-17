@echo off
REM ============================================================
REM  Acid Zero - flash the ESP32 All-in-One co-processor (Windows)
REM  (CC1101 + IR merged onto one 38-pin board)
REM  Usage:  flash-allinone-windows.bat COM6
REM  (defaults to COM6 if no port is given)
REM ============================================================
setlocal
set "PORT=%~1"
if "%PORT%"=="" set "PORT=COM6"
set "BIN=%~dp0esp32-allinone\prebuilt\esp32-allinone.merged.bin"

if not exist "%BIN%" (
  echo ERROR: firmware image not found: "%BIN%"
  exit /b 1
)

echo Flashing "%BIN%"
echo      to  %PORT%  at 921600 baud ...
esptool --chip esp32 -p %PORT% -b 921600 write_flash 0x0 "%BIN%"
if errorlevel 1 (
  echo.
  echo esptool not found on PATH - retrying via "python -m esptool" ...
  python -m esptool --chip esp32 -p %PORT% -b 921600 write_flash 0x0 "%BIN%"
)
endlocal
