@echo off
setlocal
if exist "%~dp0dist\Sekiro Resource Modifier.exe" (
 start "Sekiro Resource Modifier" "%~dp0dist\Sekiro Resource Modifier.exe"
 exit /b 0
)
if exist "%~dp0Sekiro Resource Modifier.exe" (
 start "Sekiro Resource Modifier" "%~dp0Sekiro Resource Modifier.exe"
 exit /b 0
)
where py >nul 2>nul
if not errorlevel 1 (
 start "Sekiro Resource Modifier" pyw -3 -B "%~dp0app\gui.py"
 exit /b 0
)
where pythonw >nul 2>nul
if not errorlevel 1 (
 start "Sekiro Resource Modifier" pythonw -B "%~dp0app\gui.py"
 exit /b 0
)
echo Download the Windows portable EXE from the repository Releases page.
echo No Python installation is needed for the portable version.
pause
exit /b 1
