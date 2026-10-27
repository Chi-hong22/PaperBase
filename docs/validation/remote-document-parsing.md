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

2026-10-27 以明确允许外传的输入对官方 OXR 免费 API 发出两次请求，配置只选 `https://free-oxr.somark.cn/api/v1`，没有调用付费 API 或自动添加后备地址。

- 合成一页 PDF 成功经过当前 Canonical 门禁，状态为 `NORMALIZED`；观察到公式文本、HTML 表格及本地化 PNG 图片。该样例只能证明当前候选路径可运行，不能作为一般论文准确率证据。
- 一份 arXiv 公开 CC BY 4.0 论文 PDF（18 页，约 1.77 MB）得到 63,894 字符候选稿和 13 个可本地解码图片，但在现有 APA/作者年份参考文献格式门禁 `references_unparseable` 进入 `NEEDS_REVIEW`。CLI 退出码 0 不表示 Canonical 已采用。
- 未保存未采用的论文 Markdown 候选正文，所以没有做全文逐页的阅读顺序、公式、表格、引用或参考文献对照；不报告准确率或质量通过。RDP-003 的候选缓存与离线续作验证也没有补做这次公开论文的全文质量验证。
- 此外在 `f1fd602` 上用单页合成 PDF 完成一次真实 `visual.mode=auto` OXR 冒烟：上传后生成候选和自动审计任务包；Agent Host 对该页判定为单栏且通过，CLI 随后写入 `NORMALIZED`，本地 PNG 存在，缓存已清理。同一摄入命令续作时 `parseWithOxr` sentinel 与 `urlopen` 计数均为 0。该运行使用 provenance 修复前代码，Canonical frontmatter converter version 为 `1.0.0`、Manifest pipeline version 为 `unknown`；不将该旧产物说成由 `42b080c` 生成。该提交后的离线定向测试验证新采用结果两处均为 `unknown`，没有再次上传或改写这次旧产物。

公开样本来源为 [arXiv:2608.28698](https://arxiv.org/abs/2608.28698)，其来源页许可链接为 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。OXR Free API 当前公开文档说明单文件最大 10 MB、每次最多 20 页，并提示请求排队且不保证稳定性，参见 [SoMark OXR Free API 文档](https://docs.somark.ai/api-reference/oxr/index#free-api) 和 [OXR 官方仓库](https://github.com/SoMarkAI/OXR)。免费 API 的边界不套用于 SoMark 商业服务或其他自建实例。

真实请求输入、隔离库、Manifest 与图片，以及单页 auto smoke 的任务和结果，保存在执行机器 Git 忽略的 `.scratch/remote-document-parsing/evidence/api-smoke/` 与 `.scratch/remote-document-parsing/evidence/real-visual-smoke/`。这些原始证据不会随仓库克隆，也没有把 PDF、论文正文、响应正文、图片或密钥加入本仓库；本记录仅留事实摘要。

## 尚待确认

- Zotero 远程摄入的端到端验证（用户明确暂缓）。
- 真实公开论文的全文结构和公式质量；此前未保存候选，不能由当前摘要补推。
- 更多代表性论文的视觉与内容质量评估；单页 auto smoke 不能代表全文或其他文档格式。
