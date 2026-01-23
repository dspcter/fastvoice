#!/usr/bin/env python3
"""
注入逻辑测试脚本

这个脚本测试注入逻辑的关键部分，不需要 GUI：
1. 测试关闭检查逻辑
2. 测试剪贴板操作
3. 测试日志输出
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 配置简单日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_injector_creation():
    """测试 1：注入器是否能创建"""
    logger.info("=" * 60)
    logger.info("测试 1：注入器创建")
    logger.info("=" * 60)

    try:
        from core.text_injector import get_text_injector

        injector = get_text_injector()
        logger.info(f"✓ 注入器创建成功")
        logger.info(f"  注入方式: {injector.get_method()}")
        logger.info(f"  可用方法: {injector.get_available_methods()}")
        return True
    except Exception as e:
        logger.error(f"✗ 注入器创建失败: {e}")
        return False


def test_macos_injector():
    """测试 2：macOS 注入器是否能创建"""
    logger.info("=" * 60)
    logger.info("测试 2：macOS 注入器创建")
    logger.info("=" * 60)

    try:
        from core.text_injector_macos import get_macos_injector

        injector = get_macos_injector()
        if injector:
            logger.info(f"✓ macOS 注入器创建成功")
            return True
        else:
            logger.warning("⚠️ macOS 注入器返回 None（PyObjC 不可用）")
            return False
    except Exception as e:
        logger.error(f"✗ macOS 注入器创建失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_clipboard():
    """测试 3：剪贴板操作是否正常"""
    logger.info("=" * 60)
    logger.info("测试 3：剪贴板操作")
    logger.info("=" * 60)

    try:
        import pyperclip

        # 保存当前剪贴板
        original = pyperclip.paste()
        logger.info(f"当前剪贴板长度: {len(original)}")

        # 设置测试内容
        test_text = "TEST_CONTENT_调试测试"
        pyperclip.copy(test_text)
        logger.info(f"✓ 剪贴板已设置: '{test_text}'")

        # 验证
        current = pyperclip.paste()
        if current == test_text:
            logger.info(f"✓ 剪贴板验证通过")
        else:
            logger.error(f"✗ 剪贴板验证失败: 期望 '{test_text}'，实际 '{current}'")

        # 恢复剪贴板
        pyperclip.copy(original)
        logger.info(f"✓ 剪贴板已恢复")

        return True
    except Exception as e:
        logger.error(f"✗ 剪贴板测试失败: {e}")
        return False


def test_inject_call():
    """测试 4：模拟调用 inject()"""
    logger.info("=" * 60)
    logger.info("测试 4：模拟 inject() 调用")
    logger.info("=" * 60)

    try:
        from core.text_injector import get_text_injector

        injector = get_text_injector()
        test_text = "测试注入_不实际执行"

        logger.info(f"调用 inject('{test_text}')...")
        # 注意：这个会实际尝试注入，可能在当前环境中不工作
        result = injector.inject(test_text)

        if result:
            logger.info(f"✓ inject() 返回 True")
        else:
            logger.warning(f"⚠️ inject() 返回 False（可能环境不支持）")

        return True
    except Exception as e:
        logger.error(f"✗ inject() 调用失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_shutdown_flags():
    """测试 5：关闭标志逻辑"""
    logger.info("=" * 60)
    logger.info("测试 5：关闭标志逻辑")
    logger.info("=" * 60)

    try:
        # 检查全局关闭标志
        from core.text_injector_macos import _is_cleaning_up, _is_shutting_down_globally

        logger.info(f"_is_cleaning_up = {_is_cleaning_up}")
        logger.info(f"_is_shutting_down_globally = {_is_shutting_down_globally}")

        # 测试 cleanup() 是否能调用
        from core.text_injector_macos import get_macos_injector
        injector = get_macos_injector()
        if injector:
            logger.info("调用 cleanup()...")
            injector.cleanup()

            # 检查标志是否被设置
            logger.info(f"cleanup() 后 _is_cleaning_up = {_is_cleaning_up}")
            logger.info(f"cleanup() 后 _is_shutting_down_globally = {_is_shutting_down_globally}")

        return True
    except Exception as e:
        logger.error(f"✗ 关闭标志测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    """运行所有测试"""
    logger.info("FastVoice 注入逻辑测试")
    logger.info("=" * 60)

    results = {}

    # 运行测试
    results["创建基础注入器"] = test_injector_creation()
    results["创建macOS注入器"] = test_macos_injector()
    results["剪贴板操作"] = test_clipboard()
    results["inject()调用"] = test_inject_call()
    results["关闭标志逻辑"] = test_shutdown_flags()

    # 输出结果
    logger.info("")
    logger.info("=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)

    for test_name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        logger.info(f"{status}: {test_name}")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
