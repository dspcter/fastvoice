#!/bin/bash
# 快人快语启动脚本 (macOS)

echo "快人快语 - 启动中..."
echo ""

# 进入脚本所在目录
cd "$(dirname "$0")"

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python 版本: $PYTHON_VERSION"
echo ""

# 检查依赖
echo "检查依赖..."
python3 test_dependencies.py

echo ""
echo "===================="
echo "如需安装依赖，请运行:"
echo "  pip install -r requirements.txt"
echo "===================="
echo ""

# 启动程序
python3 main.py
