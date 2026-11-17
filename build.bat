@echo off
REM PyInstaller 빌드 (onedir). 결과: dist\ChristmasWonderland\ChristmasWonderland.exe
REM 반드시 Windows 에서 실행하세요 (PyInstaller 는 다른 OS 용 exe 를 만들 수 없습니다).
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --windowed --name ChristmasWonderland ^
  --icon assets\icon.ico ^
  --add-data "assets;assets" ^
  main.py
REM gifts\ 폴더(어드벤트 선물 외부 프로그램)가 있으면 exe 옆으로 복사합니다. 없으면 빈 폴더만 만듭니다.
if exist gifts (xcopy /E /I /Y gifts dist\ChristmasWonderland\gifts >nul) else (mkdir dist\ChristmasWonderland\gifts)
REM data\ 폴더(settings.json, backups)는 exe 옆에 런타임에 생성됩니다.
REM 쓰기 불가 위치에 설치하면 %%APPDATA%%\ChristmasWonderland\data 로 자동 대체됩니다.
pause
