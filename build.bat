@echo off
setlocal
cd /d "%~dp0"
title QuickInvoice build

echo === Installing Python requirements ===
python -m pip install --upgrade -r requirements.txt pyinstaller || goto :fail

echo.
echo === Building QuickInvoice.exe ===
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name QuickInvoice ^
  --icon assets\icon.ico ^
  --add-data "assets\icon.png;assets" ^
  quickinvoice.py || goto :fail

echo.
echo === Finding Inno Setup ===
call :find_iscc
if not defined ISCC (
  echo Inno Setup not found - installing it with winget...
  winget install --id JRSoftware.InnoSetup -e --silent --accept-source-agreements --accept-package-agreements
  call :find_iscc
)
if not defined ISCC (
  echo Couldn't find Inno Setup. The plain exe is in dist\QuickInvoice.exe
  goto :done
)

echo.
echo === Building installer ===
"%ISCC%" installer.iss || goto :fail
echo.
echo Installer is in the "installer" folder.
goto :done

:find_iscc
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC for /f "delims=" %%I in ('where iscc 2^>nul') do set "ISCC=%%I"
exit /b 0

:fail
echo.
echo *** Build failed ***
pause
exit /b 1

:done
pause
