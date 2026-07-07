# tests/unit/test_exceptions.py
import pytest
from paperbase.core.exceptions import (
    PaperBaseError,
    ValidationError,
    PaperBaseSystemError,
    TransientError
)


def test_paperbase_error_is_base_exception():
    """基类应该继承自 Exception"""
    error = PaperBaseError("test message")
    assert isinstance(error, Exception)
    assert str(error) == "test message"


def test_validation_error_inheritance():
    """ValidationError 应该继承自 PaperBaseError"""
    error = ValidationError("invalid schema")
    assert isinstance(error, PaperBaseError)
    assert isinstance(error, Exception)


def test_system_error_inheritance():
    """PaperBaseSystemError 应该继承自 PaperBaseError"""
    error = PaperBaseSystemError("system failure")
    assert isinstance(error, PaperBaseError)


def test_transient_error_inheritance():
    """TransientError 应该继承自 PaperBaseError"""
    error = TransientError("network timeout")
    assert isinstance(error, PaperBaseError)


def test_exception_with_context():
    """异常应该支持上下文信息"""
    error = ValidationError("invalid field", context={"field": "year", "value": 999})
    assert error.context == {"field": "year", "value": 999}
