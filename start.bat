@echo off
chcp 65001 >nul
cd /d g:\new
echo ============================================
echo  🛍️ 出行决策 Agent · 商场推荐助手
echo  启动中...
echo ============================================
echo.
"C:\ProgramData\anaconda3\python.exe" app.py
pause
