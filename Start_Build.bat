@echo off
setlocal
::: PS5 Dump & Image Converter v1.9.2 - EXE Build Starter
:: One-Click Release: startet den vollstaendigen Windows-Build ohne manuelle Execution Policy.
cd /d "%~dp0"
echo.
echo =============================================
echo   PS5 Dump ^& Image Converter - RELEASE
echo   Version: v1.9.2
echo =============================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build_EXE.ps1"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo [FEHLER] Release-Build fehlgeschlagen. Exit-Code: %RC%
    echo          Pruefe die Meldungen oben sowie die Build-Voraussetzungen.
    echo.
    pause
    exit /b %RC%
)
echo.
echo [OK] Release-Build erfolgreich.
echo.
pause
exit /b 0
