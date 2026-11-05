@echo off
setlocal
cd /d "%~dp0."

set "PY=%~dp0runtime\python.exe"
set "READY=%~dp0runtime\portable-ready.txt"
if exist "%PY%" if exist "%READY%" goto launch_app
goto bootstrap_runtime

:launch_app
"%PY%" -c "import evaluator, openpyxl" >nul 2>nul
if errorlevel 1 goto repair_runtime

echo Starting UT Review. Keep this window open while using the app.
"%PY%" -m evaluator --project "%USERPROFILE%\UT Inspection Evaluator"
if errorlevel 1 echo UT Review stopped with an error.
pause
exit /b

:repair_runtime
echo The bundled runtime is incomplete. Recreating it now.
if exist "%READY%" del /q "%READY%"
goto bootstrap_runtime

:bootstrap_runtime
echo Preparing the portable runtime on this computer. This happens only once.
echo The first setup needs internet access and a writable copy of this folder.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\Setup-Windows-Portable.ps1" -Root "%~dp0."
if errorlevel 1 goto setup_error
if not exist "%PY%" goto setup_error
if not exist "%READY%" goto setup_error
goto launch_app

:setup_error
echo First-run setup did not finish. Check the PowerShell message above.
echo Confirm this folder is writable and has internet access, then try again.
pause
exit /b 1
