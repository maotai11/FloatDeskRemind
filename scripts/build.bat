@echo off
:: ==========================================
:: FloatDesk Remind - Build EXE
:: onedir mode: output is dist\FloatDeskRemind\
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

echo [2/3] Verifying output...
if not exist "dist\FloatDeskRemind\FloatDeskRemind.exe" (
    echo.
    echo ERROR: dist\FloatDeskRemind\FloatDeskRemind.exe not found after build.
    echo Build may have silently failed.
    pause
    exit /b 1
)

echo [3/3] Build successful.
echo.
echo EXE location : dist\FloatDeskRemind\FloatDeskRemind.exe
for %%F in ("dist\FloatDeskRemind\FloatDeskRemind.exe") do echo EXE timestamp : %%~tF
for %%F in ("dist\FloatDeskRemind\FloatDeskRemind.exe") do echo EXE size      : %%~zF bytes
echo.
echo To distribute: zip the entire dist\FloatDeskRemind\ folder.
echo.
pause
