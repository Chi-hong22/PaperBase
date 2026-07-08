# Prompt Design Rationale: Entity Extraction for Cross-Domain Papers

## 概述

本文档记录 PaperBase 实体抽取提示词的设计决策、理论基础和工程权衡。该提示词位于 `src/paperbase/core/llm_client.py` 的 `_build_extraction_prompt` 方法中。

**核心目标：** 从跨学科论文中自动提取高精度实体，用于知识图谱构建和跨论文关联查询。

**设计理念：** 可操作化规则（operationalizable criteria）+ 术语保真（terminology preservation）+ 高精度优先（precision over recall）。

---

## 1. 设计目标

### 1.1 区分"核心使用" vs "顺带提及"

**问题：** 论文中会大量提及实体，但只有部分是论文的核心贡献或工具。

**示例：**
- **核心使用**：论文提出新的 submap-based SLAM 方法，submap 出现在 Title/Abstract/Method。
- **顺带提及**：论文在 Related Work 中提及 ORB-SLAM2 作为对比基线。

**设计决策：** 基于**章节位置 + 作用类型**过滤：
- 提取出现在 Title/Abstract/Method/Experiment 的实体。
- 排除仅出现在 Related Work/Introduction 的对比性提及。

**理由：**
- **可操作化**：章节位置是客观规则，LLM 可遵循。
- **泛化性**：适用于所有学科（SLAM/NLP/CV 均遵循相似论文结构）。
- **精度优先**：避免将所有提及的方法都标记为"核心方法"，导致图谱噪声。

### 1.2 跨学科泛化

**问题：** PaperBase 需要处理不同领域的论文（SLAM、NLP、CV、生物信息等），实体类型差异大。

**设计决策：** 定义通用实体类别 + 领域无关规则：
- **methods**：算法、模型、技术（适用于任何学科）
- **datasets**：训练/测试数据集（适用于实验性论文）
- **domains**：应用领域（如 AUV navigation, sentiment analysis）
- **platforms**：运行平台（如 AUV, GPU, mobile device）
- **constraints**：核心约束（如 underwater, real-time, limited memory）

**理由：**
- 这五个类别是论文方法论的通用组成部分（问题 → 方法 → 平台 → 约束 → 数据集）。
- 避免为每个学科定义专有类别（如 "SLAM methods"、"NLP models"），减少维护成本。

### 1.3 保留原文术语

**问题：** 同一概念有多种写法（submap / sub-map / submapping），强制规范化会丢失论文原始用词习惯。

**设计决策：** 保留原文术语，延迟到后处理阶段做模糊匹配：
- LLM 提取时：原文写 "submap" 就提取 "submap"，写 "sub-map" 就提取 "sub-map"。
- 后处理阶段：通过 `terminology.yaml` 定义等价类（submap ≈ sub-map ≈ submapping），在查询时做模糊匹配。

**理由：**
- **信息保真**：不丢失论文原始用词（某些情况下 "submap" 和 "submapping" 可能有微妙区别）。
- **降低 LLM 负担**：不要求 LLM 学习所有术语的标准形式（LLM 无法穷举所有领域的术语规范）。
- **可审计性**：用户可以看到论文原文使用的术语，而非被 LLM "翻译"后的版本。

**权衡：** 需要额外维护 `terminology.yaml`，但收益远大于成本（一次性维护 vs 每次提取都规范化）。

### 1.4 高精度优先

**目标：** 75-80% 精度，允许较低召回率。

**理由：**
- **知识图谱质量**：低精度会导致图谱中充满无关边（如将所有 Related Work 中的方法都标记为"使用"）。
- **人工成本**：修正误报（false positive）比补充漏报（false negative）成本更高（需要检查上下文判断是否误报）。
- **查询体验**：用户查询 "使用 BERT 的论文" 时，期望返回**真正使用** BERT 的论文，而非仅在 Related Work 中提及的论文。

**实现方式：**
- 严格章节规则（排除 Related Work）。
- Few-shot examples 强调反例（如 "ORB-SLAM2 仅在 Related Work → 不提取"）。

---

## 2. 关键设计决策

### 2.1 为什么使用可操作化规则（Operationalizable Criteria）

**可操作化规则 = 客观、可验证、可遵循的判断标准。**

**对比：**
- **不可操作**："提取重要的方法"（"重要"主观且模糊）
- **可操作**："提取出现在 Title/Abstract/Method/Experiment 的方法"（客观可验证）

**优势：**
1. **LLM 一致性**：减少 LLM 的随机性（不同 run 的结果更稳定）。
2. **可调试性**：如果提取错误，可以明确定位是哪条规则失效。
3. **可扩展性**：新增规则时可以单独测试（如增加 "排除 Limitation 中的提及"）。

**参考：** Codex feedback 中强调 "operationalizable criteria" 是提高 LLM 任务一致性的关键。

### 2.2 为什么保留原文术语（Terminology Preservation）

**替代方案：** LLM 提取时直接规范化（如将 "sub-map" 统一为 "submap"）。

**拒绝理由：**
1. **LLM 知识局限**：LLM 无法穷举所有领域的术语规范（如 SLAM 中的 "loop closure" vs "loop closing"）。
2. **语义损失风险**：某些情况下变体有微妙差异（如 "submapping" 强调过程，"submap" 强调数据结构）。
3. **跨学科一致性**：不同学科的术语规范不同，LLM 难以适配（如 NLP 中 "fine-tuning" vs CV 中 "transfer learning"）。

**当前方案优势：**
- 保留论文原始信息，延迟决策到后处理阶段。
- 后处理阶段通过 `terminology.yaml` 做领域专家审核的术语映射。

### 2.3 为什么使用 Few-Shot Examples

**替代方案：** 仅提供规则定义（zero-shot）。

**Few-shot 优势：**
1. **降低歧义**：规则定义可能有多种解释，examples 提供具体参考。
2. **强化反例**：examples 明确展示"不应该提取"的情况（如 Related Work 中的提及）。
3. **跨域泛化**：提供不同领域的 examples（SLAM/NLP/CV），帮助 LLM 理解规则的通用性。

**Example 设计原则：**
- **多样性**：覆盖不同学科（SLAM/NLP/CV）。
- **对比性**：每个 example 包含"应该提取"和"不应该提取"的案例。
- **解释性**：附带 `**解释**` 说明为什么这样提取。

### 2.4 为什么选择 Precision vs Recall 权衡

**当前目标：** 75-80% 精度，允许 50-60% 召回率。

**理由：**
1. **知识图谱应用场景**：查询"使用 X 的论文"时，用户期望高精度结果。
2. **人工修正成本**：误报需要人工审查上下文，漏报可以通过手动补充（或后续优化）。
3. **渐进式改进**：初期高精度 → 稳定后逐步提高召回率（而非初期低精度 → 清理噪声）。

**未来优化方向：**
- 专家反馈循环：记录用户修正 → 生成新的 few-shot examples。
- 领域自适应：为高频领域（如 SLAM）提供专用 examples。

---

## 3. Prompt 结构

### 3.1 实体类别定义

**设计：** 为每个类别提供"判断标准"而非"定义"。

**示例（methods）：**
```
1. **methods**（核心技术方法）
   - 论文主要使用/提出/改进的算法、模型、技术
   - 判断标准：出现在 Title/Abstract/Method/Experiment，且是论文的核心贡献或主要工具
   - 排除：仅在 Related Work/Introduction 中对比提及的方法
```

**关键要素：**
- **判断标准**：可操作化的检查规则（章节位置 + 作用类型）。
- **排除规则**：明确反例（避免 LLM 过度提取）。

### 3.2 术语处理规则

**三层规则：**
1. **保留原文术语**：不强制统一变体（submap / sub-map / submapping 都保留）。
2. **基础规范化**：仅处理明确约定（缩写全大写、专有名词保留原文）。
3. **不要编造标准化形式**：明确禁止 LLM "创造性"规范化。

**设计理由：**
- 第 1 层：保证信息保真。
- 第 2 层：处理常识性规范（SLAM vs slam 不是术语变体，是拼写错误）。
-第 3 层：防止 LLM 过度主动（LLM 倾向于"帮助"用户规范化，但可能引入错误）。

### 3.3 Few-Shot Examples

**当前覆盖：**
- **Example 1（SLAM）**：AUV underwater navigation, submap-based SLAM
- **Example 2（NLP）**：BERT fine-tuning, sentiment analysis
- **Example 3（CV）**：YOLOv5, real-time object detection on mobile

**设计原则：**
- 每个 example 包含**正例**和**反例**（如 ORB-SLAM2 不提取，BERT 提取）。
- 每个 example 附带**解释**（说明为什么这样判断）。
- 覆盖不同实体类别（methods/datasets/domains/platforms/constraints）。

### 3.4 输出要求

**关键约束：**
1. 严格 JSON 格式（支持 OpenAI `response_format={"type": "json_object"}`）。
2. 只提取核心使用，不提取顺带提及。
3. 无法确定时返回空列表 `[]`（而非猜测）。
4. 不要编造不存在的实体（避免 hallucination）。
5. 不要重复提取（去重）。

**设计理由：**
- 第 1 条：保证输出可解析（避免 LLM 返回自然语言）。
- 第 2-4 条：强化高精度目标（宁缺毋滥）。
- 第 5 条：减少后处理负担。

---

## 4. 已知局限性

### 4.1 高度专业化领域

**问题：** 某些领域的术语高度专业化（如量子计算、蛋白质折叠），当前 prompt 可能无法准确识别实体类型。

**示例：**
- 量子计算论文中的 "qubit coherence time" 是 constraint 还是 metric？
- 蛋白质折叠论文中的 "AlphaFold" 是 method 还是 platform？

**缓解措施：**
- 未来支持领域自适应 prompt（为特定领域提供专用 examples）。
- 用户可以通过手动标注修正（并反馈到 terminology.yaml）。

### 4.2 新兴跨学科领域

**问题：** 新兴跨学科领域（如 neuro-symbolic AI）可能使用非传统术语，当前 prompt 难以覆盖。

**示例：**
- "differentiable logic programming" 是 method 还是 paradigm？

**缓解措施：**
- 定期更新 few-shot examples（基于用户反馈和新论文）。
- 支持自定义实体类别（未来扩展）。

### 4.3 LLM 训练数据截止日期

**问题：** LLM 的训练数据有截止日期（如 GPT-4 的 2023 年 4 月），对于 2024 年后的新术语可能不熟悉。

**示例：**
- 2025 年出现的新方法 "XYZ" 可能被误分类。

**缓解措施：**
- 依赖 prompt 中的规则（而非 LLM 的先验知识）。
- 使用最新的 LLM（如 GPT-4 Turbo 或本地更新的模型）。

### 4.4 摘要截断问题

**问题：** 当前 prompt 使用论文前 4000 字符（约 1000 tokens），可能截断 Method 章节。

**影响：**
- 如果核心方法在 Method 后半部分，可能漏提取。

**缓解措施：**
- 优先提取 Title + Abstract（通常包含核心信息）。
- 未来支持多段提取（分别提取 Abstract 和 Method，再合并）。

---

## 5. 未来改进方向

### 5.1 领域自适应 Prompt

**目标：** 为高频领域（如 SLAM、NLP、CV）提供专用 few-shot examples。

**实现方式：**
1. 检测论文领域（通过 Title/Abstract 关键词）。
2. 动态选择对应领域的 examples（如 SLAM 论文使用 SLAM examples）。
3. Fallback 到通用 prompt（如果领域无法识别）。

**预期收益：**
- 提高领域内实体识别精度（如 SLAM 论文中的 "loop closure" 更准确分类为 method）。

### 5.2 专家反馈循环

**目标：** 基于用户修正（manual correction）生成新的 few-shot examples。

**实现流程：**
1. 用户修正 LLM 提取的实体（通过 CLI 或 UI）。
2. 系统记录修正前后的差异（作为负样本）。
3. 定期分析修正模式，生成新的 few-shot examples。
4. A/B 测试新 prompt 的效果。

**预期收益：**
- 持续优化 prompt（而非一次性设计）。
- 适配项目特定的论文风格（如某实验室的论文写作习惯）。

### 5.3 基于嵌入的术语相似度匹配

**目标：** 在查询阶段使用 embedding 做模糊匹配（而非精确字符串匹配）。

**实现方式：**
1. 为所有提取的实体生成 embedding（通过 LLM 或专用模型）。
2. 查询时计算 embedding 相似度（如 "submap" 和 "sub-map" 的 cosine similarity > 0.9）。
3. 返回相似度高于阈值的所有论文。

**预期收益：**
- 无需手动维护 `terminology.yaml`（自动发现术语变体）。
- 支持跨语言查询（如查询 "SLAM" 也能匹配中文论文中的"即时定位与地图构建"）。

**挑战：**
- 需要高质量 embedding 模型（领域通用 or 领域专用）。
- 相似度阈值需要实验调优（避免误匹配）。

### 5.4 多段式提取

**目标：** 分别提取 Title + Abstract + Method，避免 4000 字符截断问题。

**实现方式：**
1. 分段提取：Title + Abstract → 提取 domains/constraints。
2. Method 章节 → 提取 methods。
3. Experiment 章节 → 提取 datasets/platforms。
4. 合并去重。

**预期收益：**
- 提高长论文的召回率（不受字符限制影响）。

**挑战：**
- 需要准确的章节识别（Markdown heading 可能不规范）。
- 增加 LLM 调用次数（成本上升）。

---

## 6. 设计权衡总结

| 设计选择 | 优势 | 劣势 | 当前判断 |
|---------|------|------|---------|
| **可操作化规则** | 一致性高、可调试、可扩展 | 可能过于刚性（边缘案例难处理） | ✅ 优先采用（初期稳定性重要） |
| **保留原文术语** | 信息保真、降低 LLM 负担 | 需要维护 terminology.yaml | ✅ 优先采用（收益 > 成本） |
| **高精度优先** | 知识图谱质量高、用户体验好 | 召回率较低（可能漏提取） | ✅ 优先采用（渐进式改进） |
| **Few-shot examples** | 降低歧义、强化反例 | Prompt 长度增加（token 成本） | ✅ 优先采用（3 examples 是平衡点） |
| **通用类别** | 跨学科泛化 | 高度专业化领域可能不足 | ✅ 优先采用（未来支持领域自适应） |

---

## 7. 参考资料

- **Codex Feedback**：强调 "operationalizable criteria" 和 "preserve terminology"
- **OpenAI Best Practices**：Few-shot prompting for structured output
- **Knowledge Graph Literature**：高精度优先于高召回率（Precision-First Entity Extraction）
- **PaperBase AGENTS.md**：Terminology library and fuzzy matching strategy

---

## 变更日志

- **v1.0 (2026-07-07)**：初始版本，基于 Task 0-5 的实现经验总结。
