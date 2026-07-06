# PaperBase Foundation 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 PaperBase 论文知识库的核心基础设施，包括项目骨架、Canonical Schema、状态机制和基础工作流。

**Architecture:** 7层分层架构，以 Canonical Markdown 为 source of truth，支持幂等状态机管理，Graphify 作为可重建的 projection layer。直接集成现有 skills（paper-fetch、zotero-mcp、graphify），不构建 multi-agent framework。

**Tech Stack:**
- Python 3.11+
- uv (项目管理)
- pydantic v2 (schema 验证)
- sqlite3 (registry)
- CSL JSON (元数据标准)
- PyYAML (frontmatter)

## Global Constraints

- Python >= 3.11
- 所有文件使用 UTF-8 编码
- 所有路径使用 `/` 或 `Path` 对象（跨平台兼容）
- 不使用 `.env` 文件，用 `env.example` 替代
- 所有 schema 必须通过 pydantic 验证
- 所有状态转换必须记录到 manifest.json
- 不得通过自动化工作流绕过付费墙（scansci 配置 scihub_enabled=false）
- Graphify 只扫描 `library/papers/**/paper.md`
- 资产路径必须是相对路径
- 遵循 DRY, YAGNI, KISS 原则
- 使用 TDD：先写测试，再写实现

---

## Phase 1: 项目骨架搭建

### Task 1: 初始化项目结构

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `CLAUDE.md`
- Create: `.gitignore`
- Create: `env.example`

**Interfaces:**
- Consumes: 无
- Produces: 
  - uv 项目结构
  - 基础文档框架

- [ ] **Step 1: 初始化 uv 项目**

```bash
cd F:\__PaperBase__
uv init --name paperbase --lib
```

Expected: 生成 `pyproject.toml` 和基础目录结构

- [ ] **Step 2: 配置 pyproject.toml**

编辑 `pyproject.toml`：

```toml
[project]
name = "paperbase"
version = "0.1.0"
description = "Academic paper knowledge base infrastructure"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.13.0",
    "pyyaml>=6.0",
    "click>=8.1.0",
    "rich>=13.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.5.0",
]

[project.scripts]
paperbase = "paperbase.cli.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]
ignore = ["E501"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v --cov=paperbase --cov-report=term-missing"

- [ ] **Step 3: 安装依赖**

```bash
uv sync
```

Expected: 生成 `uv.lock` 和虚拟环境

- [ ] **Step 4: 创建 .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.venv/
venv/
ENV/
env/

# uv
.python-version
uv.lock

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/

# PaperBase specific
library/sources/
library/papers/
registry/
graph/
*.db
*.sqlite
*.sqlite3

# Temp
.DS_Store
Thumbs.db
*.tmp
*.log

- [ ] **Step 5: 创建 README.md**

```markdown
# PaperBase

学术论文知识库基础设施。

## 特性

- 🎯 Canonical Markdown 作为 source of truth
- 📊 幂等状态机管理论文摄入流程
- 🔍 集成 Zotero、paper-fetch、graphify
- 📝 CSL JSON 标准元数据
- 🔄 可重建的知识图谱

## 快速开始

```bash
# 安装
uv sync

# 摄入论文
paperbase ingest "10.1038/s41586-026-10265-5"

# 查询知识库
paperbase search "machine learning"
```

## 文档

- [AGENTS.md](AGENTS.md) - Agent 工作指南
- [架构设计](docs/architecture.md)
- [API 文档](docs/api.md)

## 许可

MIT License
```

- [ ] **Step 6: 提交初始结构**

```bash
git add pyproject.toml .gitignore README.md
git commit -m "chore: initialize PaperBase project structure

Agent-Task: 初始化项目骨架
Agent-Model: claude-fable-5
Agent-Decision: 使用 uv 作为项目管理工具，pydantic v2 作为 schema 验证
Agent-Limitation: 暂未添加具体实现代码

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交


---

### Task 2: 创建目录结构

**Files:**
- Create: `src/paperbase/__init__.py`
- Create: `src/paperbase/core/__init__.py`
- Create: `src/paperbase/schemas/__init__.py`
- Create: `src/paperbase/adapters/__init__.py`
- Create: `src/paperbase/cli/__init__.py`
- Create: `tests/__init__.py`
- Create: `config/paperbase.yaml`
- Create: `skills/README.md`

**Interfaces:**
- Consumes: 项目根目录结构
- Produces: 完整的 Python 包结构和配置目录

- [ ] **Step 1: 创建源代码目录**

```bash
mkdir -p src/paperbase/{core,schemas,adapters,cli,utils}
touch src/paperbase/__init__.py
touch src/paperbase/core/__init__.py
touch src/paperbase/schemas/__init__.py
touch src/paperbase/adapters/__init__.py
touch src/paperbase/cli/__init__.py
touch src/paperbase/utils/__init__.py
```

Expected: 创建 Python 包结构

- [ ] **Step 2: 创建配置和数据目录**

```bash
mkdir -p config/schemas
mkdir -p library/{sources/pdf/sha256,papers,collections,notes}
mkdir -p registry
mkdir -p graph
mkdir -p skills
mkdir -p docs/{architecture,api}
```

Expected: 创建所有必需的目录

- [ ] **Step 3: 创建测试目录**

```bash
mkdir -p tests/{unit,integration,fixtures}
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
```

Expected: 创建测试目录结构


- [ ] **Step 4: 创建基础配置文件**

创建 `config/paperbase.yaml`：

```yaml
# PaperBase 配置文件

project:
  name: "PaperBase"
  version: "0.1.0"

paths:
  library: "library"
  registry: "registry"
  graph: "graph"
  skills: "skills"

storage:
  pdf_content_addressed: true
  sha256_sharding: true  # ab/abcdef...pdf

state_machine:
  initial_state: "discovered"
  final_state: "ready"

adapters:
  paper_fetch:
    enabled: true
  zotero:
    enabled: true
    local_mode: true
  scansci:
    enabled: false
    scihub_enabled: false
    require_authorized_access: true

graphify:
  auto_update: true
  ignore_patterns:
    - "sources/"
    - "registry/"
    - "**/source/"
    - "**/*.pdf"
    - "**/chunks.jsonl"
    - "**/references.jsonl"
```

- [ ] **Step 5: 创建 skills README**

创建 `skills/README.md`：

```markdown
# PaperBase Skills

此目录存放项目级 skills。

## 已集成 Skills

- paper-fetch-skill: 论文获取和转换
- citation-check-skill: 引用验证
- zotero-mcp: Zotero 集成（通过 MCP）
- graphify: 知识图谱构建（通过 MCP）

## 安装

详见各 skill 的安装说明。

## Symlink 配置

`.agents/skills` 和 `.claude/skills` 通过 symlink 指向此目录。
```

- [ ] **Step 6: 提交目录结构**

```bash
git add src/ tests/ config/ skills/ library/ docs/
git add -f library/.gitkeep registry/.gitkeep graph/.gitkeep
git commit -m "chore: create project directory structure

Agent-Task: 创建 PaperBase 目录结构
Agent-Model: claude-fable-5
Agent-Decision: 7层架构，library 分层存储 sources/papers/collections
Agent-Limitation: library 目录暂为空

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交


---

### Task 3: 定义 Canonical Schema

**Files:**
- Create: `src/paperbase/schemas/paper.py`
- Create: `src/paperbase/schemas/manifest.py`
- Create: `src/paperbase/schemas/csl.py`
- Create: `tests/unit/test_schemas.py`

**Interfaces:**
- Consumes: pydantic v2
- Produces:
  - `PaperMetadata` (BaseModel)
  - `ManifestSchema` (BaseModel)
  - `CSLItem` (BaseModel)

- [ ] **Step 1: 编写 CSL JSON schema 测试**

创建 `tests/unit/test_schemas.py`：

```python
import pytest
from paperbase.schemas.csl import CSLName, CSLDate, CSLItem


def test_csl_name_valid():
    """测试 CSL 名称格式"""
    name = CSLName(family="Smith", given="John")
    assert name.family == "Smith"
    assert name.given == "John"


def test_csl_name_family_only():
    """测试仅姓氏"""
    name = CSLName(family="Smith")
    assert name.family == "Smith"
    assert name.given is None


def test_csl_date_valid():
    """测试 CSL 日期格式"""
    date = CSLDate(date_parts=[[2026, 7, 6]])
    assert date.date_parts == [[2026, 7, 6]]


def test_csl_item_minimal():
    """测试最小 CSL item"""
    item = CSLItem(
        type="article-journal",
        id="item-1",
        title="Test Paper",
        author=[CSLName(family="Smith", given="John")],
        issued=CSLDate(date_parts=[[2026]])
    )
    assert item.type == "article-journal"
    assert item.title == "Test Paper"
    assert len(item.author) == 1


def test_csl_item_with_doi():
    """测试带 DOI 的 CSL item"""
    item = CSLItem(
        type="article-journal",
        id="item-1",
        title="Test Paper",
        author=[CSLName(family="Smith")],
        issued=CSLDate(date_parts=[[2026]]),
        DOI="10.1234/test"
    )
    assert item.DOI == "10.1234/test"
```


- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_schemas.py::test_csl_name_valid -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'paperbase.schemas.csl'"

- [ ] **Step 3: 实现 CSL JSON schema**

创建 `src/paperbase/schemas/csl.py`：

```python
"""CSL JSON Schema 定义

基于 Citation Style Language (CSL) 标准
https://citeproc-js.readthedocs.io/
"""

from pydantic import BaseModel, Field


class CSLName(BaseModel):
    """CSL 名称格式"""
    family: str
    given: str | None = None
    
    model_config = {"extra": "allow"}


class CSLDate(BaseModel):
    """CSL 日期格式"""
    date_parts: list[list[int]] = Field(alias="date-parts")
    
    model_config = {"populate_by_name": True}


class CSLItem(BaseModel):
    """CSL Item 完整格式"""
    type: str  # article-journal, book, paper-conference, etc.
    id: str
    title: str
    author: list[CSLName]
    issued: CSLDate
    
    # Optional fields
    DOI: str | None = None
    container_title: str | None = Field(None, alias="container-title")
    volume: str | None = None
    issue: str | None = None
    page: str | None = None
    publisher: str | None = None
    ISSN: str | None = None
    URL: str | None = None
    abstract: str | None = None
    
    model_config = {
        "populate_by_name": True,
        "extra": "allow"
    }
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/unit/test_schemas.py -v
```

Expected: 所有测试 PASS


- [ ] **Step 5: 编写 PaperMetadata 测试**

在 `tests/unit/test_schemas.py` 中添加：

```python
from paperbase.schemas.paper import PaperMetadata, PaperIdentifiers, PaperSource, PaperProvenance


def test_paper_metadata_minimal():
    """测试最小 paper metadata"""
    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        title="Test Paper",
        authors=[{"name": "John Smith"}],
        year=2026,
        abstract="Test abstract"
    )
    assert metadata.paper_id == "doi:10.1234/test"
    assert metadata.title == "Test Paper"
    assert metadata.year == 2026


def test_paper_metadata_with_identifiers():
    """测试带完整标识符的 metadata"""
    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        title="Test Paper",
        authors=[{"name": "John Smith"}],
        year=2026,
        abstract="Test abstract",
        identifiers=PaperIdentifiers(
            doi="10.1234/test",
            arxiv="2401.12345"
        )
    )
    assert metadata.identifiers.doi == "10.1234/test"
    assert metadata.identifiers.arxiv == "2401.12345"
```

- [ ] **Step 6: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_schemas.py::test_paper_metadata_minimal -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'paperbase.schemas.paper'"


- [ ] **Step 7: 实现 PaperMetadata schema**

创建 `src/paperbase/schemas/paper.py`：

```python
"""Paper Canonical Schema 定义

Canonical Markdown frontmatter 的 pydantic 模型
"""

from datetime import datetime
from pydantic import BaseModel, Field


class PaperAuthor(BaseModel):
    """论文作者"""
    name: str
    orcid: str | None = None
    affiliation: str | None = None


class PaperVenue(BaseModel):
    """发表venue"""
    name: str
    type: str  # journal, conference, preprint


class PaperIdentifiers(BaseModel):
    """论文标识符"""
    doi: str | None = None
    arxiv: str | None = None
    pmid: str | None = None
    openalex: str | None = None
    semantic_scholar: str | None = None


class PaperSource(BaseModel):
    """数据来源"""
    discovery: str  # zotero, search, manual
    fulltext_provider: str | None = None  # paper-fetch, manual
    original_url: str | None = None


class PaperProvenance(BaseModel):
    """溯源信息"""
    ingested_at: str  # ISO 8601
    converter: dict[str, str]  # {name, version}
    normalizer: dict[str, str]  # {name, version}
    source_pdf_sha256: str | None = None
    canonical_content_sha256: str


class PaperAssets(BaseModel):
    """资产配置"""
    root: str = "./assets"


class PaperReferences(BaseModel):
    """引用信息"""
    path: str = "./references.jsonl"
    count: int


class PaperChunks(BaseModel):
    """分块信息"""
    path: str = "./chunks.jsonl"
    strategy: str = "section-aware-v1"


class PaperQuality(BaseModel):
    """质量标记"""
    fulltext: bool = True
    metadata_complete: bool = True
    references_parsed: bool = True
    needs_review: bool = False


class PaperMetadata(BaseModel):
    """Paper Canonical Metadata (YAML frontmatter)"""
    schema_version: str
    paper_id: str
    storage_id: str
    
    title: str
    authors: list[PaperAuthor]
    year: int
    published_at: str | None = None
    
    venue: PaperVenue | None = None
    identifiers: PaperIdentifiers | None = None
    language: str = "en"
    abstract: str
    keywords: list[str] = Field(default_factory=list)
    
    source: PaperSource | None = None
    provenance: PaperProvenance | None = None
    
    assets: PaperAssets = Field(default_factory=PaperAssets)
    references: PaperReferences | None = None
    chunks: PaperChunks | None = None
    quality: PaperQuality = Field(default_factory=PaperQuality)
```


- [ ] **Step 8: 运行 PaperMetadata 测试确认通过**

```bash
uv run pytest tests/unit/test_schemas.py::test_paper_metadata_minimal -v
uv run pytest tests/unit/test_schemas.py::test_paper_metadata_with_identifiers -v
```

Expected: 所有测试 PASS

- [ ] **Step 9: 编写 Manifest schema 测试**

在 `tests/unit/test_schemas.py` 中添加：

```python
from paperbase.schemas.manifest import ManifestSchema, PaperState


def test_manifest_minimal():
    """测试最小 manifest"""
    manifest = ManifestSchema(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        state=PaperState.DISCOVERED
    )
    assert manifest.paper_id == "doi:10.1234/test"
    assert manifest.state == PaperState.DISCOVERED


def test_manifest_state_transitions():
    """测试状态枚举"""
    assert PaperState.DISCOVERED.value == "discovered"
    assert PaperState.READY.value == "ready"
```

- [ ] **Step 10: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_schemas.py::test_manifest_minimal -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'paperbase.schemas.manifest'"

- [ ] **Step 11: 实现 Manifest schema**

创建 `src/paperbase/schemas/manifest.py`：

```python
"""Manifest Schema 定义

每篇论文的状态和溯源信息
"""

from enum import Enum
from pydantic import BaseModel, Field


class PaperState(str, Enum):
    """论文处理状态"""
    DISCOVERED = "discovered"
    RESOLVED = "resolved"
    SOURCE_READY = "source_ready"
    CONVERTED = "converted"
    NORMALIZED = "normalized"
    VALIDATED = "validated"
    GRAPHED = "graphed"
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"


class SourcePDF(BaseModel):
    """PDF 源文件信息"""
    path: str
    sha256: str
    acquired_at: str


class CanonicalMD(BaseModel):
    """规范化 Markdown 信息"""
    path: str
    sha256: str
    schema_version: str


class PipelineInfo(BaseModel):
    """处理流程信息"""
    converter: str
    converter_version: str
    normalizer_version: str | None = None


class GraphInfo(BaseModel):
    """图谱索引信息"""
    indexed: bool = False
    indexed_content_sha256: str | None = None


class ManifestSchema(BaseModel):
    """Paper Manifest (manifest.json)"""
    paper_id: str
    storage_id: str
    state: PaperState
    
    source_pdf: SourcePDF | None = None
    canonical_md: CanonicalMD | None = None
    pipeline: PipelineInfo | None = None
    graph: GraphInfo | None = None
    
    created_at: str | None = None
    updated_at: str | None = None
```


- [ ] **Step 12: 运行所有 schema 测试确认通过**

```bash
uv run pytest tests/unit/test_schemas.py -v
```

Expected: 所有测试 PASS

- [ ] **Step 13: 提交 schemas**

```bash
git add src/paperbase/schemas/ tests/unit/test_schemas.py
git commit -m "feat: add canonical schemas (CSL, Paper, Manifest)

Agent-Task: 定义 PaperBase Canonical Schema
Agent-Model: claude-fable-5
Agent-Decision: 使用 pydantic v2 实现 CSL JSON 标准，定义 Paper frontmatter 和 Manifest 格式
Agent-Limitation: 暂未实现 schema 序列化和反序列化工具函数

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交

---

### Task 4: 核心工具函数

**Files:**
- Create: `src/paperbase/core/identity.py`
- Create: `src/paperbase/core/paths.py`
- Create: `src/paperbase/utils/hash.py`
- Create: `tests/unit/test_identity.py`
- Create: `tests/unit/test_hash.py`

**Interfaces:**
- Consumes: pydantic schemas
- Produces:
  - `normalize_paper_id(raw: str) -> str`
  - `generate_storage_id(paper_id: str) -> str`
  - `sha256_file(path: Path) -> str`
  - `PaperPaths` (dataclass)

- [ ] **Step 1: 编写 hash 工具测试**

创建 `tests/unit/test_hash.py`：

```python
import pytest
from pathlib import Path
from paperbase.utils.hash import sha256_file, sha256_string


def test_sha256_string():
    """测试字符串 hash"""
    result = sha256_string("test")
    assert len(result) == 64
    assert result == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


def test_sha256_file(tmp_path):
    """测试文件 hash"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content", encoding="utf-8")
    
    result = sha256_file(test_file)
    assert len(result) == 64
```


- [ ] **Step 2: 运行 hash 测试确认失败**

```bash
uv run pytest tests/unit/test_hash.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'paperbase.utils.hash'"

- [ ] **Step 3: 实现 hash 工具**

创建 `src/paperbase/utils/hash.py`：

```python
"""Hash 工具函数"""

import hashlib
from pathlib import Path


def sha256_string(text: str) -> str:
    """计算字符串的 SHA256"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """计算文件的 SHA256"""
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()
```

- [ ] **Step 4: 运行 hash 测试确认通过**

```bash
uv run pytest tests/unit/test_hash.py -v
```

Expected: 所有测试 PASS

- [ ] **Step 5: 编写 identity 工具测试**

创建 `tests/unit/test_identity.py`：

```python
import pytest
from paperbase.core.identity import normalize_paper_id, generate_storage_id, parse_paper_id


def test_normalize_doi():
    """测试 DOI 规范化"""
    assert normalize_paper_id("10.1038/s41586-026-10265-5") == "doi:10.1038/s41586-026-10265-5"
    assert normalize_paper_id("doi:10.1038/nature") == "doi:10.1038/nature"
    assert normalize_paper_id("DOI:10.1038/nature") == "doi:10.1038/nature"


def test_normalize_arxiv():
    """测试 arXiv 规范化"""
    assert normalize_paper_id("2401.12345") == "arxiv:2401.12345"
    assert normalize_paper_id("arxiv:2401.12345") == "arxiv:2401.12345"
    assert normalize_paper_id("arXiv:2401.12345v1") == "arxiv:2401.12345"


def test_generate_storage_id():
    """测试 storage_id 生成"""
    paper_id = "doi:10.1038/s41586-026-10265-5"
    storage_id = generate_storage_id(paper_id)
    
    assert storage_id.startswith("p_")
    assert len(storage_id) == 14  # p_ + 12 chars
    
    # 幂等性
    assert generate_storage_id(paper_id) == storage_id


def test_parse_paper_id():
    """测试 paper_id 解析"""
    result = parse_paper_id("doi:10.1038/nature")
    assert result["type"] == "doi"
    assert result["value"] == "10.1038/nature"
    
    result = parse_paper_id("arxiv:2401.12345")
    assert result["type"] == "arxiv"
    assert result["value"] == "2401.12345"
```


- [ ] **Step 6: 运行 identity 测试确认失败**

```bash
uv run pytest tests/unit/test_identity.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'paperbase.core.identity'"

- [ ] **Step 7: 实现 identity 工具**

创建 `src/paperbase/core/identity.py`：

```python
"""Paper Identity 工具

处理 paper_id 规范化、storage_id 生成
"""

import re
from paperbase.utils.hash import sha256_string


def normalize_paper_id(raw: str) -> str:
    """
    规范化 paper_id
    
    优先级：doi > pmid > arxiv > openalex > s2 > fallback
    """
    raw = raw.strip()
    
    # DOI
    if raw.lower().startswith("doi:"):
        return f"doi:{raw[4:].strip()}"
    if raw.startswith("10."):
        return f"doi:{raw}"
    
    # arXiv
    arxiv_pattern = r"^(arxiv:)?(\d{4}\.\d{4,5})(v\d+)?$"
    match = re.match(arxiv_pattern, raw, re.IGNORECASE)
    if match:
        return f"arxiv:{match.group(2)}"
    
    # PMID
    if raw.lower().startswith("pmid:"):
        return f"pmid:{raw[5:].strip()}"
    if raw.startswith("PMID"):
        return f"pmid:{raw[4:].strip()}"
    
    # OpenAlex
    if raw.lower().startswith("openalex:"):
        return raw.lower()
    
    # Semantic Scholar
    if raw.lower().startswith("s2:"):
        return raw.lower()
    
    # Fallback: 使用原始值
    return f"fallback:{sha256_string(raw)[:16]}"


def generate_storage_id(paper_id: str) -> str:
    """
    生成 storage_id
    
    格式: p_<12位hash>
    """
    hash_value = sha256_string(paper_id)
    return f"p_{hash_value[:12]}"


def parse_paper_id(paper_id: str) -> dict[str, str]:
    """
    解析 paper_id
    
    返回: {type: str, value: str}
    """
    if ":" in paper_id:
        type_part, value_part = paper_id.split(":", 1)
        return {"type": type_part, "value": value_part}
    return {"type": "unknown", "value": paper_id}
```

- [ ] **Step 8: 运行 identity 测试确认通过**

```bash
uv run pytest tests/unit/test_identity.py -v
```

Expected: 所有测试 PASS


- [ ] **Step 9: 实现 PaperPaths 工具**

创建 `src/paperbase/core/paths.py`：

```python
"""Paper 路径管理"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PaperPaths:
    """论文存储路径管理"""
    storage_id: str
    base_dir: Path
    
    @property
    def paper_dir(self) -> Path:
        """论文目录"""
        return self.base_dir / "library" / "papers" / self.storage_id
    
    @property
    def paper_md(self) -> Path:
        """规范化 Markdown"""
        return self.paper_dir / "paper.md"
    
    @property
    def manifest_json(self) -> Path:
        """Manifest 文件"""
        return self.paper_dir / "manifest.json"
    
    @property
    def references_jsonl(self) -> Path:
        """引用文件"""
        return self.paper_dir / "references.jsonl"
    
    @property
    def chunks_jsonl(self) -> Path:
        """分块文件"""
        return self.paper_dir / "chunks.jsonl"
    
    @property
    def assets_dir(self) -> Path:
        """资产目录"""
        return self.paper_dir / "assets"
    
    @property
    def source_dir(self) -> Path:
        """源文件目录"""
        return self.paper_dir / "source"
    
    @property
    def source_pdf(self) -> Path:
        """源 PDF"""
        return self.source_dir / "source.pdf"
    
    def create_directories(self):
        """创建所有必需目录"""
        self.paper_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(exist_ok=True)
        self.source_dir.mkdir(exist_ok=True)
```

- [ ] **Step 10: 提交核心工具**

```bash
git add src/paperbase/core/ src/paperbase/utils/ tests/unit/test_identity.py tests/unit/test_hash.py
git commit -m "feat: add core utilities (identity, paths, hash)

Agent-Task: 实现核心工具函数
Agent-Model: claude-fable-5
Agent-Decision: identity 支持 doi/arxiv/pmid 规范化，storage_id 用 hash 生成确保唯一性
Agent-Limitation: 暂未实现 fallback paper_id 的高级处理

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交


---

### Task 5: 编写 AGENTS.md 和 CLAUDE.md

**Files:**
- Create: `AGENTS.md`
- Create: `CLAUDE.md`

**Interfaces:**
- Consumes: 项目结构和 schema 定义
- Produces: Agent 工作指南文档

- [ ] **Step 1: 创建 AGENTS.md**

```markdown
# PaperBase - Agent 工作指南

## 项目定位

PaperBase 是学术论文知识库基础设施，用于：
- 摄入、规范化、验证和图谱化学术论文
- 提供统一的 Canonical Markdown 作为 source of truth
- 支持幂等状态机管理论文处理流程

## Source of Truth

**核心原则：`library/papers/<storage_id>/paper.md` 是唯一 source of truth**

其他都是 derived artifacts（可重建）：
- `graph/` - Graphify 生成的知识图谱
- `registry/` - SQLite 快速查询索引
- `**/chunks.jsonl` - 检索用分块
- `**/references.jsonl` - 结构化引用

## 目录结构

```
paperbase/
├── src/paperbase/          # Python 包
│   ├── core/               # 核心逻辑（identity, paths, state）
│   ├── schemas/            # Pydantic schemas
│   ├── adapters/           # 外部工具适配器
│   ├── cli/                # CLI 入口
│   └── utils/              # 工具函数
├── config/                 # 配置文件
│   ├── paperbase.yaml      # 主配置
│   └── schemas/            # JSON Schema 定义
├── library/                # 知识库主体
│   ├── sources/pdf/        # 内容寻址的 PDF 存储
│   ├── papers/             # 规范化论文（Canonical）
│   ├── collections/        # 用户论文集合
│   └── notes/              # 用户笔记
├── registry/               # SQLite 索引
├── graph/                  # Graphify 输出
├── skills/                 # 项目级 skills
└── docs/                   # 文档
```

## Invariants（不可违反）

1. **每篇论文必须有唯一 `paper_id`**（doi:xxx 优先）
2. **每篇论文必须有 `manifest.json`** 记录状态和溯源
3. **不得通过自动化工作流绕过付费墙**（scansci 必须配置 `scihub_enabled=false`）
4. **Graphify 只扫描 `library/papers/**/paper.md`**（用 `.graphifyignore` 排除其他）
5. **所有资产路径必须是相对路径**（`./assets/fig-001.png`）
6. **状态转换必须更新 `manifest.json` 的 `updated_at`**
7. **不修改 `paper.md` 的 frontmatter 必须保持 `canonical_content_sha256` 不变**

## 工作流状态机

```
DISCOVERED → RESOLVED → SOURCE_READY → CONVERTED → NORMALIZED → VALIDATED → GRAPHED → READY
```

异常状态：
- `NEEDS_REVIEW`: 需要人工审核
- `BLOCKED`: 阻塞（缺依赖）
- `FAILED_RETRYABLE`: 可重试失败
- `FAILED_PERMANENT`: 永久失败

## Commands

```bash
# 摄入单篇论文
paperbase ingest "10.1038/s41586-026-10265-5"
paperbase ingest "arxiv:2401.12345"
paperbase ingest --file paper.pdf

# 搜索论文
paperbase search "machine learning"
paperbase search --zotero "reinforcement learning"

# 查询状态
paperbase status <paper_id>

# 更新图谱
paperbase graph update

# 验证知识库
paperbase validate
```

## Done Criteria

任务完成的标准：
- [ ] `manifest.json` 存在且 `state = "ready"`
- [ ] `paper.md` 存在且通过 schema validation
- [ ] `paper.md` 的 frontmatter 完整（title/authors/year/abstract）
- [ ] `references.jsonl` 存在且所有引用已 resolved
- [ ] `graph/` 已更新且 `manifest.json` 中 `graph.indexed = true`
- [ ] 所有测试通过

## 技术栈

- **项目管理**: uv
- **Schema 验证**: pydantic v2
- **Registry**: sqlite3
- **元数据标准**: CSL JSON
- **依赖项目**:
  - paper-fetch-skill (论文获取)
  - zotero-mcp (Zotero 集成)
  - graphify (知识图谱)
  - citation-check-skill (引用验证)
```


- [ ] **Step 2: 创建 CLAUDE.md**

```markdown
# PaperBase - Claude 特定指南

## 项目简介

PaperBase 是论文知识库脚手架，核心理念：
- Canonical Markdown 是唯一 source of truth
- 幂等状态机管理论文处理
- 所有投影层（graph/registry）可重建

## 快速上手

**常见任务：**

1. **摄入新论文**
   ```bash
   paperbase ingest "doi:10.1038/nature"
   ```

2. **检查论文状态**
   ```bash
   paperbase status "doi:10.1038/nature"
   ```

3. **更新知识图谱**
   ```bash
   paperbase graph update
   ```

## Canonical Schema 位置

- Paper frontmatter: `src/paperbase/schemas/paper.py` - `PaperMetadata`
- Manifest: `src/paperbase/schemas/manifest.py` - `ManifestSchema`
- CSL JSON: `src/paperbase/schemas/csl.py` - `CSLItem`

## 修改边界

**可修改：**
- 实现新的 adapter（`src/paperbase/adapters/`）
- 添加新的 CLI 命令（`src/paperbase/cli/`）
- 扩展 schema 字段（向后兼容）

**不可修改（除非明确要求）：**
- Canonical Schema 的核心字段（schema_version/paper_id/storage_id）
- 状态机转换规则
- Invariants（AGENTS.md 中列出的）
- library/ 目录结构

## 调试建议

1. **查看 manifest.json** 确认状态
2. **检查 paper.md frontmatter** 是否通过 schema 验证
3. **查看 registry/papers.sqlite** 确认索引状态
4. **检查 .graphifyignore** 确保 Graphify 不扫描重复内容

## Skills 使用

项目集成的 skills：
- `paper-fetch-skill`: 在 `skills/paper-fetch-skill/`
- `citation-check-skill`: 在 `skills/citation-check-skill/`
- `zotero-mcp`: 通过 MCP 调用
- `graphify`: 通过 MCP 调用

## 测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/unit/test_schemas.py -v

# 测试覆盖率
uv run pytest --cov=paperbase --cov-report=html
```
```

- [ ] **Step 3: 提交文档**

```bash
git add AGENTS.md CLAUDE.md
git commit -m "docs: add AGENTS.md and CLAUDE.md

Agent-Task: 编写 Agent 工作指南
Agent-Model: claude-fable-5
Agent-Decision: AGENTS.md 包含 invariants 和状态机，CLAUDE.md 包含快速上手
Agent-Limitation: 具体 CLI 命令实现尚未完成

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交


---

## Phase 2: 状态管理和 Registry

### Task 6: 实现 Registry

**Files:**
- Create: `src/paperbase/core/registry.py`
- Create: `tests/unit/test_registry.py`

**Interfaces:**
- Consumes: sqlite3, ManifestSchema
- Produces:
  - `PaperRegistry` (class)
  - `register_paper(paper_id, storage_id, state)`
  - `get_paper(paper_id) -> dict | None`
  - `list_papers(state: PaperState | None) -> list[dict]`

- [ ] **Step 1: 编写 registry 测试**

创建 `tests/unit/test_registry.py`：

```python
import pytest
from pathlib import Path
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState


@pytest.fixture
def registry(tmp_path):
    """创建临时 registry"""
    db_path = tmp_path / "test.db"
    return PaperRegistry(db_path)


def test_registry_init(registry):
    """测试 registry 初始化"""
    assert registry.conn is not None


def test_register_paper(registry):
    """测试注册论文"""
    registry.register_paper(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        state=PaperState.DISCOVERED,
        title="Test Paper",
        authors=["John Smith"],
        year=2026
    )
    
    paper = registry.get_paper("doi:10.1234/test")
    assert paper is not None
    assert paper["paper_id"] == "doi:10.1234/test"
    assert paper["state"] == "discovered"
    assert paper["title"] == "Test Paper"


def test_get_paper_not_found(registry):
    """测试查询不存在的论文"""
    paper = registry.get_paper("doi:10.1234/notexist")
    assert paper is None


def test_update_state(registry):
    """测试更新状态"""
    registry.register_paper(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        state=PaperState.DISCOVERED,
        title="Test",
        authors=[],
        year=2026
    )
    
    registry.update_state("doi:10.1234/test", PaperState.READY)
    
    paper = registry.get_paper("doi:10.1234/test")
    assert paper["state"] == "ready"


def test_list_papers_by_state(registry):
    """测试按状态查询"""
    registry.register_paper(
        paper_id="doi:10.1234/test1",
        storage_id="p_abc123",
        state=PaperState.READY,
        title="Test1",
        authors=[],
        year=2026
    )
    registry.register_paper(
        paper_id="doi:10.1234/test2",
        storage_id="p_abc124",
        state=PaperState.DISCOVERED,
        title="Test2",
        authors=[],
        year=2026
    )
    
    ready_papers = registry.list_papers(state=PaperState.READY)
    assert len(ready_papers) == 1
    assert ready_papers[0]["paper_id"] == "doi:10.1234/test1"
```


- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_registry.py::test_registry_init -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'paperbase.core.registry'"

- [ ] **Step 3: 实现 PaperRegistry**

创建 `src/paperbase/core/registry.py`：

```python
"""Paper Registry 实现

使用 SQLite 存储论文索引和状态
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from paperbase.schemas.manifest import PaperState


class PaperRegistry:
    """论文索引 Registry"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
    
    def _init_schema(self):
        """初始化数据库 schema"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                storage_id TEXT NOT NULL,
                state TEXT NOT NULL,
                title TEXT,
                authors TEXT,  -- JSON array
                year INTEGER,
                doi TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_state ON papers(state)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year)
        """)
        self.conn.commit()
    
    def register_paper(
        self,
        paper_id: str,
        storage_id: str,
        state: PaperState,
        title: str | None = None,
        authors: list[str] | None = None,
        year: int | None = None,
        doi: str | None = None
    ):
        """注册或更新论文"""
        authors_json = json.dumps(authors or [])
        now = datetime.utcnow().isoformat()
        
        self.conn.execute("""
            INSERT INTO papers (paper_id, storage_id, state, title, authors, year, doi, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
                storage_id = excluded.storage_id,
                state = excluded.state,
                title = excluded.title,
                authors = excluded.authors,
                year = excluded.year,
                doi = excluded.doi,
                updated_at = excluded.updated_at
        """, (paper_id, storage_id, state.value, title, authors_json, year, doi, now))
        self.conn.commit()
    
    def get_paper(self, paper_id: str) -> dict | None:
        """查询单篇论文"""
        cursor = self.conn.execute(
            "SELECT * FROM papers WHERE paper_id = ?",
            (paper_id,)
        )
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result["authors"] = json.loads(result["authors"])
            return result
        return None
    
    def update_state(self, paper_id: str, state: PaperState):
        """更新论文状态"""
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "UPDATE papers SET state = ?, updated_at = ? WHERE paper_id = ?",
            (state.value, now, paper_id)
        )
        self.conn.commit()
    
    def list_papers(self, state: PaperState | None = None) -> list[dict]:
        """列出论文"""
        if state:
            cursor = self.conn.execute(
                "SELECT * FROM papers WHERE state = ? ORDER BY updated_at DESC",
                (state.value,)
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM papers ORDER BY updated_at DESC"
            )
        
        results = []
        for row in cursor.fetchall():
            result = dict(row)
            result["authors"] = json.loads(result["authors"])
            results.append(result)
        return results
    
    def close(self):
        """关闭连接"""
        self.conn.close()
```


- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/unit/test_registry.py -v
```

Expected: 所有测试 PASS

- [ ] **Step 5: 提交 Registry**

```bash
git add src/paperbase/core/registry.py tests/unit/test_registry.py
git commit -m "feat: implement paper registry with SQLite

Agent-Task: 实现 PaperRegistry
Agent-Model: claude-fable-5
Agent-Decision: 使用 sqlite3 标准库，authors 存储为 JSON，支持按状态查询
Agent-Limitation: 暂未实现全文搜索和复杂查询

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交

---

### Task 7: 实现 Manifest 管理

**Files:**
- Create: `src/paperbase/core/manifest.py`
- Create: `tests/unit/test_manifest.py`

**Interfaces:**
- Consumes: ManifestSchema, PaperPaths
- Produces:
  - `load_manifest(path: Path) -> ManifestSchema`
  - `save_manifest(manifest: ManifestSchema, path: Path)`
  - `create_manifest(paper_id: str, storage_id: str) -> ManifestSchema`

- [ ] **Step 1: 编写 manifest 测试**

创建 `tests/unit/test_manifest.py`：

```python
import pytest
import json
from pathlib import Path
from paperbase.core.manifest import load_manifest, save_manifest, create_manifest
from paperbase.schemas.manifest import PaperState


def test_create_manifest():
    """测试创建 manifest"""
    manifest = create_manifest(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123"
    )
    assert manifest.paper_id == "doi:10.1234/test"
    assert manifest.storage_id == "p_abc123"
    assert manifest.state == PaperState.DISCOVERED


def test_save_and_load_manifest(tmp_path):
    """测试保存和加载 manifest"""
    manifest = create_manifest(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123"
    )
    
    manifest_path = tmp_path / "manifest.json"
    save_manifest(manifest, manifest_path)
    
    assert manifest_path.exists()
    
    loaded = load_manifest(manifest_path)
    assert loaded.paper_id == manifest.paper_id
    assert loaded.state == manifest.state


def test_manifest_json_format(tmp_path):
    """测试 manifest JSON 格式"""
    manifest = create_manifest(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123"
    )
    manifest.state = PaperState.READY
    
    manifest_path = tmp_path / "manifest.json"
    save_manifest(manifest, manifest_path)
    
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    
    assert data["paper_id"] == "doi:10.1234/test"
    assert data["state"] == "ready"
```


- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_manifest.py::test_create_manifest -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'paperbase.core.manifest'"

- [ ] **Step 3: 实现 Manifest 管理**

创建 `src/paperbase/core/manifest.py`：

```python
"""Manifest 管理工具"""

import json
from pathlib import Path
from datetime import datetime
from paperbase.schemas.manifest import ManifestSchema, PaperState


def create_manifest(paper_id: str, storage_id: str) -> ManifestSchema:
    """创建新的 manifest"""
    now = datetime.utcnow().isoformat() + "Z"
    return ManifestSchema(
        paper_id=paper_id,
        storage_id=storage_id,
        state=PaperState.DISCOVERED,
        created_at=now,
        updated_at=now
    )


def load_manifest(path: Path) -> ManifestSchema:
    """从文件加载 manifest"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return ManifestSchema.model_validate(data)


def save_manifest(manifest: ManifestSchema, path: Path):
    """保存 manifest 到文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # 更新 updated_at
    manifest.updated_at = datetime.utcnow().isoformat() + "Z"
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            manifest.model_dump(mode="json", exclude_none=True),
            f,
            indent=2,
            ensure_ascii=False
        )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/unit/test_manifest.py -v
```

Expected: 所有测试 PASS

- [ ] **Step 5: 提交 Manifest 管理**

```bash
git add src/paperbase/core/manifest.py tests/unit/test_manifest.py
git commit -m "feat: implement manifest management

Agent-Task: 实现 Manifest 加载、保存和创建
Agent-Model: claude-fable-5
Agent-Decision: 自动更新 updated_at，使用 pydantic model_dump 确保格式正确
Agent-Limitation: 暂未实现 manifest 迁移和版本管理

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交


---

## Phase 3: CLI 基础框架

### Task 8: 实现基础 CLI

**Files:**
- Create: `src/paperbase/cli/main.py`
- Create: `src/paperbase/cli/commands/__init__.py`
- Create: `src/paperbase/cli/commands/status.py`

**Interfaces:**
- Consumes: click, rich, PaperRegistry
- Produces:
  - `paperbase` CLI 入口
  - `paperbase status` 命令

- [ ] **Step 1: 实现 CLI 入口**

创建 `src/paperbase/cli/main.py`：

```python
"""PaperBase CLI 入口"""

import click
from pathlib import Path


@click.group()
@click.version_option(version="0.1.0")
@click.option(
    "--base-dir",
    type=click.Path(path_type=Path),
    default=Path.cwd(),
    help="PaperBase 根目录"
)
@click.pass_context
def main(ctx, base_dir: Path):
    """PaperBase - 学术论文知识库"""
    ctx.ensure_object(dict)
    ctx.obj["base_dir"] = base_dir


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 实现 status 命令**

创建 `src/paperbase/cli/commands/status.py`：

```python
"""status 命令实现"""

import click
from rich.console import Console
from rich.table import Table
from pathlib import Path
from paperbase.core.registry import PaperRegistry


@click.command()
@click.argument("paper_id", required=False)
@click.pass_context
def status(ctx, paper_id: str | None):
    """查询论文状态"""
    console = Console()
    base_dir = ctx.obj["base_dir"]
    registry_path = base_dir / "registry" / "papers.db"
    
    if not registry_path.exists():
        console.print("[yellow]Registry 不存在，请先摄入论文[/yellow]")
        return
    
    registry = PaperRegistry(registry_path)
    
    if paper_id:
        # 查询单篇
        paper = registry.get_paper(paper_id)
        if paper:
            console.print(f"[bold]Paper ID:[/bold] {paper['paper_id']}")
            console.print(f"[bold]Storage ID:[/bold] {paper['storage_id']}")
            console.print(f"[bold]State:[/bold] {paper['state']}")
            console.print(f"[bold]Title:[/bold] {paper['title']}")
            console.print(f"[bold]Year:[/bold] {paper['year']}")
        else:
            console.print(f"[red]未找到论文: {paper_id}[/red]")
    else:
        # 列出所有
        papers = registry.list_papers()
        if not papers:
            console.print("[yellow]知识库为空[/yellow]")
            return
        
        table = Table(title="PaperBase 论文列表")
        table.add_column("Paper ID", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Year", style="magenta")
        table.add_column("State", style="green")
        
        for paper in papers[:20]:  # 限制 20 条
            table.add_row(
                paper["paper_id"],
                paper["title"] or "N/A",
                str(paper["year"]) if paper["year"] else "N/A",
                paper["state"]
            )
        
        console.print(table)
        if len(papers) > 20:
            console.print(f"\n[dim]... 还有 {len(papers) - 20} 篇论文[/dim]")
    
    registry.close()
```


- [ ] **Step 3: 注册 status 命令**

在 `src/paperbase/cli/main.py` 中添加：

```python
from paperbase.cli.commands.status import status

# 在 main() 函数后添加
main.add_command(status)
```

- [ ] **Step 4: 手动测试 CLI**

```bash
uv run paperbase --help
uv run paperbase status
```

Expected: 显示帮助信息和状态命令输出

- [ ] **Step 5: 提交 CLI 基础**

```bash
git add src/paperbase/cli/
git commit -m "feat: add basic CLI with status command

Agent-Task: 实现 CLI 基础框架
Agent-Model: claude-fable-5
Agent-Decision: 使用 click 作为 CLI 框架，rich 美化输出
Agent-Limitation: 暂未实现 ingest/search/graph 等核心命令

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交

---

## Phase 4: 集成准备

### Task 9: 配置 Skills 目录结构

**Files:**
- Create: `scripts/setup_skills.py`
- Create: `.graphifyignore`
- Update: `config/paperbase.yaml`

**Interfaces:**
- Consumes: 项目配置
- Produces: Skills 安装脚本和 Graphify 配置

- [ ] **Step 1: 创建 .graphifyignore**

```gitignore
# 源文件和备份
sources/
**/source/
**/*.pdf

# Registry 和状态文件
registry/
**/manifest.json
**/chunks.jsonl
**/references.jsonl

# 构建产物
__pycache__/
*.pyc
.venv/
uv.lock

# 临时文件
*.tmp
*.log
.DS_Store
```

- [ ] **Step 2: 创建 Skills 安装脚本**

创建 `scripts/setup_skills.py`：

```python
"""Skills 安装和配置脚本"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str):
    """运行命令并处理错误"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"❌ 失败: {result.stderr}", file=sys.stderr)
        return False
    print("✅ 成功")
    return True


def main():
    base_dir = Path(__file__).parent.parent
    skills_dir = base_dir / "skills"
    skills_dir.mkdir(exist_ok=True)
    
    print("🚀 PaperBase Skills 安装")
    
    # 1. paper-fetch-skill
    if not (skills_dir / "paper-fetch-skill").exists():
        run_command(
            ["git", "clone", "https://github.com/Dictation354/paper-fetch-skill.git",
             str(skills_dir / "paper-fetch-skill")],
            "📥 克隆 paper-fetch-skill"
        )
    
    # 2. citation-check-skill
    print("\n⚠️  citation-check-skill 需要手动下载 release zip 并解压到 skills/")
    print("    下载地址: https://github.com/serenakeyitan/citation-check-skill/releases")
    
    # 3. zotero-mcp
    run_command(
        ["uv", "tool", "install", "zotero-mcp-server"],
        "📦 安装 zotero-mcp"
    )
    
    # 4. graphify
    run_command(
        ["uv", "tool", "install", "graphify"],
        "📦 安装 graphify"
    )
    
    print("\n" + "="*60)
    print("✨ Skills 安装完成")
    print("="*60)


if __name__ == "__main__":
    main()
```


- [ ] **Step 3: 运行 Skills 安装脚本**

```bash
uv run python scripts/setup_skills.py
```

Expected: 成功安装 zotero-mcp 和 graphify

- [ ] **Step 4: 验证 Skills 安装**

```bash
# 检查 zotero-mcp
zotero-cli --version

# 检查 graphify
graphify --version
```

Expected: 显示版本信息

- [ ] **Step 5: 提交 Skills 配置**

```bash
git add scripts/setup_skills.py .graphifyignore
git commit -m "feat: add skills setup script and graphify ignore config

Agent-Task: 配置 Skills 集成
Agent-Model: claude-fable-5
Agent-Decision: 自动化安装 zotero-mcp 和 graphify，paper-fetch 通过 git clone
Agent-Limitation: citation-check-skill 需要手动下载

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交

---

## 验收标准

完成以上所有 Task 后，项目应满足：

### 结构完整性
- [ ] 所有目录结构创建完成
- [ ] `pyproject.toml` 配置正确
- [ ] `uv.lock` 生成且依赖安装成功

### Schema 定义
- [ ] `PaperMetadata` schema 定义完整且测试通过
- [ ] `ManifestSchema` schema 定义完整且测试通过
- [ ] `CSLItem` schema 定义完整且测试通过

### 核心功能
- [ ] Identity 工具（normalize_paper_id, generate_storage_id）测试通过
- [ ] PaperPaths 工具正常工作
- [ ] Hash 工具测试通过
- [ ] PaperRegistry 实现完整且测试通过
- [ ] Manifest 管理实现完整且测试通过

### CLI
- [ ] `paperbase --help` 正常显示
- [ ] `paperbase status` 命令可执行（即使知识库为空）

### 文档
- [ ] AGENTS.md 包含完整的 invariants 和工作流说明
- [ ] CLAUDE.md 包含快速上手指南
- [ ] README.md 描述清晰

### Skills 集成准备
- [ ] `.graphifyignore` 配置正确
- [ ] Skills 安装脚本可运行
- [ ] zotero-mcp 和 graphify 安装成功

### 测试覆盖
- [ ] 所有 unit 测试通过
- [ ] 测试覆盖率 > 80%

---

## 后续工作

Phase 1 完成后，后续开发方向：

### Phase 2: 论文摄入流程
- 实现 paper-fetch adapter
- 实现 normalizer（候选 MD → Canonical MD）
- 实现 `paperbase ingest` 命令
- 实现状态机转换

### Phase 3: 图谱集成
- 实现 Graphify adapter
- 实现 `paperbase graph update` 命令
- 实现图谱查询

### Phase 4: 搜索和查询
- 集成 Zotero MCP
- 实现 `paperbase search` 命令
- 实现全文检索

### Phase 5: 验证和审计
- 集成 citation-check-skill
- 实现 `paperbase validate` 命令
- 实现引用验证流程

---

## 自检清单

在标记计划为"完成"前，确认：

1. **Schema 一致性**: 所有 pydantic models 字段名与设计文档一致
2. **路径正确性**: 所有路径使用 `/` 或 `Path` 对象
3. **测试完整性**: 每个公开函数都有对应测试
4. **文档准确性**: AGENTS.md 和 CLAUDE.md 与实际代码一致
5. **编码规范**: 所有文件使用 UTF-8，遵循 ruff 规则
6. **Git 提交**: 每个 Task 完成后提交，commit message 符合规范
7. **依赖明确**: 所有外部依赖在 pyproject.toml 中声明
8. **配置完整**: config/paperbase.yaml 覆盖所有必需配置项

---

## 实施建议

1. **按顺序执行**: Task 之间有依赖关系，必须按序完成
2. **TDD 严格**: 先写测试，确认失败，再写实现，确认通过
3. **频繁提交**: 每个 Task 完成后立即提交
4. **验证充分**: 每个 step 执行后确认 Expected 结果
5. **问题记录**: 遇到偏差立即记录到 Agent-Limitation
6. **保持简单**: 只实现必需功能，不添加额外特性

