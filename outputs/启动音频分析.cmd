@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -Command "try { $r = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2; if ($r.ok) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 (
  start "" "http://127.0.0.1:8765/#analysis"
  exit /b 0
)
set "LOWEND_PYTHON=%~dp0..\work\audio-env\Scripts\python.exe"
if not exist "%LOWEND_PYTHON%" set "LOWEND_PYTHON=%~dp0audio-analysis\.venv\Scripts\python.exe"
if not exist "%LOWEND_PYTHON%" (
  echo Python environment missing. Run audio-analysis\install.ps1 first.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8765/#analysis
echo Keep this window open while using audio analysis. Close it to stop the server.
"%LOWEND_PYTHON%" "%~dp0audio-analysis\server.py" --port 8765
pause
