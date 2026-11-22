@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
if not defined PDFIU_RUNTIME set "PDFIU_RUNTIME=%~dp0runtime"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0pdfiu.py" %*
    exit /b
)
if exist "%PDFIU_RUNTIME%\deps\PySide6" (
    where pyw.exe >nul 2>&1
    if not errorlevel 1 (
        start "" pyw.exe -3.12 "%~dp0pdfiu.py" %*
        exit /b
    )
)
echo Prepara el entorno de PDFiu siguiendo README.md.
pause
exit /b 1
