"""LLM 客户端（支持任何 OpenAI-compatible API，完全可选）"""

import os
from pathlib import Path
import yaml
from typing import Any
import logging

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 客户端（内部使用，可选）"""

    def __init__(self, config: dict | None = None, config_path: Path | None = None):
        """
        初始化 LLM 客户端

        Args:
            config: 配置字典（优先）
            config_path: 配置文件路径（fallback）
        """
        if config is None:
            config = self._load_config(config_path)
        else:
            # 展开传入的 config 中的环境变量
            self._expand_env_vars(config)

        self.config = config
        self.enabled = config.get("llm", {}).get("enabled", False)
        self.client = None
        self.model = None

        if self.enabled:
            self._init_client()

    def _load_config(self, config_path: Path | None) -> dict:
        """加载配置文件"""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "paperbase.yaml"

        if not config_path.exists():
            return {"llm": {"enabled": False}}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")
            return {"llm": {"enabled": False}}

        # 展开环境变量
        self._expand_env_vars(config)

        return config

    def _expand_env_vars(self, config: dict):
        """展开环境变量 ${VAR}"""
        if "llm" not in config:
            return

        llm_config = config["llm"]
        for key in ["base_url", "api_key", "model"]:
            if key in llm_config and isinstance(llm_config[key], str):
                value = llm_config[key]
                if value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    llm_config[key] = os.getenv(env_var, "")

    def _init_client(self):
        """初始化 OpenAI-compatible 客户端"""
        llm_config = self.config.get("llm", {})
        base_url = llm_config.get("base_url", "")
        api_key = llm_config.get("api_key", "")
        model = llm_config.get("model", "")

        if not base_url or not model:
            logger.warning("LLM enabled but base_url or model missing, disabling")
            self.enabled = False
            return

        # api_key 可选（本地 LLM 可能不需要）
        if not api_key or api_key == "not-required":
            api_key = "not-required"  # OpenAI SDK 需要非空字符串

        try:
            import openai
            self.client = openai.OpenAI(
                base_url=base_url,
                api_key=api_key
            )
            self.model = model
            logger.info(f"LLM client initialized: {base_url} / {model}")

        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            self.enabled = False

    def extract_entities(self, paper_content: str) -> dict[str, Any] | None:
        """
        从论文内容提取实体

        Args:
            paper_content: 论文内容（paper.md 全文或摘要）

        Returns:
            {"methods": [...], "datasets": [...], ...} 或 None（未启用/失败）
        """
        if not self.enabled:
            return None

        # 限制内容长度
        max_length = self.config.get("llm", {}).get("max_content_length", 4000)
        content = paper_content[:max_length]

        prompt = self._build_extraction_prompt(content)

        try:
            timeout = self.config.get("llm", {}).get("extract_timeout", 30)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=timeout
            )

            import json
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
            return None

    def _build_extraction_prompt(self, content: str) -> str:
        """
        构建实体提取 prompt（生产级，v1.0）

        设计原则：
        - 区分"核心使用"vs"顺带提及"（基于章节位置 + 作用类型）
        - 跨学科泛化（通过通用规则 + 少样本示例）
        - 保留原文术语（后处理阶段通过 terminology.yaml 做模糊匹配）
        """
        return f"""你是论文实体提取专家。从以下论文内容中提取**核心使用**的实体，忽略**顺带提及**的内容。

---
## 实体类别定义

1. **methods**（核心技术方法）
   - 论文主要使用/提出/改进的算法、模型、技术
   - 判断标准：出现在 Title/Abstract/Method/Experiment，且是论文的核心贡献或主要工具
   - 排除：仅在 Related Work/Introduction 中对比提及的方法

2. **datasets**（使用的数据集）
   - 论文用于训练、验证、测试的数据集
   - 判断标准：出现在 Experiment/Evaluation，且有实验结果
   - 排除：仅在 Related Work 中提及的数据集

3. **domains**（应用领域）
   - 论文解决的具体问题领域
   - 判断标准：Title/Abstract 中明确声明，或 Experiment 中的真实应用场景
   - 示例：AUV navigation, sentiment analysis, object detection, protein folding

4. **platforms**（运行平台）
   - 论文实现/部署的硬件或软件平台
   - 判断标准：Experiment 中实际使用，或 Method 中明确要求
   - 示例：AUV, drone, GPU cluster, mobile device

5. **constraints**（关键约束）
   - 论文需要应对的核心约束条件
   - 判断标准：Abstract/Method 中明确强调，且影响方法设计
   - 示例：underwater low visibility, real-time requirement, memory limitation

---
## 术语处理规则

1. **保留原文术语**：尽量保持论文中的原始写法
   - 如果论文写 "submap"，就提取 "submap"
   - 如果论文写 "sub-map"，就提取 "sub-map"
   - 不要强制统一变体（submapping/sub-map/submap 都保留）

2. **基础规范化**（仅以下两种情况）：
   - 缩写全大写：SLAM, CNN, BERT, GPU（而非 slam, cnn, bert）
   - 专有名词保留原文大小写：Transformer, ImageNet, PyTorch

3. **不要编造标准化形式**：
   - 不要将 "submapping" 改成 "sub-map"
   - 不要将 "local map" 改成 "submap"
   - 术语变体合并由后处理阶段的 terminology.yaml 负责

---
## Few-Shot Examples

### Example 1: AUV SLAM 论文
**Input（摘要片段）:**
"We propose a submap-based SLAM system for AUVs operating in underwater environments. Our method uses a Particle Filter for localization and is evaluated on the AQUALOC dataset. We compare with ORB-SLAM2 in the related work section."

**Output:**
```json
{{
  "methods": [
    {{"name": "submap", "type": "mapping"}},
    {{"name": "Particle Filter", "type": "localization"}}
  ],
  "datasets": [
    {{"name": "AQUALOC"}}
  ],
  "domains": [
    {{"name": "AUV navigation"}},
    {{"name": "underwater SLAM"}}
  ],
  "platforms": [
    {{"name": "AUV"}}
  ],
  "constraints": [
    {{"name": "underwater environment"}}
  ]
}}
```
**解释**：
- ORB-SLAM2 仅在 Related Work 中提及 → 不提取
- submap 和 Particle Filter 是核心方法 → 提取
- AQUALOC 用于实验 → 提取
- 保留原文 "submap"（不改成 "sub-map"）

### Example 2: NLP 情感分析论文
**Input（摘要片段）:**
"We fine-tune BERT for sentiment analysis on the IMDB dataset, achieving 94% accuracy. Our method outperforms previous works using LSTM and GRU. The model runs on a single GPU."

**Output:**
```json
{{
  "methods": [
    {{"name": "BERT", "type": "model"}},
    {{"name": "fine-tuning", "type": "training"}}
  ],
  "datasets": [
    {{"name": "IMDB"}}
  ],
  "domains": [
    {{"name": "sentiment analysis"}}
  ],
  "platforms": [
    {{"name": "GPU"}}
  ],
  "constraints": []
}}
```
**解释**：
- LSTM 和 GRU 仅用于对比 → 不提取
- BERT 是核心模型 → 提取
- GPU 是运行平台 → 提取
- 无明确约束 → constraints 为空

### Example 3: CV 目标检测论文
**Input（摘要片段）:**
"We propose a real-time object detection system using YOLOv5 on COCO dataset. The system is designed for mobile devices with limited memory. We mention Faster R-CNN in the introduction."

**Output:**
```json
{{
  "methods": [
    {{"name": "YOLOv5", "type": "detection"}}
  ],
  "datasets": [
    {{"name": "COCO"}}
  ],
  "domains": [
    {{"name": "object detection"}}
  ],
  "platforms": [
    {{"name": "mobile device"}}
  ],
  "constraints": [
    {{"name": "real-time requirement"}},
    {{"name": "limited memory"}}
  ]
}}
```
**解释**：
- Faster R-CNN 仅在 Introduction 中提及 → 不提取
- real-time 和 limited memory 是设计约束 → 提取

---
## 论文内容

{content}

---
## 输出要求

1. 严格返回 JSON 格式（如上述 examples）
2. 只提取**核心使用**的实体，不要提取**顺带提及**
3. 如果某类别无法确定，返回空列表 `[]`
4. 保留原文术语，不要过度规范化
5. 不要编造不存在的实体
6. 不要重复提取相同实体（如 "BERT" 出现多次，只提取一次）

请输出 JSON：
"""
