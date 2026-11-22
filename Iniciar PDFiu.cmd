@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
set "FOLIO_PDF_RUNTIME=%~dp0runtime"
if not exist "%FOLIO_PDF_RUNTIME%\deps\PySide6" set "FOLIO_PDF_RUNTIME=%USERPROFILE%\Documents\Codex\tools\folio-pdf"
if not exist "%FOLIO_PDF_RUNTIME%\deps\PySide6" (
    echo No se encuentra el entorno de PDFiu. Consulta el archivo LEEME.md.
    pause
    exit /b 1
)
set "FOLIO_PYTHON=%USERPROFILE%\AppData\Local\Programs\Python\Python312\pythonw.exe"
if not exist "%FOLIO_PYTHON%" set "FOLIO_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if exist "%FOLIO_PYTHON%" (
    start "" "%FOLIO_PYTHON%" "%~dp0folio.py" %*
    exit /b
)
where pyw.exe >nul 2>&1
if errorlevel 1 (
    echo Se necesita Python 3.12 de 64 bits. Consulta el archivo LEEME.md.
    pause
    exit /b 1
)
start "" pyw.exe -3.12 "%~dp0folio.py" %*
