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

REM GUI looks for the icon and the help page next to the exe (app_dir()),
REM not inside _internal, so put copies there too.
copy /Y "tunelift.ico" "dist\TuneLift\" || goto :err

echo.
echo Build complete. Run: dist\TuneLift\TuneLift.exe
goto :eof

:err
echo.
echo BUILD FAILED - see the output above.
exit /b 1
