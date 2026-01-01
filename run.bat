@echo off
REM 快人快语启动脚本 (Windows)

echo 快人快语 - 启动中...
echo.

REM 进入脚本所在目录
cd /d "%~dp0"

REM 检查 Python 版本
echo Python 版本:
python --version
echo.

REM 检查依赖
echo 检查依赖...
python test_dependencies.py

echo.
echo ====================
echo 如需安装依赖，请运行:
echo   pip install -r requirements.txt
echo ====================
echo.

REM 启动程序
python main.py

pause
