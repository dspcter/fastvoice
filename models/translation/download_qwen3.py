#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen3-4B 模型下载脚本（支持断点续传）
"""

import os
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from huggingface_hub import snapshot_download
from huggingface_hub.utils import tqdm


def download_with_resume(model_id: str, target_dir: str, max_retries: int = 5):
    """
    支持断点续传的模型下载

    Args:
        model_id: HuggingFace 模型 ID
        target_dir: 目标目录
        max_retries: 最大重试次数
    """
    target_path = Path(target_dir).absolute()

    print(f"{'='*60}")
    print(f"开始下载模型: {model_id}")
    print(f"目标目录: {target_path}")
    print(f"模型大小约 8GB，请耐心等待...")
    print(f"{'='*60}\n")

    for attempt in range(max_retries):
        try:
            print(f"下载尝试 {attempt + 1}/{max_retries}...")

            # snapshot_download 默认支持断点续传
            # 它会保留 .incomplete 文件，中断后可以继续
            snapshot_download(
                repo_id=model_id,
                local_dir=str(target_path),
                local_dir_use_symlinks=False,
                # 断点续传相关参数
                resume_download=True,  # 启用断点续传
                # 显示下载进度
            )

            print(f"\n{'='*60}")
            print("✓ 模型下载完成！")
            print(f"{'='*60}")

            # 验证下载
            print("\n验证下载文件...")
            model_dir = target_path
            safetensors_files = list(model_dir.glob("*.safetensors"))

            if not safetensors_files:
                print("❌ 错误：未找到模型权重文件 (*.safetensors)")
                return False

            total_size = sum(f.stat().st_size for f in safetensors_files)
            print(f"✓ 找到 {len(safetensors_files)} 个模型文件")
            print(f"✓ 总大小: {total_size / (1024**3):.2f} GB")

            # 检查 index.json
            index_file = model_dir / "model.safetensors.index.json"
            if index_file.exists():
                print(f"✓ 模型索引文件存在")
            else:
                print(f"⚠ 警告：模型索引文件不存在")

            return True

        except KeyboardInterrupt:
            print("\n\n下载被用户中断")
            print("下次运行时将从断点继续下载")
            return False

        except Exception as e:
            print(f"\n❌ 下载失败 (尝试 {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5  # 递增等待时间
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"\n已达到最大重试次数 ({max_retries})，下载失败")
                print("建议检查网络连接或稍后重试")
                return False


def main():
    """主函数"""
    # 模型配置
    MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
    TARGET_DIR = "qwen3-4b"

    # 切换到 models/translation 目录
    script_dir = Path(__file__).parent
    os.chdir(script_dir)

    # 开始下载
    success = download_with_resume(MODEL_ID, TARGET_DIR)

    if success:
        print("\n✓ 所有操作完成！")
        sys.exit(0)
    else:
        print("\n✗ 下载未完成")
        sys.exit(1)


if __name__ == "__main__":
    main()
