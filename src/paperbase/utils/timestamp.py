"""时间戳工具函数

提供统一的 ISO 8601 格式时间戳生成，避免格式不一致问题。
"""

from datetime import datetime, timezone


def now_iso8601() -> str:
    """生成当前时间的 ISO 8601 格式字符串

    格式: YYYY-MM-DDTHH:MM:SS.ffffffZ
    示例: 2026-07-10T12:34:56.789012Z

    Returns:
        str: ISO 8601 格式的 UTC 时间戳，以 'Z' 结尾

    Note:
        - 始终使用 UTC 时区
        - 使用 'Z' 后缀而不是 '+00:00'
        - 保留微秒精度
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def to_iso8601(dt: datetime) -> str:
    """将 datetime 对象转换为 ISO 8601 格式字符串

    Args:
        dt: datetime 对象（可以是任意时区）

    Returns:
        str: ISO 8601 格式的 UTC 时间戳，以 'Z' 结尾

    Note:
        如果输入的 datetime 没有时区信息，会假定为 UTC
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.isoformat().replace("+00:00", "Z")
