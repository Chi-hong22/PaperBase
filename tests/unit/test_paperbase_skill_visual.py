"""项目内 PaperBase skill 的视觉 PDF 路由契约。"""

# ruff: noqa: N802

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = PROJECT_ROOT / "skills" / "paperbase" / "SKILL.md"
VISUAL_REFERENCE_PATH = (
    PROJECT_ROOT / "skills" / "paperbase" / "references" / "visual_pdf_conversion.md"
)


def _readSkillArtifacts() -> tuple[str, str]:
    return (
        SKILL_PATH.read_text(encoding="utf-8"),
        VISUAL_REFERENCE_PATH.read_text(encoding="utf-8"),
    )


def testSkillRoutesVisualActionToReferenceWithoutNewCommand():
    """普通 ingest 的 AgentActionRequired 才按需加载视觉说明。"""
    skill, reference = _readSkillArtifacts()

    assert "AgentActionRequired" in skill
    assert "references/visual_pdf_conversion.md" in skill
    assert "--accept-visual-warnings" in skill
    assert "paperbase visual" not in skill.lower()
    assert "paperbase visual" not in reference.lower()
    for vendor_invocation in (
        "openai api",
        "anthropic api",
        "client.chat.completions",
        "requests.post(",
    ):
        assert vendor_invocation not in reference.lower()


def testVisualReferenceDescribesEveryWorkerContractAndOwnership():
    """三类任务均以现有 schema、页标记及唯一写入边界表达。"""
    _, reference = _readSkillArtifacts()

    required_tokens = (
        "pdf_auto_text_audit",
        "visual-chunk-result-v1",
        "visual-boundary-review-result-v1",
        "result.md",
        "result.json",
        "<!-- paperbase:visual-page-start page={page} -->",
        "<!-- paperbase:visual-page-end page={page} -->",
        "requested_model",
        "原样",
        "Candidate",
        "Canonical",
        "manifest",
        "run.json",
        "只写本块",
        "只写 result.json",
        "核心页不重叠",
        "context",
    )
    for token in required_tokens:
        assert token in reference

    assert "Boundary Review `blocked` 时停止并映射 `NEEDS_REVIEW`" in reference
    assert "`--accept-visual-warnings` 不能接受" in reference
    assert "Boundary Review `blocked` 时停止并报告 `BLOCKED`" not in reference
    assert "厂商 API" in reference


def testVisualReferenceCoversResumeWarningsAndRequiredScenarios():
    """续作、确认门禁与四类状态场景均遵循普通 ingest 状态映射。"""
    _, reference = _readSkillArtifacts()

    required_tokens = (
        "普通双栏",
        "失败续作",
        "能力缺失",
        "裁剪 warning 确认",
        "重复执行原 ingest",
        "429",
        "503",
        "timeout",
        "channel_error",
        "最多一次",
        "completed",
        "affected_chunk_ids",
        "Boundary Review",
        "pass",
        "--accept-visual-warnings",
        "用户明确确认",
        "Agent 不得自行确认",
        "BLOCKED",
        "FAILED_RETRYABLE",
        "NEEDS_REVIEW",
        "NORMALIZED",
    )
    for token in required_tokens:
        assert token in reference
