#!/usr/bin/env python3
"""文档质量检查工具"""

import re
from pathlib import Path

def check_document(file_path: Path):
    """检查单个文档的质量问题"""
    print(f"\n{'='*60}")
    print(f"检查: {file_path}")
    print('='*60)

    content = file_path.read_text(encoding='utf-8')
    issues = []

    # 1. 检查代码块是否闭合
    backticks = content.count('```')
    if backticks % 2 != 0:
        issues.append(f"❌ 代码块未闭合（``` 数量: {backticks}）")
    else:
        print(f"✓ 代码块闭合正确（{backticks//2} 个代码块）")

    # 2. 检查代码块语言标注
    code_blocks = re.findall(r'```(\w*)\n', content)
    unlabeled = sum(1 for lang in code_blocks if not lang)
    if unlabeled > 0:
        issues.append(f"⚠️  有 {unlabeled} 个代码块缺少语言标注")
    else:
        print(f"✓ 所有代码块都有语言标注")

    # 3. 检查标题层级
    h1_count = len(re.findall(r'^# [^#]', content, re.MULTILINE))
    h2_count = len(re.findall(r'^## [^#]', content, re.MULTILINE))
    h3_count = len(re.findall(r'^### [^#]', content, re.MULTILINE))

    if h1_count == 0:
        issues.append("❌ 缺少一级标题")
    elif h1_count > 1:
        issues.append(f"⚠️  有 {h1_count} 个一级标题（建议只有1个）")
    else:
        print(f"✓ 标题结构合理（H1:{h1_count}, H2:{h2_count}, H3:{h3_count}）")

    # 4. 检查链接
    links = re.findall(r'\[([^\]]+)\]\(([^)]*)\)', content)
    empty_links = [text for text, url in links if not url]
    if empty_links:
        issues.append(f"❌ 有 {len(empty_links)} 个空链接")
    else:
        print(f"✓ 所有链接都有目标（{len(links)} 个链接）")

    # 5. 检查 TODO/FIXME
    todos = re.findall(r'TODO|FIXME|XXX', content)
    if todos:
        issues.append(f"⚠️  包含 {len(todos)} 个 TODO/FIXME 标记")
    else:
        print(f"✓ 无未完成标记")

    # 6. 检查中英文混排空格（扩展 Unicode 范围）
    # CJK 统一汉字基本区 + 扩展 A
    mixed = re.findall(r'[一-鿿㐀-䶿][a-zA-Z]|[a-zA-Z][一-鿿㐀-䶿]', content)
    if len(mixed) > 50:
        issues.append(f"⚠️  中英文混排较多（{len(mixed)} 处），建议检查是否需要空格")

    # 7. 检查行长度
    lines = content.split('\n')
    long_lines = [i+1 for i, line in enumerate(lines) if len(line) > 120 and not line.startswith('```')]
    if len(long_lines) > 10:
        issues.append(f"⚠️  有 {len(long_lines)} 行超过120字符（非代码块）")

    # 8. 检查文档结构
    if '## ' not in content:
        issues.append("❌ 缺少二级标题，文档结构可能不完整")

    # 9. 检查是否有示例
    if 'example' not in content.lower() and '示例' not in content and '例子' not in content:
        issues.append("⚠️  文档中可能缺少示例")

    # 10. 检查Windows路径（可能需要转义）
    windows_paths = re.findall(r'[A-Z]:\\[^`\s]+', content)
    if windows_paths:
        print(f"ℹ️  包含 {len(windows_paths)} 个 Windows 路径")

    # 输出问题
    if issues:
        print("\n发现的问题:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✅ 未发现明显问题")

    # 统计信息
    print(f"\n统计:")
    print(f"  总行数: {len(lines)}")
    print(f"  总字符数: {len(content)}")
    print(f"  代码块数: {backticks//2 if backticks % 2 == 0 else '未闭合'}")

    return len(issues)

# 检查三个文档
docs_to_check = [
    Path("docs/troubleshooting/llm-config-issues.md"),
    Path("docs/improvements/config-refactoring.md"),
    Path("docs/improvements/extract-command.md"),
]

total_issues = 0
for doc in docs_to_check:
    if doc.exists():
        total_issues += check_document(doc)
    else:
        print(f"❌ 文件不存在: {doc}")

print(f"\n{'='*60}")
print(f"总计发现 {total_issues} 类问题")
print('='*60)
