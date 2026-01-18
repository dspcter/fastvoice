#!/usr/bin/env python3
"""
分析历史日志中的按键事件时间
"""

import re
from datetime import datetime
from collections import defaultdict

# 读取日志文件
log_file = "/Users/wangchengliang/Documents/claude/快人快语/logs/fastvoice.log"

# 存储按键事件
events = []
current_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - core\.hotkey_manager - INFO - 语音输入: (开始|停止)录音')

print("=" * 80)
print("按键事件时间分析")
print("=" * 80)

with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        match = current_pattern.search(line)
        if match:
            time_str = match.group(1)
            action = match.group(2)
            time_obj = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            events.append((time_obj, action))

print(f"\n找到 {len(events)} 个按键事件\n")

# 分析连续的开始-停止对
durations = []
intervals = []

for i in range(0, len(events) - 1, 2):
    if i + 1 < len(events):
        start_time, start_action = events[i]
        stop_time, stop_action = events[i + 1]

        if start_action == "开始" and stop_action == "停止":
            duration = (stop_time - start_time).total_seconds()
            durations.append(duration)

            # 计算到下一对的间隔（如果有）
            if i + 2 < len(events):
                next_start_time = events[i + 2][0]
                interval = (next_start_time - stop_time).total_seconds()
                intervals.append(interval)

# 统计分析
print("=" * 80)
print("录音时长统计（开始到停止）")
print("=" * 80)

if durations:
    durations_sorted = sorted(durations)

    print(f"总录音次数: {len(durations)}")
    print(f"\n时长分布:")
    print(f"  最短: {min(durations_sorted):.3f}秒")
    print(f"  最长: {max(durations_sorted):.3f}秒")
    print(f"  平均: {sum(durations_sorted)/len(durations_sorted):.3f}秒")
    print(f"  中位数: {durations_sorted[len(durations_sorted)//2]:.3f}秒")

    # 分段统计
    print(f"\n时长分段:")
    ranges = [
        (0, 0.5, "极短 (<0.5s) - 可能是虚假按键"),
        (0.5, 1.0, "短 (0.5-1.0s)"),
        (1.0, 3.0, "正常 (1.0-3.0s)"),
        (3.0, 10.0, "长 (3.0-10.0s)"),
        (10.0, float('inf'), "超长 (>10s)")
    ]

    for min_s, max_s, label in ranges:
        count = sum(1 for d in durations if min_s <= d < max_s)
        pct = count / len(durations) * 100
        print(f"  {label}: {count} 次 ({pct:.1f}%)")

    # 列出所有极短的录音
    very_short = [d for d in durations if d < 0.5]
    if very_short:
        print(f"\n极短录音详情 (< 0.5秒):")
        print(f"  时间: {', '.join([f'{d:.3f}s' for d in very_short[:10]])}")

print("\n" + "=" * 80)
print("两次按键间隔统计（停止到下一次开始）")
print("=" * 80)

if intervals:
    intervals_sorted = sorted(intervals)

    print(f"总间隔次数: {len(intervals)}")
    print(f"\n间隔分布:")
    print(f"  最短: {min(intervals_sorted):.3f}秒")
    print(f"  最长: {max(intervals_sorted):.3f}秒")
    print(f"  平均: {sum(intervals_sorted)/len(intervals_sorted):.3f}秒")
    print(f"  中位数: {intervals_sorted[len(intervals_sorted)//2]:.3f}秒")

    # 分段统计
    print(f"\n间隔分段:")
    ranges = [
        (0, 0.5, "极短 (<0.5s) - 可能是连击"),
        (0.5, 2.0, "短 (0.5-2.0s)"),
        (2.0, 10.0, "正常 (2.0-10.0s)"),
        (10.0, 60.0, "长 (10-60s)"),
        (60.0, float('inf'), "超长 (>60s)")
    ]

    for min_s, max_s, label in ranges:
        count = sum(1 for i in intervals if min_s <= i < max_s)
        pct = count / len(intervals) * 100
        print(f"  {label}: {count} 次 ({pct:.1f}%)")

    # 列出所有极短的间隔
    very_short_intervals = [i for i in intervals if i < 0.5]
    if very_short_intervals:
        print(f"\n极短间隔详情 (< 0.5秒):")
        print(f"  时间: {', '.join([f'{i:.3f}s' for i in very_short_intervals[:15]])}")

print("\n" + "=" * 80)
print("建议参数")
print("=" * 80)

# 基于统计数据给出建议
if durations:
    # 找到虚假按键的阈值
    very_short_count = len([d for d in durations if d < 0.5])
    if very_short_count > 0:
        print(f"\n虚假按键检测:")
        print(f"  - {very_short_count}/{len(durations)} 次录音极短 (<0.5s)")
        print(f"  - 建议第一次快速释放阈值: 150-250ms")
        print(f"  - 建议长按确认阈值: 300-400ms")

if intervals:
    short_interval_count = len([i for i in intervals if i < 2.0])
    if short_interval_count > 0:
        print(f"\n连击检测:")
        print(f"  - {short_interval_count}/{len(intervals)} 次间隔很短 (<2s)")
        print(f"  - 建议双击间隔阈值: 300-500ms")

print(f"\n尾音延迟:")
print(f"  - 建议延迟: 300-500ms")
print(f"  - 用于收录\"嗯\"\"啊\"等尾音")
