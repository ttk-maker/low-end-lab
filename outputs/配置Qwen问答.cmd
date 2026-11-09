@echo off
setlocal
cd /d "%~dp0"
set "LOWEND_PYTHON=%~dp0..\work\audio-env\Scripts\python.exe"
if not exist "%LOWEND_PYTHON%" set "LOWEND_PYTHON=%~dp0audio-analysis\.venv\Scripts\python.exe"
if not exist "%LOWEND_PYTHON%" (
  echo Run audio-analysis\install.ps1 first.
  pause
  exit /b 1
)
"%LOWEND_PYTHON%" "%~dp0audio-analysis\qwen_coach.py" %*
pause
