@echo off
:: PS5 Dump & Image Converter - EXE Build Starter
:: Einfach per Doppelklick ausfuehren!
:: Startet Build_EXE.ps1 automatisch mit Bypass-ExecutionPolicy

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build_EXE.ps1"
