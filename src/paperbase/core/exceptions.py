# src/paperbase/core/exceptions.py
"""统一的异常处理体系"""


class PaperBaseError(Exception):
    """PaperBase 异常基类"""

    def __init__(self, message: str, context: dict | None = None):
        super().__init__(message)
        self.context = context or {}


class ValidationError(PaperBaseError):
    """数据验证错误 - 用户可修复

    Examples:
        - Schema 验证失败
        - 文件格式错误
        - 参数值无效
    """


class PaperBaseSystemError(PaperBaseError):
    """系统错误 - 需要技术介入

    Examples:
        - 文件系统权限问题
        - 数据库连接失败
        - 外部依赖缺失
    """


class TransientError(PaperBaseError):
    """临时错误 - 可重试

    Examples:
        - 网络超时
        - 临时文件锁定
        - LLM API 限流
    """
