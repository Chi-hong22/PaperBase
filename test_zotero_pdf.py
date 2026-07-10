"""手动测试 Zotero PDF 导入功能"""

from pathlib import Path
from paperbase.adapters.zotero_adapter import ZoteroAdapter, ZoteroUnavailable

def test_get_pdf_path():
    """测试获取 PDF 路径功能"""
    print("=" * 60)
    print("测试 Zotero PDF 路径获取功能")
    print("=" * 60)

    try:
        # 初始化 adapter（本地模式）
        print("\n1. 初始化 ZoteroAdapter（本地模式）...")
        adapter = ZoteroAdapter(local_mode=True)
        print("   ✓ 初始化成功")

        # 测试获取最近条目
        print("\n2. 获取最近 5 篇论文...")
        items = adapter.list_recent(limit=5)
        print(f"   ✓ 找到 {len(items)} 篇论文")

        if not items:
            print("\n⚠ Zotero 中没有论文，无法继续测试")
            return

        # 测试每个条目的 PDF 路径
        print("\n3. 测试 PDF 路径获取：")
        for i, item in enumerate(items, 1):
            print(f"\n   [{i}] {item.title[:60]}...")
            print(f"       Key: {item.key}")
            print(f"       Has PDF: {item.has_pdf}")

            if item.has_pdf:
                pdf_path = adapter.get_pdf_path(item.key)
                if pdf_path:
                    print(f"       ✓ PDF 路径: {pdf_path}")
                    print(f"       ✓ 文件存在: {Path(pdf_path).exists()}")
                else:
                    print(f"       ✗ 无法获取 PDF 路径")
            else:
                print(f"       - 无 PDF 附件")

        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)

    except ZoteroUnavailable as e:
        print(f"\n✗ Zotero 不可用: {e}")
        print("\n提示：")
        print("  1. 确保 Zotero 应用正在运行")
        print("  2. 确保已安装 zotero-mcp-server: uv tool install zotero-mcp-server")

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_get_pdf_path()
