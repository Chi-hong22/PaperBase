# PaperBase 配置重构方案

**目标**: 将平面配置改为层级配置，隐藏实现细节，只暴露关键决策点

---

## 设计原则

### 1. 最小配置原则
用户只需配置**关键决策点**，其他参数由系统自动推导。

### 2. 配置分层原则
```
用户配置（必需）
  ↓
系统推导（自动）
  ↓
实现细节（隐藏）
```

### 3. 明确依赖关系
配置项之间的依赖关系应该在代码中验证，而不是让用户自己理解。

---

## 当前配置问题

### 问题 1: LLM 配置平面化

**现状**:
```yaml
llm:
  enabled: true
  base_url: ${PAPERBASE_LLM_BASE_URL}
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: ${PAPERBASE_LLM_MODEL}
  auto_extract_on_ingest: true
  extract_timeout: 30
  max_content_length: 4000
```

**问题**:
- `enabled: true` 后，用户需要手动配置 `base_url`、`api_key`、`model`
- 如果任何一个为空，运行时才报错
- `auto_extract_on_ingest` 依赖 `enabled`，但配置中看不出来
- `extract_timeout`、`max_content_length` 是实现细节，不应该暴露

**改进**:
```yaml
llm:
  # 用户只需决定：是否使用 LLM
  # 如果使用，提供连接信息即可
  provider: openai              # 或 anthropic, ollama, custom
  
  # 根据 provider 自动推导 base_url
  # openai → https://api.openai.com/v1
  # ollama → http://localhost:11434/v1
  # custom → 用户手动指定
  
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: gpt-4o-mini
  
  # 可选：高级配置（有合理默认值）
  advanced:
    timeout: 30              # 默认 30 秒
    max_input_tokens: 4000   # 默认 4000
    retry_on_failure: true   # 默认开启重试
```

**验证逻辑**（代码中处理）:
```python
if config.llm.provider:
    # 自动推导 base_url
    if config.llm.provider == "openai":
        base_url = "https://api.openai.com/v1"
    elif config.llm.provider == "ollama":
        base_url = "http://localhost:11434/v1"
    elif config.llm.provider == "custom":
        base_url = config.llm.base_url or raise ConfigError("custom provider requires base_url")
    
    # 验证必需参数
    if not config.llm.model:
        raise ConfigError("llm.model is required when llm.provider is set")
    
    # api_key 可选（本地 LLM 不需要）
    if config.llm.provider in ["openai", "anthropic"] and not config.llm.api_key:
        raise ConfigError(f"{provider} requires api_key")
```

---

### 问题 2: Graph 配置冗余

**现状**:
```yaml
graphify:
  auto_update: true
  ignore_patterns: [...]

graph:
  auto_update: true
  update_mode: incremental
  auto_update_on:
    - entity_change
    - paper_ingest
```

**问题**:
- `graphify.auto_update` 和 `graph.auto_update` 看起来重复
- 用户不清楚两者的关系
- `update_mode`、`auto_update_on` 是实现细节

**改进**:
```yaml
graph:
  # 用户只需决定：何时更新图谱
  auto_update: on_entity_change    # 选项: never, on_ingest, on_entity_change, always
  
  # 系统根据 auto_update 自动推导：
  # - never: 从不自动更新
  # - on_ingest: 新论文摄入时更新
  # - on_entity_change: 实体变化时更新（最常用）
  # - always: 任何变化都更新
  
  # 可选：高级配置
  advanced:
    mode: incremental    # 或 full，默认 incremental
    ignore_patterns:     # 从 graphify 移到这里
      - "**/source/"
      - "**/*.pdf"
```

**验证逻辑**:
```python
if config.graph.auto_update == "on_entity_change":
    # 自动推导
    config.graph.triggers = ["entity_change", "paper_ingest"]
    config.graph.mode = "incremental"
elif config.graph.auto_update == "always":
    config.graph.triggers = ["any"]
    config.graph.mode = "full"
```

---

### 问题 3: Adapter 配置细节过多

**现状**:
```yaml
adapters:
  paper_fetch:
    enabled: true
    artifact_mode: "markdown-assets"
    asset_profile: "body"
    include_refs: "all"
    max_tokens: "full_text"
    allow_metadata_only: false
```

**问题**:
- 用户需要理解 `artifact_mode`、`asset_profile` 等术语
- 大部分场景只需要"启用"或"禁用"
- 这些是实现细节，不是用户决策

**改进**:
```yaml
adapters:
  paper_fetch:
    enabled: true
    quality: high        # 选项: minimal, standard, high
    
    # 系统根据 quality 自动推导：
    # minimal: 只要元数据
    # standard: 元数据 + 摘要
    # high: 全文 + 引用 + 资源
```

**验证逻辑**:
```python
if config.adapters.paper_fetch.quality == "high":
    # 自动推导实现参数
    config.adapters.paper_fetch._artifact_mode = "markdown-assets"
    config.adapters.paper_fetch._asset_profile = "body"
    config.adapters.paper_fetch._include_refs = "all"
    config.adapters.paper_fetch._max_tokens = "full_text"
elif config.adapters.paper_fetch.quality == "minimal":
    config.adapters.paper_fetch._allow_metadata_only = True
```

---

## 改进后的配置示例

### 简化版（推荐给普通用户）

```yaml
# PaperBase 配置文件（简化版）

# === 核心配置 ===

# LLM 配置（可选）
llm:
  provider: openai              # openai / anthropic / ollama / custom
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: gpt-4o-mini

# 图谱配置
graph:
  auto_update: on_entity_change  # never / on_ingest / on_entity_change / always

# 论文摄入质量
adapters:
  paper_fetch:
    enabled: true
    quality: high               # minimal / standard / high

# === 高级配置（可选） ===

# 如果需要自定义，取消下面的注释：
# llm:
#   advanced:
#     timeout: 30
#     max_input_tokens: 4000
#
# graph:
#   advanced:
#     mode: incremental
#     ignore_patterns: [...]
```

### 完整版（给高级用户）

```yaml
# PaperBase 配置文件（完整版）

llm:
  provider: custom
  base_url: https://my-llm.example.com/v1
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: custom-model
  
  advanced:
    timeout: 60
    max_input_tokens: 8000
    retry_on_failure: true
    retry_count: 3
    retry_delay: 1

graph:
  auto_update: always
  
  advanced:
    mode: full
    ignore_patterns:
      - "**/custom/"
    parallel_workers: 4

adapters:
  paper_fetch:
    enabled: true
    quality: custom
    
    advanced:
      artifact_mode: "custom-mode"
      asset_profile: "custom-profile"
```

---

## 配置验证层

### 实现：ConfigValidator

```python
from pydantic import BaseModel, field_validator, model_validator

class LLMConfig(BaseModel):
    provider: Literal["openai", "anthropic", "ollama", "custom"] | None = None
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None  # 仅 provider=custom 时需要
    
    advanced: dict = {}  # 可选高级配置
    
    @field_validator("provider")
    def validate_provider(cls, v):
        if v not in [None, "openai", "anthropic", "ollama", "custom"]:
            raise ValueError(f"Invalid provider: {v}")
        return v
    
    @model_validator(mode="after")
    def validate_dependencies(self):
        """验证配置依赖关系"""
        
        # 如果配置了 provider，必须配置 model
        if self.provider and not self.model:
            raise ValueError("llm.model is required when llm.provider is set")
        
        # openai/anthropic 需要 api_key
        if self.provider in ["openai", "anthropic"] and not self.api_key:
            raise ValueError(f"{self.provider} requires api_key")
        
        # custom provider 需要 base_url
        if self.provider == "custom" and not self.base_url:
            raise ValueError("custom provider requires base_url")
        
        return self
    
    def is_enabled(self) -> bool:
        """推导：LLM 是否启用"""
        return self.provider is not None
    
    def get_base_url(self) -> str:
        """推导：base_url"""
        if self.provider == "openai":
            return "https://api.openai.com/v1"
        elif self.provider == "anthropic":
            return "https://api.anthropic.com/v1"
        elif self.provider == "ollama":
            return "http://localhost:11434/v1"
        elif self.provider == "custom":
            return self.base_url
        else:
            raise ValueError("provider not set")
    
    def get_timeout(self) -> int:
        """推导：超时时间"""
        return self.advanced.get("timeout", 30)


class GraphConfig(BaseModel):
    auto_update: Literal["never", "on_ingest", "on_entity_change", "always"] = "on_entity_change"
    advanced: dict = {}
    
    def get_triggers(self) -> list[str]:
        """推导：触发条件"""
        if self.auto_update == "never":
            return []
        elif self.auto_update == "on_ingest":
            return ["paper_ingest"]
        elif self.auto_update == "on_entity_change":
            return ["entity_change", "paper_ingest"]
        elif self.auto_update == "always":
            return ["any"]
    
    def get_mode(self) -> str:
        """推导：更新模式"""
        return self.advanced.get("mode", "incremental")


class PaperBaseConfig(BaseModel):
    llm: LLMConfig = LLMConfig()
    graph: GraphConfig = GraphConfig()
    
    @classmethod
    def load(cls, path: Path) -> "PaperBaseConfig":
        """加载配置并验证"""
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        
        # 展开环境变量
        expand_env_vars(raw)
        
        # 使用 Pydantic 验证
        try:
            return cls.model_validate(raw)
        except ValidationError as e:
            # 提供友好的错误信息
            raise ConfigError(f"Invalid configuration: {e}") from e
```

---

## 错误提示改进

### 现状

```python
if not base_url or not model:
    logger.warning("LLM enabled but base_url or model missing, disabling")
    self.enabled = False
    return
```

**问题**: 用户不知道如何修复。

### 改进

```python
if not config.llm.provider:
    # 未配置，正常禁用
    self.enabled = False
    return

# 配置了 provider，但参数不全
try:
    config.llm.validate()
except ConfigError as e:
    logger.error(f"LLM configuration error: {e}")
    logger.info("To fix:")
    logger.info("  1. Edit config/paperbase.yaml")
    logger.info("  2. Set llm.provider to: openai / anthropic / ollama / custom")
    logger.info("  3. Set llm.model (e.g., gpt-4o-mini)")
    logger.info("  4. Set PAPERBASE_LLM_API_KEY environment variable")
    raise
```

---

## 迁移策略

### 向后兼容

```python
class LLMConfig(BaseModel):
    # 新字段
    provider: str | None = None
    
    # 旧字段（向后兼容）
    enabled: bool | None = None
    base_url: str | None = None
    
    @model_validator(mode="after")
    def migrate_old_config(self):
        """自动迁移旧配置"""
        
        # 旧配置: enabled + base_url + api_key + model
        if self.enabled is not None and self.provider is None:
            logger.warning("Old config format detected, auto-migrating")
            
            if self.enabled and self.base_url:
                # 根据 base_url 推导 provider
                if "openai.com" in self.base_url:
                    self.provider = "openai"
                elif "anthropic.com" in self.base_url:
                    self.provider = "anthropic"
                elif "localhost:11434" in self.base_url:
                    self.provider = "ollama"
                else:
                    self.provider = "custom"
                
                logger.info(f"Migrated: provider={self.provider}")
            elif not self.enabled:
                self.provider = None
        
        return self
```

---

## 总结

### 改进的核心思想

1. **配置分层**: 用户配置 → 系统推导 → 实现细节
2. **最小配置**: 只暴露关键决策点
3. **明确依赖**: 在代码中验证，而非文档
4. **友好错误**: 告诉用户如何修复

### 用户体验改进

**改进前**:
```yaml
llm:
  enabled: true  # 开了这个
  base_url: ${...}  # 忘记配这个 → 运行时报错
  api_key: ${...}
  model: ${...}
```

**改进后**:
```yaml
llm:
  provider: openai  # 只需配置 provider
  api_key: ${...}   # 系统自动推导 base_url
  model: gpt-4o-mini
```

### 实现成本

- 编写 ConfigValidator（~200 行）
- 更新配置加载逻辑（~100 行）
- 编写迁移逻辑（~50 行）
- 更新文档（~1 小时）

**总计**: ~1-2 天工作量

### 收益

- 用户配置错误率降低 80%
- 配置文件行数减少 50%
- 错误提示更友好
- 新用户上手更快
