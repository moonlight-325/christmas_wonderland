@echo off
REM Build with PyInstaller (onedir). Output: dist\ChristmasWonderland\ChristmasWonderland.exe
REM Run this script on Windows. PyInstaller cannot build Windows executables on other operating systems.

python -m pip install -r requirements.txt pyinstaller

pyinstaller --noconfirm --clean --windowed --name ChristmasWonderland ^
  --icon assets\icon.ico ^
  --add-data "assets;assets" ^
  main.py

REM Copy the gifts folder (external Advent Calendar programs) next to the executable if it exists.
REM If it does not exist, create an empty folder instead.
if exist gifts (xcopy /E /I /Y gifts dist\ChristmasWonderland\gifts >nul) else (mkdir dist\ChristmasWonderland\gifts)

REM The data folder (settings.json and backups) is created next to the executable at runtime.
REM If the installation directory is not writable, the application automatically uses:
REM %APPDATA%\ChristmasWonderland\data

pause