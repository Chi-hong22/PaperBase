# Query Routing Guide

How PaperBase intelligently routes queries to the right execution path.

## Overview

PaperBase uses a **dual-track query system**:

```
User Query
    ↓
Pattern Matching
    ↓
┌─────────────────────┬──────────────────────┐
│  Structured Query   │   Semantic Query     │
│  → Registry (SQL)   │   → Graphify (LLM)   │
└─────────────────────┴──────────────────────┘
```

---

## Routing Logic

### Pattern Detection

The `query_router.py` module uses regex patterns to classify queries:

```python
def is_structured_query(query: str) -> bool:
    """Check if query matches structured patterns"""
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
```

### Routing Table

| Pattern | Example | Routed To | Why |
|---------|---------|-----------|-----|
| `doi:` | `doi:10.1234/abc` | Registry | Exact match |
| `paper_id:` | `paper_id:doi:10.1234/abc` | Registry | Exact match |
| `state:` | `state:ready` | Registry | Enumerated values |
| `year:` | `year:2024` | Registry | Numeric filter |
| `author:` | `author:Zhang` | Registry | String matching |
| `list` | `list all papers` | Registry | List operation |
| `show all` | `show all` | Registry | List operation |
| *other* | `SLAM 相关论文` | Graphify | Semantic |

---

## Registry Track (Structured)

### When to Use

- Exact identifier lookups (DOI, paper_id)
- State filtering
- Metadata filtering (year, author)
- Listing all papers

### Strengths

✅ Fast (< 100ms typical)  
✅ No LLM cost  
✅ Precise matching  
✅ Deterministic results  

### Limitations

❌ No semantic understanding  
❌ Exact match only  
❌ No concept relationships  

### Implementation

```python
def query_registry(query: str, base_dir: Path) -> str:
    registry = PaperRegistry(base_dir / "registry" / "papers.db")
    
    if 'doi:' in query.lower():
        paper_id = extract_paper_id(query)
        result = registry.get_paper(paper_id)
        return format_paper(result)
    
    elif 'state:' in query.lower():
        state_str = extract_state(query)
        state = PaperState(state_str)
        papers = registry.list_papers(state=state)
        return format_papers(papers)
    
    # ... other patterns
```

### Query Examples

```python
# DOI lookup
query = "doi:10.1038/nature12373"
→ SELECT * FROM papers WHERE paper_id = 'doi:10.1038/nature12373'

# State filter
query = "state:ready"
→ SELECT * FROM papers WHERE state = 'ready'

# Year filter
query = "year:2024"
→ SELECT * FROM papers WHERE year = 2024

# Author search
query = "author:Zhang"
→ SELECT * FROM papers WHERE authors LIKE '%Zhang%'

# List all
query = "list all papers"
→ SELECT * FROM papers ORDER BY updated_at DESC
```

---

## Graphify Track (Semantic)

### When to Use

- Natural language queries
- Concept relationships
- Topic exploration
- "Papers related to X"
- Cross-domain queries

### Strengths

✅ Semantic understanding  
✅ Concept relationships  
✅ Theme-based exploration  
✅ Finds non-obvious connections  

### Limitations

❌ Slower (2-5 seconds typical)  
❌ Requires LLM API  
❌ Costs tokens (~$0.001-0.01 per query)  
❌ Non-deterministic  

### Implementation

```python
def query_graph(query: str, base_dir: Path) -> str:
    graph_dir = base_dir / "graph"
    
    # Check if graph exists
    if not (graph_dir / "graph.json").exists():
        return "Graph not found, run 'paperbase graph update'"
    
    # Call graphify subprocess
    result = subprocess.run(
        ['graphify', 'query', query],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=base_dir
    )
    
    return result.stdout
```

### Query Examples

```python
# Semantic queries (routed to Graphify)
"SLAM 相关论文"
"深度学习和计算机视觉的交叉研究"
"水下导航技术"
"transformer 架构的演进"
"粒子滤波在机器人中的应用"
```

### How Graphify Works

1. **Index Phase** (happens during `graph update`):
   ```
   paper.md → LLM extracts concepts → graph.json
   ```

2. **Query Phase**:
   ```
   User query → LLM understands intent → Search graph → Return papers
   ```

---

## Edge Cases

### Ambiguous Queries

Some queries could go either way:

```python
# "author DOI" - contains both patterns
query = "author of doi:10.1234/abc"
→ Routed to Registry (doi: pattern matched first)

# "state of SLAM"
query = "state of SLAM research"
→ Routed to Graphify (semantic intent dominates)
```

**Resolution**: First match wins. Registry patterns checked first.

### Empty Results

```python
# Registry returns empty
query = "doi:10.9999/nonexistent"
→ "未找到论文: doi:10.9999/nonexistent"

# Graphify returns empty
query = "quantum computing"  # no papers on this topic
→ "查询成功，但未找到结果"
```

### Fallback Behavior

```python
# Graphify not installed
query = "SLAM 相关论文"
→ "graphify 未安装，请运行: uv tool install graphify"

# Graph not built
query = "深度学习"
→ "图谱不存在，请先运行 'paperbase graph update' 构建图谱"
```

---

## Performance Tuning

### Registry Optimization

```sql
-- Add indexes for common queries
CREATE INDEX idx_papers_state ON papers(state);
CREATE INDEX idx_papers_year ON papers(year);
CREATE INDEX idx_papers_doi ON papers(doi);
```

### Graphify Optimization

```yaml
# config/paperbase.yaml
graph:
  advanced:
    mode: incremental  # Only update changed papers
```

**Incremental updates**: 10x faster than full rebuild

---

## Query Router API

### Python Interface

```python
from query_router import paperbase_query

# Automatic routing
result = paperbase_query("doi:10.1234/abc", base_dir=Path("/path/to/PaperBase"))
print(result)

# Manual routing
from query_router import is_structured_query, query_registry, query_graph

if is_structured_query(query):
    result = query_registry(query, base_dir)
else:
    result = query_graph(query, base_dir)
```

### Bash Interface

```bash
# Via skill wrapper
/paperbase doi:10.1234/abc
/paperbase state:ready
/paperbase SLAM 相关论文

# Via CLI (explicit subcommands)
paperbase status "doi:10.1234/abc"
paperbase status --state ready
paperbase query topic "SLAM"
```

---

## Testing Query Routing

### Test Structured Patterns

```python
from query_router import is_structured_query

assert is_structured_query("doi:10.1234/abc") == True
assert is_structured_query("state:ready") == True
assert is_structured_query("year:2024") == True
assert is_structured_query("author:Zhang") == True
assert is_structured_query("list all") == True
```

### Test Semantic Routing

```python
assert is_structured_query("SLAM 相关论文") == False
assert is_structured_query("深度学习和计算机视觉") == False
assert is_structured_query("水下导航技术") == False
```

### Integration Test

```bash
# Start with known data
paperbase ingest "doi:10.1234/test"
paperbase graph update

# Test Registry track
/paperbase doi:10.1234/test  # Should return paper info

# Test Graphify track
/paperbase SLAM  # Should search semantically
```

---

## Debugging

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

result = paperbase_query(query, base_dir)
# Prints:
# DEBUG: Detected structured query: doi:10.1234/abc
# DEBUG: Routing to Registry
# DEBUG: Found paper in registry
```

### Trace Query Path

```python
def paperbase_query(query: str, base_dir: Path) -> str:
    if is_structured_query(query):
        print(f"→ Registry: {query}")
        return query_registry(query, base_dir)
    else:
        print(f"→ Graphify: {query}")
        return query_graph(query, base_dir)
```

### Check Graph Status

```bash
# Verify graph exists
ls graph/graph.json

# Check graph stats
paperbase graph status

# Test graphify directly
graphify query "SLAM" --graph graph/
```

---

## Best Practices

### For Users

1. Use structured queries when you know exact identifiers
2. Use semantic queries for exploration
3. Combine both: Registry to filter, Graphify to explore

### For Developers

1. Keep structured patterns simple and fast
2. Fail gracefully when graphify unavailable
3. Cache graph queries if possible (future enhancement)
4. Monitor query performance and adjust routing

---

## Future Enhancements

### Planned

- [ ] Hybrid queries (Registry + Graphify)
- [ ] Query result caching
- [ ] Multi-modal search (text + figures)
- [ ] Federated search across multiple PaperBase instances

### Under Consideration

- [ ] Learning from user feedback (which queries → which track)
- [ ] Fuzzy matching in Registry
- [ ] Graphify fallback to full-text search
