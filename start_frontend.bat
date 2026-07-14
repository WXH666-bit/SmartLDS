@echo off
chcp 65001 >nul
echo ====================================
echo   SmartLDS 前端启动
echo ====================================

echo [1/2] 清理旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8080"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5174"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5175"') do taskkill /F /PID %%a >nul 2>&1

echo [2/2] 启动 Vite 开发服务器...
cd /d "%~dp0frontend"
call npm run dev -- --host
pause
