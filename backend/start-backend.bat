@echo off
REM Starts the CropMind backend so that BOTH the dashboard and the ESP32 can reach it.
REM --host 0.0.0.0 accepts connections from other devices on the Wi-Fi (the ESP32);
REM without it only this laptop can connect and the ESP32 shows as offline.
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo.
echo CropMind backend - the ESP32's API_URL must use one of these addresses:
ipconfig | findstr /C:"IPv4"
echo.
uvicorn main:app --reload --host 0.0.0.0 --port 8000
