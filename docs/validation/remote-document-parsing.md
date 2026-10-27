# 远程文档解析验证记录

状态：配置加载、受控 HTTP、真实 OXR 冒烟、完整相关回归和独立代码审查均已有证据。单页合成输入的 `visual.mode=auto` 审计已通过并采用；公开论文全文识别质量仍未验收。

## 配置与命令合同

- `tests/cli/test_remote_document_parsing_docs.py` 从统一说明读取完整 YAML，使用真实 `load_config()` 加载，并检查默认 `parser: local`、两项 profile、timeout 及 `config show` 密钥遮蔽。
- 同一测试以真实 CLI Help 确认 `ingest --pdf-parser [local|remote]` 存在。`tests/integration/test_remote_pdf_ingest.py` 用受控 HTTP 验证 OXR 生产适配器、本地覆盖不改配置、Canonical 元数据与图片，以及已解析在线 Markdown 不会重复上传。
- `tests/integration/test_remote_pdf_visual_resume.py` 用受控 HTTP 验证 auto 审计、always 视觉页块与 Boundary Review、密钥轮换复用、身份变化失效、Warning 重审、质量失败不转向后备 profile、`visual.mode=off` 门禁待审续作和成功采用清理缓存。
- Zotero PDF 入口代码接入了 `--pdf-parser`，但按用户要求没有运行 Zotero 端到端测试。

2026-10-27 在集成提交 `f1fd602` 上运行完整相关回归：`pytest -q --no-cov --tb=short -k 'not zotero'`，结果为 542 passed、10 skipped、31 deselected。Zotero 相关测试被明确排除；本次结果不声称所有测试通过。执行主机的完整输出另存于本机 Git 忽略目录 `.scratch/remote-document-parsing/evidence/full-regression.txt`，其他克隆不会包含该文件。

随后独立 Standards/Spec review 发现 OXR 采用结果的 converter 版本在 Canonical provenance 与 Manifest pipeline 中不一致，修复已合入 `42b080c`。修复后相关定向测试为 95 passed、1 skipped；没有因该小修复重复运行全量回归。

## 真实 API 冒烟

2026-10-27 共四个真实 OXR Free API 解析场景，均只配置 `https://free-oxr.somark.cn/api/v1`；未调用付费 API、未自动添加其他服务。

- **合成 PDF，`visual.mode=off`：** 一页输入经过 Canonical 门禁进入 `NORMALIZED`；候选保留公式、HTML 表格与本地化 PNG。此项证明合成路径可采用，不作为论文质量证据。
- **公开 PDF，`visual.mode=off`，旧缓存实现前：** [arXiv:2608.28698](https://arxiv.org/abs/2608.28698)（18 页、约 1.77 MB、CC BY 4.0）返回 63,894 字符候选与 13 个可解码图像，因 `references_unparseable` 进入 `NEEDS_REVIEW`。当时未保存候选正文，无法据那次运行抽查页面。
- **合成 PDF，`visual.mode=auto`：** OXR 候选生成自动审计任务包，Agent Host 将单页判为单栏且通过，CLI 写入 `NORMALIZED`，PNG 位于本地。用相同摄入命令续作时，`parseWithOxr` sentinel 与 `urlopen` 计数均为 0，没有第二次 HTTP 请求。该次运行基于修复前 `f1fd602`，Canonical frontmatter converter version 为 `1.0.0`，Manifest pipeline version 为 `unknown`；不把该旧产物说成由 `42b080c` 生成。后续离线定向测试验证修复后新产物两处均为 `unknown`，没有再次上传或改写旧产物。
- **同一公开 PDF，`visual.mode=off`，候选缓存实现后：** 再次为检查缓存后的候选保留而调用一次；这不是自动重试或顺延。输出仍因 APA/作者年份参考文献格式未满足编号门禁而进入 `NEEDS_REVIEW`。抽查 page_num 0–1 的双栏顺序、page_num 3 的公式、page_num 4 的表格、page_num 5 的图像资产，以及 page_num 8–9 的引用顺序。发现页 1–2 的 `ex-`/`pensive` 跨页断词未合并且插入了脚注/图内容，Pfitzmann 2022 参考文献跨栏拆成两段；Formula 2、Table 1 表头及抽查数值与原页一致，PNG 可本地打开。主代理独立复核了 Formula 2 与 Table 1 数值。

最后一次缓存调用保留了候选，但全文仍未成为 Canonical；这些代表页抽查不等于全文校对、准确率基准或质量通过。其他页及全部引用关系仍未完成逐项核对。

公开样本来源为 [arXiv:2608.28698](https://arxiv.org/abs/2608.28698)，其来源页许可链接为 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。OXR Free API 当前公开文档说明单文件最大 10 MB、每次最多 20 页，并提示请求排队且不保证稳定性，参见 [SoMark OXR Free API 文档](https://docs.somark.ai/api-reference/oxr/index#free-api) 和 [OXR 官方仓库](https://github.com/SoMarkAI/OXR)。免费 API 的边界不套用于 SoMark 商业服务或其他自建实例。

真实请求输入、隔离库、Manifest 与图片，以及单页 auto smoke 的任务和结果，保存在执行机器 Git 忽略的 `.scratch/remote-document-parsing/evidence/api-smoke/` 与 `.scratch/remote-document-parsing/evidence/real-visual-smoke/`。这些原始证据不会随仓库克隆，也没有把 PDF、论文正文、响应正文、图片或密钥加入本仓库；本记录仅留事实摘要。

## 尚待确认

- Zotero 远程摄入的端到端验证（用户明确暂缓）。
- 真实公开论文的全文结构和公式质量；此前未保存候选，不能由当前摘要补推。
- 更多代表性论文的视觉与内容质量评估；单页 auto smoke 不能代表全文或其他文档格式。
