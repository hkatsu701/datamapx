@echo off
setlocal

set "ROOT=%~dp0"
set "SOURCE=%~1"
set "CHIBAN=%~2"

if "%SOURCE%"=="" set "SOURCE=%ROOT%input\sougou_uketsuke_icz_2024.csv"
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
if not exist "%ROOT%reports\service" mkdir "%ROOT%reports\service"
if not exist "%ROOT%logs" mkdir "%ROOT%logs"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%uppercase_csv_headers.ps1" ^
  -InputPath "%SOURCE%" ^
  -OutputPath "%ROOT%work\sougou_uketsuke_icz_2024.csv"
if errorlevel 1 exit /b 1

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%uppercase_csv_headers.ps1" ^
  -InputPath "%CHIBAN%" ^
  -OutputPath "%ROOT%work\CHIBAN.csv"
if errorlevel 1 exit /b 1

python -m datamapx.cli preflight "%ROOT%service.yml"
if errorlevel 1 exit /b 1

python -m datamapx.cli run "%ROOT%service.yml" --html-report
if errorlevel 1 exit /b 1

echo.
echo Service migration completed.
echo Output:  %ROOT%output\service.csv
echo Errors:  %ROOT%reports\service\errors.csv
echo Skipped: %ROOT%reports\service\skipped.csv
echo Summary: %ROOT%reports\service\summary.json
echo HTML:    %ROOT%reports\service\report.html
exit /b 0
