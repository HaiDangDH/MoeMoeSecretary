@echo off
rem ============================================================================
rem  Moe Moe Secretary - cap nhat ma nguon tu file .zip roi dong goi lai .exe
rem
rem  Cach dung:
rem    1) Keo tha file .zip ban cap nhat len bieu tuong update_and_build.bat
rem    2) hoac bam dup file nay roi keo tha / nhap duong dan .zip khi duoc hoi
rem    3) hoac:  update_and_build.bat "C:\duong dan\MoeMoeSecretary-updated.zip"
rem
rem  File .zip phai la ban day du cua du an (co main.py va thu muc src).
rem
rem  KHONG BAO GIO bi dong toi: config.yaml, cache\, dist\, .venv\ hoac venv\.
rem  config.yaml hien co duoc sao luu vao backup\ truoc, ban mau cua ban cap nhat
rem  duoc luu thanh config.yaml.new de ban doi chieu cac muc moi.
rem ============================================================================
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "ROOT=%CD%"
set "TMPDIR=%ROOT%\.update_tmp"
set "SYNC_FAIL="

echo ==============================================
echo   Moe Moe Secretary - cap nhat va build .exe
echo ==============================================
echo.

rem --- 1. Lay duong dan file .zip (tham so %1 khi keo tha, hoac nhap tay) ---
set "ZIP=%~1"
if defined ZIP goto :zip_given
echo Keo tha file .zip ban cap nhat vao cua so nay (hoac go duong dan) roi nhan Enter.
set /p "ZIP=File .zip: "
:zip_given
if not defined ZIP goto :err_nozip

rem Bo dau ngoac kep, khoang trang thua o dau/cuoi (keo tha vao cua so thuong them chung)
set "ZIP=%ZIP:"=%"
:zip_trim_end
if not defined ZIP goto :err_nozip
if not "%ZIP:~-1%"==" " goto :zip_trim_start
set "ZIP=%ZIP:~0,-1%"
goto :zip_trim_end
:zip_trim_start
if not defined ZIP goto :err_nozip
if not "%ZIP:~0,1%"==" " goto :zip_trimmed
set "ZIP=%ZIP:~1%"
goto :zip_trim_start
:zip_trimmed
for %%I in ("%ZIP%") do set "ZIP=%%~fI"

if /i not "%ZIP:~-4%"==".zip" goto :err_notzip
if not exist "%ZIP%" goto :err_missing
echo File cap nhat : "%ZIP%"
echo Thu muc du an : "%ROOT%"
echo.

rem --- 2. Canh bao neu ung dung dang chay (file .exe dang mo se khong ghi de duoc) ---
tasklist /FI "IMAGENAME eq MoeMoeSecretary.exe" 2>nul | find /I "MoeMoeSecretary.exe" >nul
if errorlevel 1 goto :not_running
echo [CANH BAO] MoeMoeSecretary.exe dang chay. Hay thoat no (chuot phai nhan vat ^> Thoat)
echo            truoc khi build, neu khong file .exe moi se khong ghi de duoc.
pause
:not_running

rem --- 3. Sao luu config.yaml TRUOC khi giai nen / ghi de bat ky thu gi ---
set "STAMP=backup"
for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss" 2^>nul`) do set "STAMP=%%T"
if not exist "config.yaml" goto :no_config
if not exist "backup" mkdir "backup"
copy /y "config.yaml" "backup\config_%STAMP%.yaml" >nul
if errorlevel 1 goto :err_backup
echo [1/5] Da sao luu config.yaml -^> backup\config_%STAMP%.yaml
goto :extract
:no_config
echo [1/5] Chua co config.yaml - bo qua buoc sao luu.

rem --- 4. Giai nen vao thu muc tam ---
:extract
if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%"
mkdir "%TMPDIR%"
set "UPD_ZIP=%ZIP%"
set "UPD_DST=%TMPDIR%"
echo [2/5] Dang giai nen...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath $env:UPD_ZIP -DestinationPath $env:UPD_DST -Force" >nul 2>nul
if not errorlevel 1 goto :extracted
echo       PowerShell khong giai nen duoc, thu lai bang tar...
tar -xf "%ZIP%" -C "%TMPDIR%"
if errorlevel 1 goto :err_extract
:extracted

rem Ban cap nhat co the nam ngay o goc zip hoac trong mot thu muc con (vi du MoeMoeSecretary\)
set "SRC="
if exist "%TMPDIR%\main.py" set "SRC=%TMPDIR%"
if not defined SRC for /d %%D in ("%TMPDIR%\*") do if exist "%%~fD\main.py" set "SRC=%%~fD"
if not defined SRC goto :err_layout
if not exist "%SRC%\src\controller.py" goto :err_layout

rem --- 5. Dong bo ma nguon (khong xoa gi o dich; KHONG dong toi config.yaml / cache / dist / venv) ---
echo [3/5] Dang cap nhat ma nguon...
for %%S in (src assets tools tests) do call :syncdir %%S
for %%F in (main.py MoeMoeSecretary.spec requirements.txt requirements-dev.txt build_exe.bat README.md .gitignore) do call :syncfile %%F
if defined SYNC_FAIL goto :err_sync

rem config mau cua ban cap nhat duoc luu thanh config.yaml.new (de doi chieu, khong ghi de config.yaml cua ban)
if exist "%SRC%\config.yaml" copy /y "%SRC%\config.yaml" "%ROOT%\config.yaml.new" >nul
if exist "%SRC%\config.yaml" echo       config.yaml cua ban GIU NGUYEN; ban mau moi: config.yaml.new

rem File .bat nay khong tu ghi de len chinh no khi dang chay (cmd doc lenh tung dong, ghi de se hong)
if not exist "%SRC%\update_and_build.bat" goto :self_done
fc /b "%SRC%\update_and_build.bat" "%~f0" >nul 2>nul
if errorlevel 1 goto :self_new
goto :self_done
:self_new
copy /y "%SRC%\update_and_build.bat" "%ROOT%\update_and_build.bat.new" >nul
echo       Co ban update_and_build.bat moi -^> update_and_build.bat.new (doi ten de dung o lan sau)
:self_done

rem --- 6. Moi truong ao + thu vien ---
echo [4/5] Dang chuan bi moi truong Python va thu vien...
set "VENV="
if exist ".venv\Scripts\activate.bat" set "VENV=.venv"
if not defined VENV if exist "venv\Scripts\activate.bat" set "VENV=venv"
if defined VENV goto :have_venv

rem Chua co moi truong ao: tao .venv moi (tim Python 3.11+ giong build_exe.bat)
set "PY="
for %%V in (3.12 3.11 3.13) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
    )
)
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto :err_python
%PY% -m venv .venv
if errorlevel 1 goto :error
set "VENV=.venv"
:have_venv
echo       Dung moi truong ao: %VENV%
call "%VENV%\Scripts\activate.bat"
if errorlevel 1 goto :error
python -m pip install -q -r requirements.txt -r requirements-dev.txt
if errorlevel 1 goto :error

rem --- 7. Don thu muc build tam roi dong goi lai .exe ---
echo [5/5] Dang dong goi .exe (mat vai phut)...
if exist "build" rmdir /s /q "build"
if not exist "assets\icon.ico" python tools\make_icon.py
pyinstaller --noconfirm --clean MoeMoeSecretary.spec
if errorlevel 1 goto :error

if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%"
echo.
echo ==============================================
echo   XONG!  File moi: dist\MoeMoeSecretary.exe
echo   - config.yaml cua ban giu nguyen (ban sao luu: thu muc backup\)
echo   - Muc cau hinh moi (neu co) xem them trong config.yaml.new
echo ==============================================
pause
exit /b 0

rem ----------------------------------------------------------------------------
:syncdir
if not exist "%SRC%\%~1" exit /b 0
robocopy "%SRC%\%~1" "%ROOT%\%~1" /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 set "SYNC_FAIL=1"
echo       da dong bo thu muc %~1\
exit /b 0

:syncfile
if not exist "%SRC%\%~1" exit /b 0
copy /y "%SRC%\%~1" "%ROOT%\%~1" >nul
if errorlevel 1 set "SYNC_FAIL=1"
echo       da cap nhat %~1
exit /b 0

rem ----------------------------------------------------------------------------
:err_nozip
echo [LOI] Chua nhap duong dan file .zip.
goto :error
:err_notzip
echo [LOI] Day khong phai file .zip: "%ZIP%"
goto :error
:err_missing
echo [LOI] Khong tim thay file: "%ZIP%"
goto :error
:err_backup
echo [LOI] Khong sao luu duoc config.yaml - dung lai de bao ve cau hinh cua ban.
goto :error
:err_extract
echo [LOI] Khong giai nen duoc file .zip (file hong hoac khong phai .zip hop le).
goto :error
:err_layout
echo [LOI] Trong file .zip khong thay main.py va src\controller.py.
echo       Hay dung ban day du cua du an (khong phai chi mot vai file le).
goto :error
:err_sync
echo [LOI] Co file khong cap nhat duoc (dang bi mo hoac bi khoa?). Dong cac chuong trinh lien quan roi thu lai.
goto :error
:err_python
echo [LOI] Khong tim thay Python 3.11 tro len. Hay cai tai https://www.python.org/downloads/
goto :error

:error
echo.
echo [LOI] Cap nhat / build that bai - xem thong bao phia tren.
echo       config.yaml, cache\ va moi truong ao KHONG bi dong toi.
if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%"
pause
exit /b 1
