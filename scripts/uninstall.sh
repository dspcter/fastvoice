#!/bin/bash
# FastVoice 完全卸载脚本
# 删除应用和所有相关文件

echo "=== FastVoice 卸载程序 ==="
echo ""
echo "警告：此操作将删除："
echo "  1. FastVoice 应用"
echo "  2. 所有模型文件（约 2GB）"
echo "  3. 配置文件"
echo "  4. 日志文件"
echo "  5. 音频录制文件"
echo ""

read -p "确认要完全卸载 FastVoice 吗？(yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "取消卸载"
    exit 0
fi

echo ""
echo "开始卸载..."

# 1. 删除应用
APP_PATH="/Applications/FastVoice.app"
if [ -e "$APP_PATH" ]; then
    echo "删除应用: $APP_PATH"
    rm -rf "$APP_PATH"
else
    echo "应用未安装在 /Applications"
fi

# 2. 删除工作目录中的模型和数据
WORK_DIR="/Users/wangchengliang/Documents/claude/快人快语"
if [ -d "$WORK_DIR" ]; then
    echo "删除工作目录中的数据..."

    # 删除模型
    rm -rf "$WORK_DIR/models"
    echo "  ✓ 已删除模型文件"

    # 删除存储（配置、标记文件）
    rm -rf "$WORK_DIR/storage"
    echo "  ✓ 已删除配置文件"

    # 删除日志
    rm -rf "$WORK_DIR/logs"
    echo "  ✓ 已删除日志文件"

    # 删除音频录制
    rm -rf "$WORK_DIR/audio"
    echo "  ✓ 已删除音频录制"
fi

# 3. 删除用户配置（如果存在）
USER_CONFIG="$HOME/.config/fastvoice"
if [ -d "$USER_CONFIG" ]; then
    echo "删除用户配置: $USER_CONFIG"
    rm -rf "$USER_CONFIG"
fi

echo ""
echo "=== 卸载完成 ==="
echo "感谢您使用 FastVoice！"
