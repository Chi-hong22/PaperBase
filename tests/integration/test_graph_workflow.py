"""图谱工作流集成测试"""

import pytest
from pathlib import Path
from paperbase.adapters.graphify_adapter import check_graphify_installed


@pytest.fixture
def skip_if_no_graphify():
    """如果 graphify 未安装，跳过测试"""
    if not check_graphify_installed():
        pytest.skip("graphify 未安装，跳过集成测试")


def test_graphify_installed(skip_if_no_graphify):
    """测试 graphify 是否可用"""
    from paperbase.adapters.graphify_adapter import check_graphify_installed
    assert check_graphify_installed() is True


def test_graph_workflow_end_to_end(tmp_path, skip_if_no_graphify):
    """测试完整的图谱工作流

    注意：这个测试需要实际的 PDF 和摄入流程
    在 CI 环境中可能需要 mock
    """
    # TODO: 实现端到端测试
    # 1. 摄入一篇论文
    # 2. 运行 graph update
    # 3. 验证 manifest 和 registry 状态
    # 4. 验证图谱文件生成
    pytest.skip("端到端测试需要实际 PDF，暂时跳过")
