# PaperBase 问题汇总与修复记录

**记录时间**: 2026-07-08  
**涉及模块**: LLM 配置、CLI 命令、实体提取

---

## 问题清单

### 问题 1: 项目未加载 .env 文件 ⚠️

**优先级**: High  
**状态**: ✅ 已修复

**描述**:
- 项目代码中没有 `load_dotenv()` 调用
- 即使 `.env` 配置正确，环境变量也无法生效

**修复**:
- `src/paperbase/cli/main.py`: 添加 `load_dotenv()`
- `src/paperbase/core/llm_client.py`: 添加 `load_dotenv()`

**文件变更**:
- `src/paperbase/cli/main.py` (+2 行)
- `src/paperbase/core/llm_client.py` (+3 行)

---

### 问题 2: LLM 功能默认禁用 ℹ️

**优先级**: Medium  
**状态**: ✅ 已修复

**描述**:
- `config/paperbase.yaml` 中 `llm.enabled: false`
- 用户配置环境变量后仍无法使用 LLM

**修复**:
- `config/paperbase.yaml`: 改为 `llm.enabled: true`

**文件变更**:
- `config/paperbase.yaml` (1 行)

**讨论**:
- 是否应该默认启用需要权衡
- 建议：保持 `false`，但在 `doctor` 命令中明确提示

---

### 问题 3: 配置文件路径计算错误 🐛

**优先级**: Critical  
**状态**: ✅ 已修复

**描述**:
- `LLMClient._load_config()` 中路径计算少一级 `parent`
- 查找 `src/config/paperbase.yaml` 而非 `config/paperbase.yaml`
- 找不到配置时静默返回默认值 `{"llm": {"enabled": False}}`

**修复**:
```python
# 修复前
config_path = Path(__file__).parent.parent.parent / "config" / "paperbase.yaml"

# 修复后
config_path = Path(__file__).parent.parent.parent.parent / "config" / "paperbase.yaml"
```

**文件变更**:
- `src/paperbase/core/llm_client.py` (1 行)

**改进建议**:
- 配置文件不存在时应该抛出异常或记录 WARNING 日志
- 使用环境变量或配置项指定配置路径，而非硬编码相对路径

---

### 问题 4: 缺少独立的实体提取命令 🆕

**优先级**: High  
**状态**: ✅ 已修复

**描述**:
- 实体提取只能在 `ingest` 时触发
- 对于已摄入但未提取实体的论文，没有官方方法重新提取
- 用户只能编写脚本调用内部 API

**修复**:
- 新增 `paperbase extract` 命令
- 支持单篇提取、批量提取、强制覆盖
- 智能跳过已有实体的论文

**文件变更**:
- `src/paperbase/cli/commands/extract.py` (新增, ~300 行)
- `src/paperbase/cli/main.py` (+2 行)

**功能特性**:
```bash
paperbase extract <paper_id>        # 单篇提取
paperbase extract --all             # 批量提取未提取的论文
paperbase extract --all --force     # 强制重新提取所有论文
paperbase extract --output-json     # JSON 输出
```

---

## 架构问题

### A1: 配置加载时机不确定 ⚠️

**描述**:
- `load_dotenv()` 分散在 CLI 入口和 LLMClient 模块
- 导入顺序可能影响环境变量加载

**建议改进**:
```python
# src/paperbase/__init__.py
from dotenv import load_dotenv

# 包初始化时加载，确保任何导入都生效
load_dotenv()
```

---

### A2: 路径计算依赖 `__file__` ⚠️

**描述**:
- 使用 `Path(__file__).parent.parent...` 计算路径
- 脆弱、易出错、难以测试

**建议改进**:
```python
# 使用环境变量或配置项
CONFIG_PATH = os.getenv("PAPERBASE_CONFIG", "config/paperbase.yaml")

# 或使用包管理器的资源 API
from importlib.resources import files
config_path = files("paperbase").joinpath("../config/paperbase.yaml")
```

---

### A3: 错误被静默处理 ⚠️

**描述**:
- 配置文件不存在时返回默认值，不报错
- 用户无法发现配置加载失败

**建议改进**:
```python
if not config_path.exists():
    logger.warning(f"Config file not found: {config_path}")
    logger.info("Using default config (LLM disabled)")
    return {"llm": {"enabled": False}}
```

---

### A4: 缺少配置诊断工具 ℹ️

**描述**:
- 用户无法验证配置是否正确加载
- 没有命令查看当前配置状态

**建议改进**:
```bash
# 新增命令
paperbase config show           # 显示当前配置
paperbase config check-llm      # 验证 LLM 配置
paperbase config path           # 显示配置文件路径
```

---

## 测试覆盖

### 需要添加的测试

#### T1: LLMClient 配置加载测试

```python
def test_llm_client_config_loading():
    """测试配置文件正确加载"""
    client = LLMClient()
    assert client.config is not None
    assert "llm" in client.config

def test_llm_client_missing_config():
    """测试配置文件不存在时的行为"""
    client = LLMClient(config_path=Path("/nonexistent/config.yaml"))
    assert client.enabled is False
```

#### T2: 环境变量展开测试

```python
def test_env_var_expansion():
    """测试环境变量正确展开"""
    os.environ["TEST_VAR"] = "test_value"
    config = {"llm": {"base_url": "${TEST_VAR}"}}
    
    client = LLMClient(config=config)
    assert client.config["llm"]["base_url"] == "test_value"
```

#### T3: extract 命令测试

```python
def test_extract_command_single():
    """测试单篇论文提取"""
    result = runner.invoke(extract, ["doi:test"])
    assert result.exit_code == 0

def test_extract_command_all():
    """测试批量提取"""
    result = runner.invoke(extract, ["--all"])
    assert result.exit_code == 0
```

---

## 文档更新清单

### 必须更新

- [ ] `README.md`: 添加 LLM 配置说明
- [ ] `README.md`: 添加 `extract` 命令示例
- [ ] `.env.example`: 已完善 ✅
- [ ] `docs/cli-reference.md`: 添加 `extract` 命令文档
- [ ] `docs/troubleshooting/llm-config-issues.md`: 已创建 ✅

### 建议添加

- [ ] `docs/architecture/configuration.md`: 配置加载机制说明
- [ ] `docs/workflows/entity-extraction.md`: 实体提取工作流
- [ ] `docs/improvements/extract-command.md`: 已创建 ✅

---

## 代码质量改进

### Q1: 添加类型注解 ℹ️

**当前**:
```python
def _load_config(self, config_path):
    ...
```

**改进**:
```python
def _load_config(self, config_path: Path | None) -> dict[str, Any]:
    ...
```

---

### Q2: 提取魔法字符串 ℹ️

**当前**:
```python
if 'entities:' in content and '- name:' in content:
    ...
```

**改进**:
```python
# 在 constants.py 中定义
ENTITY_MARKER = 'entities:'
ENTITY_NAME_MARKER = '- name:'

# 或使用 YAML 解析
frontmatter = yaml.safe_load(content.split('---')[1])
has_entities = bool(frontmatter.get('entities'))
```

---

### Q3: 增强日志记录 ℹ️

**当前**: 只有部分关键路径有日志

**改进**:
```python
logger.debug(f"Loading config from: {config_path}")
logger.debug(f"Expanding env var: {env_var} = {os.getenv(env_var)}")
logger.info(f"LLM client initialized: {base_url} / {model}")
```

---

## 性能优化

### P1: 批量提取时的并发控制 💡

**当前**: 串行处理，速度慢

**改进**: 
```python
# 使用 asyncio 或 ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(extract, paper) for paper in papers]
    results = [f.result() for f in futures]
```

**注意**: 需考虑 API rate limit

---

### P2: 实体提取结果缓存 💡

**当前**: 重复提取相同内容会重复调用 LLM

**改进**:
```python
# 在 manifest.json 记录
{
  "entities_cache": {
    "content_sha256": "abc123...",
    "extracted_at": "2026-07-08T19:30:00Z",
    "model": "mimo-v2.5",
    "entities": {...}
  }
}

# 提取前检查
if manifest.entities_cache and manifest.entities_cache.content_sha256 == current_sha256:
    return manifest.entities_cache.entities
```

---

## 安全问题

### S1: API Key 泄漏风险 ⚠️

**风险**: 日志或错误信息可能泄漏 API key

**检查**:
```bash
# 搜索是否有地方会输出 api_key
grep -r "api_key" src/ --include="*.py"
```

**建议**:
- 日志中脱敏: `api_key[:8] + "..."`
- 错误信息中不包含 key

---

## 修复优先级

### P0 (立即修复)
- ✅ 问题 1: 项目未加载 .env
- ✅ 问题 3: 配置文件路径错误

### P1 (本周修复)
- ✅ 问题 4: 缺少 extract 命令
- [ ] A3: 错误被静默处理
- [ ] A4: 缺少配置诊断工具

### P2 (下次迭代)
- [ ] A1: 配置加载时机不确定
- [ ] A2: 路径计算依赖 `__file__`
- [ ] Q2: 提取魔法字符串
- [ ] Q3: 增强日志记录

### P3 (未来考虑)
- [ ] P1: 批量提取并发控制
- [ ] P2: 实体提取结果缓存

---

## 总结

### 修复的问题
1. ✅ .env 文件未加载
2. ✅ LLM 功能默认禁用
3. ✅ 配置文件路径计算错误
4. ✅ 缺少独立的实体提取命令

### 遗留的架构问题
- 配置加载机制不够健壮
- 缺少配置诊断工具
- 错误处理不够明确

### 建议的改进方向
- 增强配置系统的可观测性
- 添加更多诊断和验证工具
- 改进日志和错误提示
- 考虑性能优化和缓存策略

### 测试覆盖率
- 当前: 未知（需要运行 pytest --cov）
- 目标: 核心模块 > 80%

### 文档完整度
- 当前: 部分文档缺失
- 需要: CLI 参考、故障排查、工作流指南
