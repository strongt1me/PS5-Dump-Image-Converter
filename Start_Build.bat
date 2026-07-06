@echo off
:: PS5 Dump & Image Converter - EXE Build Starter
:: One-Click Release: Build + EV-Signierung (Signatur ist Pflicht)

cd /d "%~dp0"

echo.
echo =============================================
echo   PS5 Dump ^& Image Converter - RELEASE
echo =============================================
echo   Modus: Build + EV-Signierung (Pflicht)
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build_EXE.ps1" -SignEV -RequireSignature
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
	echo.
	echo [FEHLER] Release-Build fehlgeschlagen. Exit-Code: %RC%
	echo          Pruefe EV-Token, Zertifikat und Signatur-Logs.
	echo.
	pause
	exit /b %RC%
)

echo.
echo [OK] Release-Build inkl. Signierung erfolgreich.
echo.
pause
exit /b 0
