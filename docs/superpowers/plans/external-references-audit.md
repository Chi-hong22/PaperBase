# PaperBase Skill 外部引用清单

## 发现的引用

1. **troubleshooting-integration.md:262**
   - 引用: `[../installation.md](../../installation.md)`
   - 目标: `docs/installation.md`
   - 内容: paper-fetch 和 graphify 安装指南
   - 是否内化: 是（核心依赖安装说明）
   - 处理方式: 提取 paper-fetch 和 graphify 安装核心部分，内化到 references/installation.md（精简版，约 100-120 行）

## 内化决策矩阵

| 引用目标 | 核心功能依赖 | 内容体积 | 内化方式 |
|---------|-------------|---------|---------|
| docs/installation.md | 是 | 中等 | 提取关键安装部分，故障排查保留在 troubleshooting-integration.md |

## 内化原则

- 只提取安装核心内容（前置条件、安装命令、验证方法）
- 故障排查内容不重复（已有 troubleshooting-integration.md）
- 避免与现有文档重叠（DRY 原则）
- 精简为 100-120 行
