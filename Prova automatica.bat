@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo Prova automatica in corso: tra poco sentirai una voce dalle casse...
".venv\Scripts\python.exe" app.py --autotest
echo.
pause
