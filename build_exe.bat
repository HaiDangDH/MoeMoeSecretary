@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ==============================================
echo   Moe Moe Secretary - dong goi thanh file .exe
echo ==============================================

rem --- Tim Python 3.11+ (uu tien 3.12 / 3.11 / 3.13) ---
set "PY="
for %%V in (3.12 3.11 3.13) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [LOI] Khong tim thay Python 3.11 tro len. Hay cai tai https://www.python.org/downloads/
    goto :error
)
echo Dung Python: %PY%

rem --- Moi truong ao + thu vien ---
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv || goto :error
)
call ".venv\Scripts\activate.bat" || goto :error
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt -r requirements-dev.txt || goto :error

rem --- Icon (tao neu chua co) ---
if not exist "assets\icon.ico" python tools\make_icon.py

rem --- Build: onefile + windowed (console=False trong file .spec) ---
pyinstaller --noconfirm --clean MoeMoeSecretary.spec || goto :error

echo.
echo ==============================================
echo   XONG!  File: dist\MoeMoeSecretary.exe
echo   Chay thu, roi (tuy chon) do tai nguyen:
echo     python tools\measure_resources.py
echo ==============================================
pause
exit /b 0

:error
echo.
echo [LOI] Build that bai - xem thong bao phia tren.
pause
exit /b 1
