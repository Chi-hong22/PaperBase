# PaperBase Domain

PaperBase 将论文来源转化为可验证的 Canonical Markdown，并从该真相源构建可重建的检索与知识图谱投影。

## Language

**Canonical Markdown（规范论文正文）**:
一篇论文在 PaperBase 中唯一受信任的内容真相源；只有通过转换质量门的内容才能成为 Canonical Markdown。
_Avoid_: 转换结果、原始 Markdown、草稿

**Conversion Candidate（转换候选稿）**:
确定性转换器从论文来源产生、尚未通过转换质量门的候选内容；它不是内容真相源。
_Avoid_: Canonical、最终 Markdown

**Visual Repair（视觉校正）**:
依据论文页面视觉证据，对转换候选稿中的阅读顺序、结构或内容损失进行受控纠正。
_Avoid_: 视觉转换引擎、视觉润色、自由重写

**Visual PDF Conversion（视觉 PDF 转换）**:
由常规摄入流程按配置选择的 PDF 转换方法，在内容成为 Canonical Markdown 前包含视觉校正。
_Avoid_: 独立视觉工作流、单独 CLI 入口、模型 API 调用

**Conversion Quality Gate（转换质量门）**:
决定转换候选稿能否成为 Canonical Markdown，或是否需要视觉校正的判定边界。
_Avoid_: 图谱预检、格式检查

**Agent Host（Agent 宿主）**:
提供 subagent 调度、模型选择和视觉输入能力的外部 Agent 系统；PaperBase 不绑定某个具体宿主。
_Avoid_: OpenAI API、PaperBase LLM

**Visual Worker（视觉校正 Worker）**:
由 Agent 宿主调度、负责处理指定论文页面和转换候选稿的 subagent 角色。
_Avoid_: PDF 转换器、Canonical 写入者

**Visual Task Package（视觉任务包）**:
PaperBase 为视觉校正准备的、可由不同 Agent 宿主读取的自包含任务描述及输入集合。
_Avoid_: Prompt、API 请求、宿主专用任务

**Visual Repair Run（视觉校正运行）**:
围绕同一论文来源和转换候选稿开展的一次可恢复处理生命周期；失败重试属于原运行的后续尝试，而不是新的运行。
_Avoid_: 单次模型调用、临时目录、重跑副本

**Run Lease（运行占用）**:
某个 Agent 宿主在有限时间内继续一次视觉校正运行的排他资格；过期占用可以由后续恢复操作接管。
_Avoid_: 永久锁、文件所有权

**Visual Chunk（视觉页块）**:
一次视觉校正运行中由单个 Visual Worker 独占处理的连续核心页面集合；相邻页面只能作为只读上下文。
_Avoid_: 文档分块、检索 Chunk、重叠写入范围

**Boundary Review（边界复核）**:
在转换候选稿成为 Canonical Markdown 前，对页块接缝、风险页面和整体覆盖进行的独立视觉检查。
_Avoid_: 全文重写、Graph preflight、抽样即通过

**Re-review（重审）**:
作废一次已完成的 Boundary Review、对当前 Visual Chunk 输出重新进行边界复核的受控状态回退；失败重试与返工重审都属于原 Visual Repair Run 生命周期。
_Avoid_: 手工改 run.json、重跑摄入、重新分块

**Visual Fallback Asset（视觉保真资产）**:
当公式或复杂表格无法可靠转成机器可读文本时，用于忠实保留原页面内容的局部视觉资产。
_Avoid_: OCR 结果、猜测性 LaTeX、普通插图

**Page Coverage（页面覆盖）**:
一次视觉校正运行对源 PDF 每一页的处理、排除或空白判定是否完整且无重复。
_Avoid_: 文本长度、抽样页数、页级哈希集合

**Scan Root（扫描根）**:
Graphify 计算来源文件身份与语义缓存键的基准目录；同一论文库的所有 Agent 与 headless 调用统一以本机 `library/papers` 为扫描根，调用侧先切换工作目录，且不以绝对路径持久化。
_Avoid_: 仓库根扫描、把 `library/papers` 当路径参数、绝对路径持久化
