"""PaperBase 统一查询 skill"""
import re
import subprocess
from pathlib import Path
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState


def paperbase_query(query: str, base_dir: Path = Path.cwd()) -> str:
    """PaperBase 统一查询入口

    根据查询模式智能路由到 Registry 或 Graphify
    """
    if is_structured_query(query):
        return query_registry(query, base_dir)
    else:
        return query_graph(query, base_dir)


def is_structured_query(query: str) -> bool:
    """判断是否为结构化查询"""
    patterns = [
        r'doi:',
        r'paper_id:',
        r'state:',
        r'year:',
        r'author:',
        r'\blist\b',
        r'\bshow\s+all\b'
    ]
    return any(re.search(p, query, re.IGNORECASE) for p in patterns)


def query_registry(query: str, base_dir: Path) -> str:
    """执行 Registry 结构化查询"""
    registry_path = base_dir / "registry" / "papers.db"

    if not registry_path.exists():
        return "Registry 不存在，请先摄入论文"

    registry = PaperRegistry(registry_path)
    try:
        # doi 查询
        if 'doi:' in query.lower():
            paper_id = query.split('doi:', 1)[1].strip()
            if not paper_id.startswith('doi:'):
                paper_id = f"doi:{paper_id}"
            result = registry.get_paper(paper_id)
            return format_paper(result) if result else f"未找到论文: {paper_id}"

        # state 查询
        elif 'state:' in query.lower():
            state_str = query.split('state:', 1)[1].strip()
            try:
                state = PaperState(state_str)
                papers = registry.list_papers(state=state)
                return format_papers(papers, f"状态为 {state_str}")
            except ValueError:
                return f"无效的状态: {state_str}"

        # year 查询
        elif 'year:' in query.lower():
            year_str = query.split('year:', 1)[1].strip()
            try:
                year = int(year_str)
                all_papers = registry.list_papers()
                papers = [p for p in all_papers if p.get('year') == year]
                return format_papers(papers, f"年份为 {year}")
            except ValueError:
                return f"无效的年份: {year_str}"

        # author 查询
        elif 'author:' in query.lower():
            author_name = query.split('author:', 1)[1].strip().strip('"\'')
            all_papers = registry.list_papers()
            papers = [p for p in all_papers if any(author_name.lower() in author.lower() for author in p.get('authors', []))]
            return format_papers(papers, f"作者包含 {author_name}")

        # list 查询
        else:
            papers = registry.list_papers()
            return format_papers(papers, "全部论文")

    finally:
        registry.close()


def query_graph(query: str, base_dir: Path) -> str:
    """执行 Graphify 语义查询"""
    graph_dir = base_dir / "library" / "graphify-out"

    if not graph_dir.exists() or not (graph_dir / "graph.json").exists():
        return "图谱不存在，请先运行 'paperbase graph update' 构建图谱"

    try:
        # 调用 graphify query
        result = subprocess.run(
            ['graphify', 'query', query],
            capture_output=True,
            text=True,
            cwd=base_dir / "library",
            timeout=30
        )

        if result.returncode == 0:
            return result.stdout.strip() or "查询成功但无结果"
        else:
            return f"Graphify 查询失败: {result.stderr.strip()}"

    except FileNotFoundError:
        return "graphify 未安装，请运行 'uv tool install graphifyy'"
    except subprocess.TimeoutExpired:
        return "查询超时（30秒）"
    except Exception as e:
        return f"查询出错: {str(e)}"


def format_paper(paper: dict) -> str:
    """格式化单个论文"""
    return f"""论文信息:
  Title: {paper.get('title', 'N/A')}
  Year: {paper.get('year', 'N/A')}
  State: {paper.get('state', 'N/A')}
  Authors: {', '.join(paper.get('authors', [])[:3])}
  DOI: {paper.get('doi', 'N/A')}
  Paper ID: {paper.get('paper_id', 'N/A')}"""


def format_papers(papers: list, title: str = "查询结果") -> str:
    """格式化论文列表"""
    if not papers:
        return f"{title}: 未找到论文"

    output = [f"{title}: 找到 {len(papers)} 篇论文\n"]

    for i, paper in enumerate(papers[:10], 1):
        output.append(f"{i}. {paper.get('title', 'N/A')} ({paper.get('year', 'N/A')})")
        output.append(f"   State: {paper.get('state', 'N/A')}")
        if paper.get('authors'):
            authors = ', '.join(paper['authors'][:2])
            output.append(f"   Authors: {authors}")

    if len(papers) > 10:
        output.append(f"\n... 及其他 {len(papers) - 10} 篇论文")

    return '\n'.join(output)
