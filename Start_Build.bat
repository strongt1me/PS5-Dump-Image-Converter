@echo off
:: PS5 Dump & Image Converter - EXE Build Starter
:: One-Click Release: Build ohne Pflicht-Signierung

cd /d "%~dp0"

echo.
echo =============================================
echo   PS5 Dump ^& Image Converter - RELEASE
echo =============================================
echo   Modus: Build
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build_EXE.ps1"
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
	echo.
	echo [FEHLER] Release-Build fehlgeschlagen. Exit-Code: %RC%
	echo          Pruefe Build-Logs und Voraussetzungen.
	echo.
	pause
	exit /b %RC%
)

echo.
echo [OK] Release-Build erfolgreich.
echo.
pause
exit /b 0
