@echo off
setlocal
cd /d "%~dp0"

rem Prefer pythonw.exe so no console window shows up.
set "PYW="
for %%V in (313 312 311 310 39 38) do (
  if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe" (
    set "PYW=%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe"
  )
)
if not defined PYW for /f "delims=" %%I in ('where pythonw 2^>nul') do (
  if not defined PYW set "PYW=%%I"
)

if not defined PYW (
  echo pythonw.exe not found. Install Python 3.8 or newer first.
  pause
  exit /b 1
)

start "" "%PYW%" "%~dp0austnet.pyw"
