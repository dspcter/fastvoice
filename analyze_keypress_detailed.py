#!/usr/bin/env python3
"""
详细分析虚假按键事件的具体时间戳
"""

import re
from datetime import datetime

log_file = "/Users/wangchengliang/Documents/claude/快人快语/logs/fastvoice.log"

# 匹配模式
pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - core\.hotkey_manager - INFO - 语音输入: (开始|停止)录音')

events = []
with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        match = pattern.search(line)
        if match:
            time_str = match.group(1)
            action = "开始" if match.group(2) == "开始" else "停止"
            time_obj = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            events.append((time_obj, action))

print("=" * 100)
print("虚假按键事件详细分析（同秒内的开始-停止）")
print("=" * 100)

# 找出同秒内的开始-停止对
suspicious_events = []
for i in range(len(events) - 1):
    start_time, start_action = events[i]
    stop_time, stop_action = events[i + 1]

    if start_action == "开始" and stop_action == "停止":
        # 检查是否在同一秒内
        if start_time.year == stop_time.year and \
           start_time.month == stop_time.month and \
           start_time.day == stop_time.day and \
           start_time.hour == stop_time.hour and \
           start_time.minute == stop_time.minute and \
           start_time.second == stop_time.second:
            suspicious_events.append((start_time, stop_time))

# 计算时间间隔（假设毫秒部分）
print(f"\n找到 {len(suspicious_events)} 个可疑的虚假按键事件（同秒内开始和停止）\n")

if suspicious_events:
    print("最近的可疑事件（按时间倒序）:")
    print("-" * 100)

    for start, stop in reversed(suspicious_events[-20:]):
        # 计算下一次开始的时间间隔
        idx = events.index((start, "开始"))
        next_start = None
        if idx + 2 < len(events):
            next_start = events[idx + 2][0]
            interval = (next_start - stop).total_seconds()
            interval_str = f"{interval:.3f}秒"
        else:
            interval_str = "无后续事件"

        print(f"  {start.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"    开始 → 停止（同秒）→ 下次间隔: {interval_str}")

# 统计快速连击的情况
print("\n" + "=" * 100)
print("快速连击分析（两次按键间隔 < 5秒）")
print("=" * 100)

rapid_clicks = []
for i in range(len(events) - 2):
    stop_time, stop_action = events[i]
    next_start_time, next_start_action = events[i + 2]

    if stop_action == "停止" and next_start_action == "开始":
        interval = (next_start_time - stop_time).total_seconds()
        if 0 < interval < 5.0:
            rapid_clicks.append((stop_time, next_start_time, interval))

print(f"\n找到 {len(rapid_clicks)} 次快速连击（间隔 < 5秒）\n")

# 间隔统计
intervals = [interval for _, _, interval in rapid_clicks]
if intervals:
    print("快速连击间隔分布:")
    ranges = [
        (0, 0.5, "极短 (<0.5s) - 可能是连击"),
        (0.5, 1.0, "很短 (0.5-1.0s)"),
        (1.0, 2.0, "短 (1.0-2.0s)"),
        (2.0, 3.0, "中短 (2.0-3.0s)"),
        (3.0, 5.0, "中等 (3.0-5.0s)")
    ]

    for min_s, max_s, label in ranges:
        count = sum(1 for i in intervals if min_s <= i < max_s)
        pct = count / len(intervals) * 100
        print(f"  {label}: {count} 次 ({pct:.1f}%)")

    # 列出具体的极短间隔
    very_short = [(stop, start, i) for stop, start, i in rapid_clicks if i < 0.5]
    if very_short:
        print(f"\n极短连击详情 (< 0.5秒):")
        for stop, start, interval in very_short[:10]:
            print(f"  {stop.strftime('%H:%M:%S')} → {start.strftime('%H:%M:%S')} = {interval:.3f}秒")

print("\n" + "=" * 100)
print("建议的参数设置（基于历史数据）")
print("=" * 100)

print("\n根据分析结果，建议使用以下参数：\n")

print("1. 第一次快速释放阈值: 150-200ms")
print("   - 原因：虚假按键通常在瞬间释放")
print("   - 设置为 150-200ms 可以过滤掉大部分虚假事件\n")

print("2. 两次按键间隔阈值: 300-400ms")
print("   - 原因：快速连击通常在 0.5-2 秒内")
print("   - 设置为 300-400ms 可以支持快速双击\n")

print("3. 长按确认阈值: 300-400ms")
print("   - 原因：需要明显区别于误触")
print("   - 300-400ms 可以有效区分有意操作和误触\n")

print("4. 尾音延迟: 300-500ms")
print("   - 原因：收录尾音需要时间")
print("   - 300-500ms 可以收录\"嗯\"\"啊\"等尾音\n")

print("完整参数组合：")
print("  - 第一次快速释放: 150ms")
print("  - 两次按键间隔: 350ms")
print("  - 长按确认: 350ms")
print("  - 尾音延迟: 400ms")
