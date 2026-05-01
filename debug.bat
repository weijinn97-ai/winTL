@echo off
if not exist .venv (
    echo [LOI] Chua co .venv. Chay setup.bat truoc.
    exit /b 1
)
call .venv\Scripts\activate.bat
python debug_detect.py %*
