@echo off
setlocal

set "ROOT=%~dp0"
set "SOURCE=%~1"
set "CHIBAN=%~2"

if "%SOURCE%"=="" set "SOURCE=%ROOT%input\INPUT.csv"
if "%CHIBAN%"=="" set "CHIBAN=%ROOT%input\CHIBAN.csv"

if not exist "%SOURCE%" (
  echo Input CSV not found: %SOURCE%
  exit /b 1
)

if not exist "%CHIBAN%" (
  echo CHIBAN CSV not found: %CHIBAN%
  exit /b 1
)

if not exist "%ROOT%work" mkdir "%ROOT%work"
if not exist "%ROOT%output" mkdir "%ROOT%output"
if not exist "%ROOT%reports" mkdir "%ROOT%reports"
if not exist "%ROOT%logs" mkdir "%ROOT%logs"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%uppercase_csv_headers.ps1" ^
  -InputPath "%SOURCE%" ^
  -OutputPath "%ROOT%work\INPUT.csv"
if errorlevel 1 exit /b 1

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%uppercase_csv_headers.ps1" ^
  -InputPath "%CHIBAN%" ^
  -OutputPath "%ROOT%work\CHIBAN.csv"
if errorlevel 1 exit /b 1

python -m datamapx.cli preflight "%ROOT%run-all.yml"
if errorlevel 1 exit /b 1

python -m datamapx.cli run-all "%ROOT%run-all.yml"
if errorlevel 1 exit /b 1

echo.
echo Migration completed.
echo Reception: %ROOT%output\受付.csv
echo Service:   %ROOT%output\サービス.csv
echo Reports:   %ROOT%reports
exit /b 0
