@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "SCRIPT=%~dp0cache_manager.py"
set "RULES=%~dp0software_cache_rules.json"
set "LOADER=%~dp0rule_loader.py"
set "HEURISTIC=%~dp0heuristic_scanner.py"
set "SAFETY=%~dp0cache_safety.py"
set "PYTHON="

if not exist "%SCRIPT%" (
  echo ERROR: cache_manager.py was not found.
  echo Expected: "%SCRIPT%"
  pause
  exit /b 1
)

if not exist "%RULES%" echo WARNING: software_cache_rules.json not found. Rule-based scan will be unavailable.
if not exist "%LOADER%" echo WARNING: rule_loader.py not found. Rule-based scan will be unavailable.
if not exist "%HEURISTIC%" echo WARNING: heuristic_scanner.py not found. Heuristic scan will be unavailable.
if not exist "%SAFETY%" echo WARNING: cache_safety.py not found. Global safety judge will be skipped.

if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not defined PYTHON if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PYTHON if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYTHON if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYTHON for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do if not defined PYTHON set "PYTHON=%%P"
if not defined PYTHON for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON set "PYTHON=%%P"

if not defined PYTHON (
  echo ERROR: Python 3 was not found.
  pause
  exit /b 1
)

"%PYTHON%" -c "from PyQt6.QtWidgets import QApplication" >nul 2>nul
if errorlevel 1 (
  echo ERROR: PyQt6 is unavailable in this Python installation.
  echo Python: "%PYTHON%"
  echo.
  echo Install with:
  echo   "%PYTHON%" -m pip install PyQt6
  pause
  exit /b 1
)

echo.
echo Starting CacheSweep (rule-library edition)...
echo Python: "%PYTHON%"
echo.
"%PYTHON%" "%SCRIPT%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo The cache manager exited with error code %RC%.
  echo Python: "%PYTHON%"
  echo Script: "%SCRIPT%"
  pause
)
exit /b %RC%
