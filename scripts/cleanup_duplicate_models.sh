#!/bin/bash
# 清理重复的模型文件

echo "=== 清理重复的模型文件 ==="

# 定义模型目录
PROJECT_DIR="/Users/wangchengliang/Documents/claude/快人快语"
MODELS_DIR="$PROJECT_DIR/models/models"
DIST_MODELS_DIR="$PROJECT_DIR/dist/FastVoice/_internal/transformers/models"

# 检查并删除打包目录中的模型（应该由工作目录的模型管理）
if [ -d "$DIST_MODELS_DIR" ]; then
    echo "发现打包目录中的模型，删除中..."
    rm -rf "$DIST_MODELS_DIR"
    echo "已删除: $DIST_MODELS_DIR"
fi

# 显示当前模型状态
echo ""
echo "=== 当前模型文件 ==="
if [ -d "$MODELS_DIR" ]; then
    echo "主模型目录: $MODELS_DIR"
    du -sh "$MODELS_DIR/asr" 2>/dev/null || echo "  ASR 模型: 未安装"
    du -sh "$MODELS_DIR/translation" 2>/dev/null || echo "  翻译模型: 未安装"
else
    echo "主模型目录不存在"
fi

echo ""
echo "=== 清理完成 ==="
