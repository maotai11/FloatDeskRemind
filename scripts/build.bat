@echo off
:: ==========================================
:: FloatDesk Remind - Build EXE
:: ==========================================
cd /d "%~dp0.."

echo [1/3] Running PyInstaller...
pyinstaller FloatDeskRemind.spec --noconfirm
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: PyInstaller failed with exit code %ERRORLEVEL%
    echo Build aborted.
    pause
    exit /b %ERRORLEVEL%
)

echo [2/3] Verifying output EXE...
if not exist "dist\FloatDeskRemind.exe" (
    echo.
    echo ERROR: dist\FloatDeskRemind.exe not found after build.
    echo Build may have silently failed.
    pause
    exit /b 1
)

echo [3/3] Build successful.
echo.
echo EXE location : dist\FloatDeskRemind.exe
for %%F in ("dist\FloatDeskRemind.exe") do echo EXE timestamp : %%~tF
for %%F in ("dist\FloatDeskRemind.exe") do echo EXE size      : %%~zF bytes
echo.
pause
