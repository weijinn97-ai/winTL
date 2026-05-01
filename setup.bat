@echo off
REM Cai dat moi truong cho bot Tien Len.
REM Chay 1 lan sau khi clone repo.

if not exist .venv (
    echo [setup] Tao .venv...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [setup] Cai dependencies...
pip install --upgrade pip
pip install opencv-python numpy python-dotenv keyboard

echo.
echo [setup] Xong. Tiep theo:
echo   1. Copy .env.example          -^> .env  (dien ADB_PATH, MEMU_IP)
echo   2. Copy bot_config.json.example -^> bot_config.json
echo   3. Copy card_detector.py THAT vao thay file stub
echo   4. Dat 52 anh la bai vao cards_output\
echo   5. Dat 5 anh nut vao button_templates\
echo   6. Chay: smoke.bat (kiem tra), roi run.bat (chay bot)
