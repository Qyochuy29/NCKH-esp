@echo off
chcp 65001 >nul
title Mở cổng 3000 cho ESP32 kết nối mạng LAN
echo =======================================================
echo    DANG CAU HINH WINDOWS FIREWALL CHO HE THONG
echo =======================================================
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [THONG BAO] Dang yeu cau quyen Administrator...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo 1. Dang mo cong 3000 tren Windows Firewall...
netsh advfirewall firewall add rule name="SafeVoice Backend 3000" dir=in action=allow protocol=TCP localport=3000

echo 2. Dang chuyen Wi-Fi sang che do Mang rieng tu (Private Network)...
powershell -Command "Set-NetConnectionProfile -Name 'Bui Tien Tuan' -NetworkCategory Private -ErrorAction SilentlyContinue"

echo.
echo =======================================================
echo  DA MO CONG 3000 THANH CONG!
echo  ESP32 da co the gui am thanh thang ve may tinh.
echo =======================================================
echo.
timeout /t 5
