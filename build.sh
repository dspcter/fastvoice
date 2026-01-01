#!/bin/bash
# macOS 打包脚本

echo "开始打包..."
pyinstaller build.spec
echo "打包完成!"
echo "可执行文件位于: dist/快人快语.app"
