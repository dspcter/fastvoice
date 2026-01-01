@echo off
REM Windows 打包脚本

echo 开始打包...
pyinstaller build.spec
echo 打包完成!
echo 可执行文件位于: dist\FastVoice.exe
pause
