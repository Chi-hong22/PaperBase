# Troubleshooting Guide

Common issues and solutions for PaperBase.

## Environment Issues

### Python Version Too Old

**Symptom**:
```
Error: Python 3.11+ required, found 3.9.x
```

**Solution**:
```bash
# Check current version
python --version

# Install Python 3.11+ via pyenv (recommended)
pyenv install 3.11.5
pyenv global 3.11.5

# Or download from python.org
# https://www.python.org/downloads/
```

---

### uv Not Found

**Symptom**:
```
uv: command not found
```

**Solution**:
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify installation
uv --version
```

---

### graphify Not Found

**Symptom**:
```
⚠️  graphify 未找到（可选）
```

**Impact**: Cannot update knowledge graph or use semantic queries

**Solution**:
```bash
# Install graphify
uv tool install graphify

# Verify installation
graphify --version
```

---

## Configuration Issues

### LLM Configuration Error

**Symptom**:
```
Error: llm.model is required when llm.base_url is set
```

**Solution**:

1. Check config file:
```bash
paperbase config show
```

2. Set environment variables:
```bash
export PAPERBASE_LLM_BASE_URL="https://api.openai.com/v1"
export PAPERBASE_LLM_API_KEY="sk-..."
export PAPERBASE_LLM_MODEL="gpt-4o-mini"
```

3. Or edit `config/paperbase.yaml`:
```yaml
llm:
  base_url: ${PAPERBASE_LLM_BASE_URL}
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: ${PAPERBASE_LLM_MODEL}
```

4. Verify:
```bash
paperbase config show
```

---

### Library Path Not Found

**Symptom**:
```
Error: Library directory not found
```

**Solution**:

1. Set environment variable:
```bash
export PAPERBASE_LIBRARY="/path/to/PaperBase"
```

2. Or use `--base-dir`:
```bash
paperbase --base-dir /path/to/PaperBase status
```

3. Or run from PaperBase root directory:
```bash
cd /path/to/PaperBase
paperbase status
```

---

## Ingestion Issues

### PDF Download Failed

**Symptom**:
```
Error: Failed to download PDF from DOI
```

**Possible Causes**:
1. DOI not open access
2. Network connectivity issues
3. Publisher API limits

**Solutions**:

1. Check if paper is open access:
   - Try alternative sources (arXiv, ResearchGate)
   
2. Download PDF manually and use `--file`:
```bash
paperbase ingest --file ~/Downloads/paper.pdf
```

3. Check network:
```bash
curl -I https://doi.org/10.1234/abc
```

---

### PDF Conversion Failed

**Symptom**:
```
Error: Failed to convert PDF to Markdown
```

**Possible Causes**:
1. Corrupted PDF
2. Scanned PDF (images only, no text)
3. PDF with DRM protection

**Solutions**:

1. Verify PDF integrity:
```bash
pdfinfo paper.pdf
```

2. For scanned PDFs, use OCR first:
```bash
# Install tesseract
brew install tesseract  # macOS
apt-get install tesseract-ocr  # Linux

# OCR the PDF (manual step)
```

3. Try alternative PDF:
   - Download from different source
   - Request author's version

---

### State Stuck in NORMALIZED

**Symptom**:
```bash
$ paperbase status
Paper ID: doi:10.1234/abc
State: normalized  # Stuck here
```

**Cause**: Graph update not run or failed

**Solution**:
```bash
# Update graph
paperbase graph update

# If still stuck, force rebuild
paperbase graph update --force
```

---

## Graph Issues

### Graph Update Timeout

**Symptom**:
```
Error: graphify execution timeout (>5 minutes)
```

**Causes**:
1. Too many papers to process
2. LLM API slow/down
3. Network issues

**Solutions**:

1. Use incremental mode:
```bash
paperbase graph update --incremental
```

2. Check LLM API status:
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $PAPERBASE_LLM_API_KEY"
```

3. Process in batches (manual):
```bash
# Update small batches
for state_file in library/papers/*/manifest.json; do
  paperbase graph update --incremental
  sleep 10
done
```

---

### Graph Files Corrupted

**Symptom**:
```
Error: Failed to parse graph.json
```

**Solution**:

1. Rebuild graph from scratch:
```bash
rm -rf graph/
paperbase graph update --force
```

2. If still fails, check `paper.md` files:
```bash
# Find invalid paper.md files
find library/papers -name "paper.md" -exec python -c "
import sys
import yaml
try:
    with open('{}', 'r') as f:
        content = f.read()
        if '---' in content:
            yaml.safe_load(content.split('---')[1])
except Exception as e:
    print('{}: {}'.format('{}', e))
" \;
```

---

### Graphify Query Returns Empty

**Symptom**:
```
Query: "SLAM"
Result: (empty)
```

**Causes**:
1. No papers on that topic
2. Graph not updated
3. Papers in NORMALIZED state (not indexed)

**Solutions**:

1. Check paper states:
```bash
paperbase status --state normalized
```

2. Update graph:
```bash
paperbase graph update
```

3. Verify graph contents:
```bash
graphify query "list all concepts" --graph graph/
```

---

## Registry Issues

### Registry Database Locked

**Symptom**:
```
Error: database is locked
```

**Cause**: Another process accessing `papers.db`

**Solution**:

1. Find and kill the process:
```bash
# Find processes using papers.db
lsof registry/papers.db

# Kill the process
kill <PID>
```

2. Wait a moment and retry

3. If persists, rebuild registry:
```bash
mv registry/papers.db registry/papers.db.backup
paperbase status  # Auto-rebuilds
```

---

### Registry Out of Sync with Manifest

**Symptom**:
Papers show different states in `status` vs `manifest.json`

**Solution**:

1. Rebuild registry from manifests:
```bash
rm registry/papers.db
paperbase status  # Auto-rebuilds from manifests
```

2. Verify consistency:
```bash
python -m scripts.check_consistency
```

---

## Search Issues

### Full-Text Search Returns No Results

**Symptom**:
```bash
$ paperbase search "transformer"
No results found
```

**Causes**:
1. Papers not in READY state
2. FTS5 index not built
3. Typo in search term

**Solutions**:

1. Check paper states:
```bash
paperbase status --state ready
```

2. Try broader search:
```bash
paperbase search "transform*"  # Wildcard
```

3. Use semantic search instead:
```bash
/paperbase transformer 架构
```

---

## Performance Issues

### Graph Update Very Slow

**Symptoms**:
- Graph update takes > 5 minutes
- High CPU/memory usage

**Solutions**:

1. Use incremental mode:
```bash
paperbase graph update --incremental
```

2. Check system resources:
```bash
top  # Check CPU/RAM
df -h  # Check disk space
```

3. Reduce LLM timeout (in `config/paperbase.yaml`):
```yaml
llm:
  advanced:
    timeout: 30  # Reduce from 60
```

---

### Ingest Takes Too Long

**Symptoms**:
- Single paper ingest > 30 seconds

**Solutions**:

1. Skip graph update:
```bash
paperbase ingest "doi:10.1234/abc" --no-graph
```

2. Batch ingest:
```bash
paperbase ingest --batch papers.txt --no-graph
paperbase graph update  # Update once at the end
```

---

## Data Issues

### Duplicate Papers

**Symptom**:
Same paper appears multiple times with different IDs

**Cause**: Ingested via different identifiers (DOI vs arXiv)

**Solution**:

1. Identify duplicates:
```bash
paperbase status | grep -i "title"
```

2. Remove duplicate:
```bash
paperbase remove "arxiv:1706.03762"  # Keep DOI version
```

3. Update graph:
```bash
paperbase graph update --force
```

---

### Paper Metadata Wrong

**Symptom**:
Author name, year, or title incorrect

**Solution**:

1. Edit `paper.md` frontmatter:
```bash
nano library/papers/p_xxxxx/paper.md
```

2. Update SHA256 in manifest:
```bash
sha256sum library/papers/p_xxxxx/paper.md
# Copy hash to manifest.json canonical_md.sha256
```

3. Rebuild registry:
```bash
rm registry/papers.db
paperbase status
```

4. Rebuild graph:
```bash
paperbase graph update --force
```

---

## Diagnostic Commands

### Quick Health Check

```bash
paperbase doctor
```

### Detailed Status Check

```bash
# Check all papers
paperbase status

# Check specific state
paperbase status --state normalized

# Check specific paper
paperbase status "doi:10.1234/abc"
```

### Verify Data Integrity

```bash
# Check paper.md files
find library/papers -name "paper.md" -exec head -1 {} \;

# Check manifest files
find library/papers -name "manifest.json" -exec python -m json.tool {} \; > /dev/null

# Check registry
sqlite3 registry/papers.db "SELECT COUNT(*) FROM papers;"

# Check graph
ls -lh graph/
```

---

## Getting Help

### Information to Collect

When reporting issues, include:

1. Environment:
```bash
paperbase doctor
python --version
uv --version
graphify --version
```

2. Error message (full output)

3. Recent operations:
```bash
# What did you just run?
paperbase status
```

4. System info:
```bash
uname -a  # OS version
df -h .   # Disk space
```

### Where to Get Help

- GitHub Issues: `https://github.com/Chi-hong22/PaperBase/issues`
- Documentation: `README.md`, `AGENTS.md`
- This guide: `references/troubleshooting.md`

---

## Emergency Recovery

### Nuclear Option: Full Rebuild

If everything is broken:

```bash
# 1. Backup library/ (DO NOT skip this!)
cp -r library/ library.backup/

# 2. Remove derived data
rm -rf registry/
rm -rf graph/

# 3. Rebuild registry
paperbase status

# 4. Rebuild graph
paperbase graph update --force

# 5. Verify
paperbase doctor
```

This should fix most issues, but you'll lose any manual tweaks to registry/graph.

---

## Prevention

### Best Practices

1. **Regular backups**:
```bash
tar -czf paperbase-backup-$(date +%Y%m%d).tar.gz library/ config/
```

2. **Use version control**:
```bash
cd library/
git init
git add .
git commit -m "Checkpoint"
```

3. **Monitor disk space**:
```bash
df -h .
```

4. **Keep software updated**:
```bash
uv tool update graphify
```

5. **Test commands on one paper first**:
```bash
# Test on one paper
paperbase remove "doi:10.1234/test" --confirm

# Then batch
for doi in $(cat dois.txt); do
  paperbase remove "$doi" --confirm
done
```
