"""已安装 Graphify 的命令与 Python 身份。"""

from dataclasses import dataclass
from pathlib import Path


class GraphifyUnavailable(RuntimeError):
    """指定来源没有可用的 Graphify。"""


@dataclass(frozen=True)
class GraphifyRuntime:
    source: str
    python: Path
    version: str

    @property
    def command(self) -> list[str]:
        return [str(self.python), "-m", "graphify"]
