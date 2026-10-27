# 远程文档解析

状态：OXR 远程 PDF 转换及候选续作已实现。端到端配置与行为按下文合同工作；真实调用和论文质量证据分开记录，全文准确性尚未验收。架构选择见 [ADR-0004](adr/0004-remote-document-parsing-providers.md)。

## 选择解析方式

PaperBase 默认在本地转换 PDF。仅在配置中把 `conversion.pdf.parser` 设为 `remote`，或在一次摄入中显式加 `--pdf-parser remote`，才会将 PDF 上传给远程服务。服务配置列表本身不会启用上传。命令行覆盖只影响当前调用，不修改配置文件。

```bash
# 使用本地转换，即使配置默认方式为 remote
uv run paperbase ingest --file paper.pdf --pdf-parser local

# 显式上传 PDF 给配置中的 OXR 链
uv run paperbase ingest --file paper.pdf --pdf-parser remote
```

选择远程时，PaperBase 会把整份源 PDF 依次发送给所配置的服务端点，直到得到技术上可用的候选稿。鉴权、网络、服务和结果错误会按规则顺延；如果前项失败，后项也会收到同一份 PDF。远程解析不需要在运行 PaperBase 的电脑上部署 OXR GPU，但需要连接所选服务。自建 OXR 的硬件要求由其部署方式决定，见 [OXR 官方仓库](https://github.com/SoMarkAI/OXR)。

本地 PDF 和 Zotero PDF 附件进入相同转换入口；Zotero 代码已接入该选择，但本次未执行 Zotero 端到端测试。在线抓取已经返回 Markdown 时沿用原流程，不会因 `--pdf-parser remote` 而上传另一个 PDF。

## 配置

配置文件为 PaperBase 库目录中的 `config/paperbase.yaml`。下面是一个完整可加载的示例，含两个自建 OXR profile。它保留 `parser: local`，所以仅复制配置不会上传文件；如果改用远程，链按 profile 列表顺序执行。

<!-- remote-config-example:start -->
```yaml
conversion:
  pdf:
    parser: local
    remote:
      providers:
        - name: oxr-primary
          provider: oxr
          base_url: http://localhost:8000/v1
          api_key: ${OXR_API_KEY}
          timeout: 300
        - name: oxr-secondary
          provider: oxr
          base_url: http://localhost:8001/v1
          api_key: ${OXR_FALLBACK_API_KEY}
          timeout: 300
    visual:
      mode: auto
      model: your-existing-visual-model
```
<!-- remote-config-example:end -->

每项 profile 需要唯一 `name`、当前支持的 `provider: oxr`、OXR 兼容 `base_url`、`api_key` 和正数 `timeout`（秒）。多个 profile 可以指向同一服务但使用不同名称或凭据。密钥可使用 `${VARIABLE}` 或 `$VARIABLE` 引用环境变量；不要把真实密钥写入共享配置。配置加载后 `paperbase config show` 会遮蔽 profile 的密钥。

在启动 PaperBase 的同一终端设置示例变量，例如 PowerShell `$env:OXR_API_KEY = '...'` 和 `$env:OXR_FALLBACK_API_KEY = '...'`。如果远程方式已选而引用变量缺失，整条配置链会在请求前报错。

官方免费服务作为手动示例，不自动添加到 profile 链：

| 服务 | `base_url` | `api_key` |
|---|---|---|
| OXR 免费 API（中国镜像） | `https://free-oxr.somark.cn/api/v1` | `dummy` |
| OXR 免费 API（全球） | `https://free-oxr.somark.ai/api/v1` | `dummy` |

这两个地址是 SoMark 官方列出的 OXR Free API；`.cn` 是 `.ai` 的镜像。使用免费服务前，请把选定地址和 `dummy` 明确写入 profile，并再次确认上传范围。不要把两个镜像当作自动默认或稳定性保证。

## 请求与顺延

OXR 适配器使用同步 `POST {base_url}/parse/sync`，通过 multipart 上传 `file`、`api_key`，并请求 `markdown` 与 `json` 两种输出。OXR 返回的 Markdown 正文作为转换候选稿；可获得的页级 JSON 会保留在转换结果中。服务结果中的图片 URL 或 Base64 会物化到本地 `assets/`，正文改为 `./assets/...` 相对引用。服务返回本机绝对图片路径时，图片无法物化，该 profile 视为不可用。

选择远程后，PaperBase 在发出首个请求前校验整个配置链。空链、名称重复、未知 provider、非法地址、无效超时及缺失密钥环境变量均报告 `remote_config_invalid`，不会上传，也不会让有效前项掩盖无效后项。未选择远程时不校验远程凭据、不探测端点。

通过本地校验后，各 profile 依次尝试。HTTP 408、429、5xx、网络错误和超时属于可顺延的暂时服务故障；鉴权或额度拒绝、解析错误、空正文、坏响应及图片物化失败也会顺延。PaperBase 不在同一 profile 上叠加自动重试。HTTP 2xx 本身不代表结果可用。首个非空且图片可本地物化的候选稿会停止顺延；随后视觉审查或 Canonical 门禁不通过时保留待审，不继续调用后项。全链失败不会自动切回本地。当前主要错误分类为 `remote_config_invalid`、`remote_transient_failure` 和 `remote_all_profiles_failed`；本机无法保存视觉续作候选时返回 `remote_candidate_cache_failed`，不会切换服务。错误原因会提到 profile 名称，但不会输出密钥、正文或原始响应。

## 视觉审查、续作与采用

`visual.mode` 控制候选稿产生后的视觉流程，与 `parser` 和 `visual.model` 分属不同设置：

| 模式 | 处理 |
|---|---|
| `off` | 不启动 Agent 视觉审查；仍执行 Canonical 采用门禁 |
| `auto` | 先准备自动审计；审计结果要求时再进入现有视觉转换 |
| `always` | 进入现有视觉转换及 Boundary Review |

只要 `visual.mode` 不是 `off`，就必须配置有效的 `visual.model`。PaperBase 会在上传 PDF 前报告缺失项。远程解析成功不代表全文质量通过，也不跳过页覆盖、视觉 Warning 确认或其他 Canonical 采用门禁。

本地 `parser` 只说明不向 OXR 上传。若用户要求所有数据留在本机，`visual.mode: auto` 或 `always` 仍会让所选 Agent Host 读取源 PDF 页面图像和转换候选稿；先核实该宿主的数据处理范围，再决定是否启用视觉流程。

候选稿在视觉任务、Warning 确认、重审和 Canonical 门禁待审期间暂存，以便重复执行原摄入命令时复用而不再次上传，包括 `visual.mode: off` 的后续采用门禁重试。身份由源 PDF 内容、解析方式及按顺序排列的非密钥 profile 字段决定，并保存实际选中的 profile；仅轮换同名 profile 的密钥不会触发重新解析，改变源文件、profile 顺序、地址或超时则会使用新候选稿。缓存只保留续作所需的 Markdown、页数据、相对图片路径、服务版本和 profile 来源，不含密钥或完整 HTTP 响应。成功采用后移除缓存元数据；正文引用的图片继续留在论文 `assets/` 中。视觉页块与 Boundary Review 仍由现有 Visual Repair Run、Run Lease 和 `--re-review` 规则推进。

Canonical 与 Registry 仍只由摄入流程写入。成功采用后的 `manifest.pipeline.converter` 记录 `oxr:<profile-name>`，版本未知时写为 `unknown`。未通过采用门禁时，不能把 Manifest 中保留的旧转换器字段当成当前 OXR 运行的来源记录。

## OXR 免费服务限制

截至 2026-10-27，[SoMark 官方 OXR Free API 文档](https://docs.somark.ai/api-reference/oxr/index#free-api)说明免费服务单文件最大 10 MB、单次最多 20 页；它不要求注册或申请真实 API key，示例使用 `dummy`。官方也说明请求会排队、不保证服务稳定，并不建议用于生产。这里的限制只适用于其 Free API；本文不把商业 SoMark API 的额度套用到免费服务，也不承诺 OXR 识别准确率、速度或可用性。

## 验证证据

当前有三层证据，不能相互替代：

1. 离线合同测试使用可控 HTTP 调用真实 OXR 适配器，覆盖配置、顺延、图片物化、视觉续作、缓存失效及 Canonical 门禁；这些测试不证明公网服务可用。
2. 2026-10-27 的两次 OXR Free API 调用分别使用合成 PDF 和一份公开 CC BY 论文。合成样例进入 `NORMALIZED`；公开论文返回 63,894 字符候选稿及 13 个可解码图片资产，但停在 `references_unparseable` 并进入 `NEEDS_REVIEW`。
3. 公开论文候选正文未被 PaperBase 持久化；本次没有逐页验证它的阅读顺序、公式、表格或参考文献完整性。因此没有全文准确率、阅读顺序或质量通过结论。离线续作验证也不等于再次端到端核对该公开论文。

真实调用记录留在执行者本机被 Git 忽略的 `.scratch/remote-document-parsing/evidence/api-smoke/real-api-smoke.md`，克隆仓库不会包含该文件。本仓库跟踪的摘要与边界见[远程解析验证记录](validation/remote-document-parsing.md)。

## 文档合同与扩展边界

本页集中维护配置、上传、顺延、结果和缓存合同。安装指南与中英文 README 只提供选择提示并链接回本页；命令以当前 `paperbase ingest --help` 为准。第一版只支持 OXR 及兼容其协议的自建地址，不实现自动发现、付费地址默认启用、本机 OXR 部署管理或通用插件平台。新增服务时复用同一候选稿、错误、profile 链和摄入采用规则。
