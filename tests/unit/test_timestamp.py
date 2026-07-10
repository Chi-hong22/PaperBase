"""测试时间戳工具函数"""

import re
from datetime import datetime, timezone, timedelta
from paperbase.utils.timestamp import now_iso8601, to_iso8601


def test_now_iso8601_format():
    """测试 now_iso8601() 返回正确的 ISO 8601 格式"""
    ts = now_iso8601()

    # 格式验证：YYYY-MM-DDTHH:MM:SS.ffffffZ
    pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$'
    assert re.match(pattern, ts), f"格式错误: {ts}"

    # 验证以 'Z' 结尾
    assert ts.endswith('Z'), f"应该以 'Z' 结尾: {ts}"

    # 验证不包含 '+00:00'
    assert '+00:00' not in ts, f"不应包含 '+00:00': {ts}"


def test_now_iso8601_timezone():
    """测试 now_iso8601() 返回的是 UTC 时间"""
    ts = now_iso8601()

    # 解析时间戳
    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))

    # 验证是 UTC 时区
    assert dt.tzinfo == timezone.utc, "应该是 UTC 时区"

    # 验证时间接近当前时间（误差小于 1 秒）
    now = datetime.now(timezone.utc)
    diff = abs((now - dt).total_seconds())
    assert diff < 1.0, f"时间差异过大: {diff} 秒"


def test_to_iso8601_with_utc():
    """测试 to_iso8601() 处理 UTC datetime"""
    dt = datetime(2026, 7, 10, 12, 34, 56, 789012, tzinfo=timezone.utc)
    ts = to_iso8601(dt)

    assert ts == "2026-07-10T12:34:56.789012Z"


def test_to_iso8601_with_timezone():
    """测试 to_iso8601() 处理其他时区的 datetime"""
    # 东八区时间
    tz_plus8 = timezone(timedelta(hours=8))
    dt = datetime(2026, 7, 10, 20, 34, 56, 789012, tzinfo=tz_plus8)
    ts = to_iso8601(dt)

    # 应该转换为 UTC（减 8 小时）
    assert ts == "2026-07-10T12:34:56.789012Z"


def test_to_iso8601_without_timezone():
    """测试 to_iso8601() 处理无时区的 datetime"""
    dt = datetime(2026, 7, 10, 12, 34, 56, 789012)
    ts = to_iso8601(dt)

    # 应该假定为 UTC
    assert ts == "2026-07-10T12:34:56.789012Z"


def test_no_mixed_format():
    """确保不会生成 '+00:00Z' 混合格式"""
    ts = now_iso8601()

    # 不应该包含混合格式
    assert '+00:00Z' not in ts, f"不应包含混合格式 '+00:00Z': {ts}"
    assert ts.count('Z') == 1, f"应该只有一个 'Z': {ts}"
    assert ts.endswith('Z'), f"应该以 'Z' 结尾: {ts}"


if __name__ == "__main__":
    test_now_iso8601_format()
    print("✅ test_now_iso8601_format 通过")

    test_now_iso8601_timezone()
    print("✅ test_now_iso8601_timezone 通过")

    test_to_iso8601_with_utc()
    print("✅ test_to_iso8601_with_utc 通过")

    test_to_iso8601_with_timezone()
    print("✅ test_to_iso8601_with_timezone 通过")

    test_to_iso8601_without_timezone()
    print("✅ test_to_iso8601_without_timezone 通过")

    test_no_mixed_format()
    print("✅ test_no_mixed_format 通过")

    print("\n✅ 所有测试通过！")
