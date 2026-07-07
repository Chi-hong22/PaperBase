# tests/integration/test_doctor_command.py
import pytest
from click.testing import CliRunner
from paperbase.cli.main import main


def test_doctor_command_runs():
    """doctor 命令应该能正常运行"""
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0 or result.exit_code == 1  # 可能因为缺少依赖而失败
    assert "检查" in result.output or "Doctor" in result.output or "PaperBase" in result.output


def test_doctor_checks_python():
    """应该检查 Python 版本"""
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])

    assert "Python" in result.output


def test_doctor_provides_suggestions():
    """应该提供建议或诊断信息"""
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])

    # 应该有某种状态指示
    assert "✅" in result.output or "❌" in result.output or "⚠️" in result.output
