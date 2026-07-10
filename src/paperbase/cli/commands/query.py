"""query 命令实现

CLI 高级用户参数化查询接口。

与 /paperbase skill 的区别：
- query CLI: 显式子命令 + 参数控制（如 --depth），适合终端手动操作
- /paperbase skill: 自动路由 + 自然语言，适合 AI Agent 工作流
"""

import click
import json
from rich.console import Console
from rich.table import Table
from pathlib import Path
from paperbase.core.graph_query import find_related_papers, find_papers_by_topic
from paperbase.core.registry import PaperRegistry


@click.group()
def query():
    """图谱查询论文（高级用户参数化控制）

    AI Agent 请使用 /paperbase skill 进行自然语言查询。
    """
    pass


@query.command()
@click.argument("paper_id")
@click.option(
    "--depth",
    "-d",
    type=int,
    default=2,
    help="遍历深度（推荐 2）。1=直接连接（主要是概念/引用），2=通过共享概念找相关论文，3=更广但噪音大"
)
@click.pass_context
def related(ctx, paper_id: str, depth: int):
    """查找相关论文

    通过知识图谱查找与指定论文相关的其他论文。

    depth 参数说明：

    - depth=1: 返回直接连接的节点，主要是概念、引用文献、技术节点。
      论文节点之间很少直接连接，通常返回 15-20 个节点，但几乎不包含其他论文。

    - depth=2: 推荐值。通过共享的概念节点（如 bathymetric_slam、multibeam_echo_sounder）
      或共享的引用文献找到相关论文。通常返回 25-45 个节点，包含 3-7 篇相关论文。

    - depth=3: 返回更广泛的关联，但噪音较大。可能返回 70+ 个节点，但论文比例较低。

    学术图谱特点：论文之间通过主题、方法论、引用文献间接关联，而非直接连接。
    因此 depth=2 是发现论文语义关联的最佳平衡点。
    """
    console = Console()
    base_dir = ctx.obj["base_dir"]

    graph_dir = base_dir / "graph"
    registry_path = base_dir / "registry" / "papers.db"

    # 检查 graph 目录是否存在
    if not graph_dir.exists():
        console.print("[yellow]图谱目录不存在，请先生成图谱[/yellow]")
        console.print("提示: 使用 'paperbase graph' 命令生成图谱")
        return

    # 检查 graph.json 是否存在
    graph_file = graph_dir / "graph.json"
    if not graph_file.exists():
        console.print("[yellow]图谱文件不存在，请先生成图谱[/yellow]")
        console.print("提示: 使用 'paperbase graph' 命令生成图谱")
        return

    # 检查 registry 是否存在
    if not registry_path.exists():
        console.print("[yellow]Registry 不存在，请先摄入论文[/yellow]")
        return

    # 将 paper_id 转换为 storage_id
    registry = PaperRegistry(registry_path)
    paper_info = registry.get_paper(paper_id)

    if not paper_info:
        console.print(f"[red]未找到论文: {paper_id}[/red]")
        registry.close()
        return

    storage_id = paper_info["storage_id"]

    # 图谱中的节点可能有后缀（如 _paper），需要找到匹配的节点 ID
    # 先尝试精确匹配，如果不存在则尝试带后缀的变体
    import json
    graph_file = graph_dir / "graph.json"
    with open(graph_file, "r", encoding="utf-8") as f:
        graph_data = json.load(f)

    # 查找匹配的节点 ID（可能是 storage_id 或 storage_id_paper 等）
    all_node_ids = [n.get("id") for n in graph_data.get("nodes", []) if n.get("id")]
    graph_node_id = None

    # 构建邻接表以检查哪些节点有连接
    edges = graph_data.get("links", graph_data.get("edges", []))
    connected_nodes = set()
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source:
            connected_nodes.add(source)
        if target:
            connected_nodes.add(target)

    # 尝试精确匹配
    if storage_id in all_node_ids and storage_id in connected_nodes:
        graph_node_id = storage_id
    else:
        # 尝试找到以 storage_id 开头的节点
        matches = [nid for nid in all_node_ids if nid.startswith(storage_id + "_")]
        if matches:
            # 优先选择有连接的节点
            connected_matches = [m for m in matches if m in connected_nodes]
            if connected_matches:
                # 在有连接的节点中，优先选择 _paper 后缀
                paper_suffix = [m for m in connected_matches if m.endswith("_paper")]
                graph_node_id = paper_suffix[0] if paper_suffix else connected_matches[0]
            else:
                # 如果都没有连接，则选择第一个
                graph_node_id = matches[0]

    if not graph_node_id:
        console.print(f"[yellow]论文 {paper_id} 不在知识图谱中[/yellow]")
        console.print("提示: 运行 'paperbase graph update' 更新图谱")
        registry.close()
        return

    # 执行查询（使用图谱节点 ID）
    try:
        related_node_ids = find_related_papers(graph_dir, graph_node_id, depth)
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        registry.close()
        return

    if not related_node_ids:
        console.print(f"[yellow]未找到与 {paper_id} 相关的论文[/yellow]")
        registry.close()
        return

    # 将图谱节点 ID 转换回 storage_id，再转换为 paper_id
    table = Table(title=f"相关论文: {paper_id} (depth={depth})")
    table.add_column("Paper ID", style="magenta", width=25)
    table.add_column("Title", style="white", width=60)
    table.add_column("Authors", style="cyan", width=30)
    table.add_column("Year", style="green", width=6)

    papers = registry.list_papers()
    seen_storage_ids = set()  # 去重

    for node_id in related_node_ids:
        # 提取 storage_id（去除后缀）
        import re
        storage_id_match = re.match(r'^(p_[0-9a-f]{12})', node_id)
        sid = storage_id_match.group(1) if storage_id_match else node_id

        # 去重
        if sid in seen_storage_ids:
            continue
        seen_storage_ids.add(sid)

        # 通过 storage_id 查找 paper
        paper = next((p for p in papers if p["storage_id"] == sid), None)

        if paper:
            pid = paper["paper_id"]
            title = paper["title"] if paper["title"] else "N/A"
            authors = paper["authors"] if paper["authors"] else []
            year = str(paper["year"]) if paper["year"] else "N/A"

            # 截断过长的 title
            if len(title) > 50:
                title = title[:47] + "..."

            # 转换 authors list 为字符串并截断
            if isinstance(authors, list):
                # 处理 list，元素可能是 dict 或 str
                author_names = [a.get("name", "Unknown") if isinstance(a, dict) else str(a) for a in authors]
                authors = ", ".join(author_names)
            elif isinstance(authors, str):
                # 可能是 JSON 字符串
                try:
                    authors_list = json.loads(authors)
                    if isinstance(authors_list, list):
                        author_names = [a.get("name", "Unknown") if isinstance(a, dict) else str(a) for a in authors_list]
                        authors = ", ".join(author_names)
                except (json.JSONDecodeError, AttributeError):
                    pass
            else:
                authors = str(authors)

            if len(authors) > 25:
                authors = authors[:22] + "..."

            table.add_row(pid, title, authors, year)
        else:
            # storage_id 不在 registry 中（引用文献）
            # 从图谱中提取标题
            node = next((n for n in graph_data.get("nodes", []) if n.get("id") == node_id), None)
            ref_title = node.get("label", "N/A") if node else "N/A"

            # 截断
            if len(node_id) > 25:
                display_id = node_id[:22] + "..."
            else:
                display_id = node_id

            if len(ref_title) > 50:
                ref_title = ref_title[:47] + "..."

            table.add_row(f"[dim]{display_id}[/dim]", f"[dim]{ref_title}[/dim]", "[dim]引用文献[/dim]", "[dim]N/A[/dim]")

    console.print(table)
    console.print(f"\n[dim]找到 {len(related_node_ids)} 个相关论文[/dim]")

    registry.close()


@query.command()
@click.argument("topic")
@click.option("--include-refs", is_flag=True, help="包含引用文献")
@click.pass_context
def topic(ctx, topic: str, include_refs: bool):
    """按主题查找论文"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    graph_dir = base_dir / "graph"
    registry_path = base_dir / "registry" / "papers.db"

    # 检查 graph 目录是否存在
    if not graph_dir.exists():
        console.print("[yellow]图谱目录不存在，请先生成图谱[/yellow]")
        console.print("提示: 使用 'paperbase graph' 命令生成图谱")
        return

    # 检查 graph.json 是否存在
    graph_file = graph_dir / "graph.json"
    if not graph_file.exists():
        console.print("[yellow]图谱文件不存在，请先生成图谱[/yellow]")
        console.print("提示: 使用 'paperbase graph' 命令生成图谱")
        return

    # 检查 registry 是否存在
    if not registry_path.exists():
        console.print("[yellow]Registry 不存在，请先摄入论文[/yellow]")
        return

    # 执行查询（返回 node_id 列表）
    try:
        matched_node_ids = find_papers_by_topic(graph_dir, topic, include_refs)
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        return

    if not matched_node_ids:
        console.print(f"[yellow]未找到主题为 '{topic}' 的论文[/yellow]")
        return

    # 将 node_id 转换为 paper_id 并获取元数据
    registry = PaperRegistry(registry_path)
    papers = registry.list_papers()

    # 分离本地论文和引用文献
    local_papers = []
    ref_papers = []
    seen_storage_ids = set()  # 去重集合

    for nid in matched_node_ids:
        # 判断是否为本地论文：所有以 p_ 开头的节点（除了 _ref_ 条目）
        import re
        is_local = nid.startswith('p_') and '_ref_' not in nid

        if is_local:
            # 提取 storage_id（去除可能的后缀）
            # p_2ddac761b162_paper → p_2ddac761b162
            # p_c083f6a2c977_attention_is_all_you_need → p_c083f6a2c977
            storage_id_match = re.match(r'^(p_[0-9a-f]{12})', nid)
            storage_id = storage_id_match.group(1) if storage_id_match else nid

            # 去重：跳过已处理的 storage_id
            if storage_id in seen_storage_ids:
                continue
            seen_storage_ids.add(storage_id)

            # 本地论文：从 registry 查找
            paper = next((p for p in papers if p["storage_id"] == storage_id), None)
            if paper:
                local_papers.append({
                    "id": paper["paper_id"],
                    "title": paper["title"] or "N/A",
                    "authors": paper["authors"] or [],
                    "year": str(paper["year"]) if paper["year"] else "N/A",
                    "type": "本地"
                })
        else:
            # 引用文献：从 graph.json 提取标签作为标题
            # 提取 storage_id 前缀（用于显示来源）
            storage_prefix = nid.split('_')[0] + '_' + nid.split('_')[1] if '_' in nid else nid
            source_paper = next((p for p in papers if p["storage_id"] == storage_prefix), None)
            source_info = f"引用自: {source_paper['title'][:20]}..." if source_paper else "引用文献"

            # 从节点标签提取标题（需要重新加载图谱）
            import json
            graph_file = graph_dir / "graph.json"
            with open(graph_file, "r", encoding="utf-8") as f:
                graph_data = json.load(f)

            node = next((n for n in graph_data.get("nodes", []) if n.get("id") == nid), None)
            ref_title = node.get("label", "N/A") if node else "N/A"

            ref_papers.append({
                "id": nid,
                "title": ref_title,
                "authors": source_info,  # 复用 authors 列显示来源
                "year": "N/A",
                "type": "引用"
            })

    # 构建表格
    table = Table(title=f"主题查询: {topic}")
    table.add_column("Paper ID", style="magenta", width=25)
    table.add_column("Title", style="white", width=60)
    table.add_column("Authors", style="cyan", width=30)
    table.add_column("Year", style="green", width=6)

    # 先显示本地论文
    for paper in local_papers:
        pid = paper["id"]
        title = paper["title"]
        authors = paper["authors"]
        year = paper["year"]

        # 截断过长的 title
        if len(title) > 50:
            title = title[:47] + "..."

        # 转换 authors 为字符串
        if isinstance(authors, str):
            # 数据库中存储的是 JSON 字符串，需要反序列化
            try:
                authors_list = json.loads(authors)
                if isinstance(authors_list, list):
                    # 提取 name 字段
                    author_names = [a.get("name", "Unknown") if isinstance(a, dict) else str(a) for a in authors_list]
                    authors = ", ".join(author_names)
                else:
                    authors = str(authors_list)
            except (json.JSONDecodeError, AttributeError):
                authors = str(authors)
        elif isinstance(authors, list):
            # 处理 list，元素可能是 dict 或 str
            author_names = [a.get("name", "Unknown") if isinstance(a, dict) else str(a) for a in authors]
            authors = ", ".join(author_names)
        else:
            authors = str(authors)

        if len(authors) > 25:
            authors = authors[:22] + "..."

        table.add_row(pid, title, authors, year)

    # 再显示引用文献（如果有）
    if ref_papers:
        # 添加分隔行
        if local_papers:
            table.add_row("", "[dim]--- 引用文献 ---[/dim]", "", "")

        for ref in ref_papers:
            nid = ref["id"]
            title = ref["title"]
            source = ref["authors"]  # 来源信息

            # 截断
            if len(nid) > 25:
                nid = nid[:22] + "..."
            if len(title) > 50:
                title = title[:47] + "..."
            if len(source) > 25:
                source = source[:22] + "..."

            table.add_row(f"[dim]{nid}[/dim]", f"[dim]{title}[/dim]", f"[dim]{source}[/dim]", "[dim]N/A[/dim]")

    console.print(table)

    # 统计信息
    if include_refs:
        console.print(f"\n[dim]本地论文: {len(local_papers)} 篇, 引用文献: {len(ref_papers)} 篇[/dim]")
    else:
        console.print(f"\n[dim]找到 {len(local_papers)} 个论文[/dim]")

    registry.close()
