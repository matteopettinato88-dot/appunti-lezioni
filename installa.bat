@echo off
setlocal
cd /d "%~dp0"
set "LOG=%~dp0installazione.log"
set PYTHONIOENCODING=utf-8
echo ==== Installazione %date% %time% ==== > "%LOG%"
echo.
echo   Installazione di Appunti Lezioni
echo   ================================
echo.
set "PYEXE="
call :cerca
if defined PYEXE goto :trovato

echo   Python non trovato: provo a installare Python 3.12...
echo Python non trovato, provo con winget >> "%LOG%"
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements >> "%LOG%" 2>&1
call :cerca
if defined PYEXE goto :trovato
echo.
echo   ERRORE: Python non installato.
echo   Installa Python 3.12 da https://www.python.org/downloads/windows/ e rilancia questo file.
echo ERRORE: Python non trovato >> "%LOG%"
pause
exit /b 1

:trovato
echo Python: %PYEXE% >> "%LOG%"
echo   [1/4] Preparo l'ambiente...
if not exist ".venv\Scripts\python.exe" "%PYEXE%" -m venv .venv >> "%LOG%" 2>&1
if not exist ".venv\Scripts\python.exe" goto :errore
echo   [2/4] Scarico le librerie, ci vuole qualche minuto...
".venv\Scripts\python.exe" -m pip install --upgrade pip >> "%LOG%" 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 goto :errore
echo   [3/4] Creo i collegamenti su Desktop e nel menu Start...
".venv\Scripts\python.exe" app.py --installa >> "%LOG%" 2>&1
echo   [4/4] Prova automatica: la prima volta scarica il modello di trascrizione,
echo         poi fa parlare una voce dalle casse. Tieni il volume acceso.
".venv\Scripts\python.exe" app.py --autotest >> "%LOG%" 2>&1
echo.
if exist autotest_risultato.txt type autotest_risultato.txt
echo.
echo.
echo   Finito! Apro Appunti Lezioni...
start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
echo   Da ora in poi lo trovi sul Desktop e nel menu Start.
pause
exit /b 0

:errore
echo.
echo   ERRORE durante l'installazione: i dettagli sono in installazione.log
echo ERRORE >> "%LOG%"
pause
exit /b 1

:cerca
for %%v in (3.12 3.13 3.11) do call :prova %%v
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
goto :eof

:prova
if defined PYEXE goto :eof
for /f "delims=" %%p in ('py -%1 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%p"
goto :eof
