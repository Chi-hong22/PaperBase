"""迁移脚本已废弃

此脚本用于迁移 VALIDATED 状态到 NORMALIZED 状态。
由于状态机已简化（2026-07-08），VALIDATED 状态已从 PaperState 枚举中移除。

如果您的知识库中仍有旧状态的论文，请手动更新 manifest.json 和 registry。
"""
from pathlib import Path

print("此迁移脚本已废弃。VALIDATED 状态在 2026-07-08 状态机简化时已移除。")
print("当前有效状态：NORMALIZED, READY, NEEDS_REVIEW, BLOCKED, FAILED_RETRYABLE, FAILED_PERMANENT")
