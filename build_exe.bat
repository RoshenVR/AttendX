@echo off
echo Installing dependencies...
python -m pip install flask qrcode[pil] pyinstaller
if %errorlevel% neq 0 (
    echo Failed to install dependencies. Please check your internet connection.
    pause
    exit /b
)

echo Building attendX executable...
python -m PyInstaller --noconfirm --name attendX --onefile --console --add-data "templates;templates" --add-data "static;static" --hidden-import=flask --hidden-import=qrcode app.py
if %errorlevel% neq 0 (
    echo Build failed.
    pause
    exit /b
)

echo Build complete. Executable is in dist\attendX.exe
pause
