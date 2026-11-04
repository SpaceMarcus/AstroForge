@echo off
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Bitte Node.js installieren oder die gehostete Browser-Version verwenden.
  pause
  exit /b 1
)
node tools/build.mjs
if errorlevel 1 (pause & exit /b 1)
start "" http://localhost:4173
node tools/serve.mjs
pause
