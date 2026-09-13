@echo off
REM ============================================================
REM  Build TuneLift from source.
REM  Produces the same layout as the shipped bundle:
REM      dist\TuneLift\TuneLift.exe      <- GUI (windowed)
REM      dist\TuneLift\main.exe          <- backend, next to the GUI
REM      dist\TuneLift\_internal\...     <- shared runtime (Qt + frida + ffmpeg)
REM
REM  Run from a normal Windows terminal (cmd); double-clicking works too.
REM  Prefers uv; falls back to the project .venv if uv is missing.
REM  ASCII-only on purpose: cmd's code page would mangle non-ASCII text.
REM ============================================================
setlocal
cd /d "%~dp0" || goto :err

where uv >nul 2>nul
if errorlevel 1 goto :nouv

echo [build] using uv
uv sync || goto :err
set "RUNNER=uv run python"
goto :build

:nouv
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo [build] uv not found, falling back to %PY%
"%PY%" -m pip install -r requirements.txt || goto :err
set "RUNNER="%PY%""

:build
if not exist "ffmpeg.exe" (
    echo [build] ffmpeg.exe missing - fetching it now...
    powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\fetch_ffmpeg.ps1" || goto :err
    if not exist "ffmpeg.exe" (
        echo [build] ERROR: could not obtain ffmpeg.exe.
        goto :err
    )
)

REM --- 1) backend: main.exe -------------------------------------
%RUNNER% -m PyInstaller --noconfirm --clean --onedir --name main ^
    --add-data "hook_qq_music.js;." ^
    --add-binary "ffmpeg.exe;." ^
    main.py || goto :err

REM --- 2) GUI: TuneLift.exe -------------------------------------
%RUNNER% -m PyInstaller --noconfirm --clean --onedir --windowed --name TuneLift ^
    --icon tunelift.ico ^
    --add-data "tunelift.ico;." ^
    GUI.py || goto :err

REM --- 3) merge: main.exe lives in the GUI bundle ---------------
copy /Y "dist\main\main.exe" "dist\TuneLift\" || goto :err
xcopy /E /I /Y "dist\main\_internal" "dist\TuneLift\_internal" >nul || goto :err

REM GUI looks for the icon next to the exe (app_dir()), not inside _internal.
copy /Y "tunelift.ico" "dist\TuneLift\" || goto :err

REM --- 4) licences travel with the bundle -----------------------
REM Qt is used under LGPLv3 and FFmpeg under LGPLv3; both require the
REM licence texts to be redistributed alongside the binaries.
xcopy /E /I /Y "LICENSES" "dist\TuneLift\LICENSES" >nul || goto :err
copy /Y "LICENSE" "dist\TuneLift\" >nul || goto :err
copy /Y "NOTICE" "dist\TuneLift\" >nul || goto :err
copy /Y "THIRD-PARTY-NOTICES.md" "dist\TuneLift\" >nul || goto :err

REM --- 5) refuse to ship GPLv3-only Qt modules -------------------
REM Qt ships a few modules under GPLv3 only. If any of their DLLs end up in
REM the bundle, Qt's own guidance says the whole application must be GPLv3.
REM We only import QtCore/QtGui/QtWidgets, so they should never be collected -
REM this guard turns a silent licensing problem into a loud build failure.
for %%M in (Qt6Lottie.dll Qt6QmlCompiler.dll Qt6QuickTimeline.dll) do (
    if exist "dist\TuneLift\_internal\PySide6\%%M" (
        echo [build] ERROR: GPLv3-only Qt module got bundled: %%M
        goto :err
    )
)

echo.
echo Build complete. Run: dist\TuneLift\TuneLift.exe
goto :eof

:err
echo.
echo BUILD FAILED - see the output above.
exit /b 1
