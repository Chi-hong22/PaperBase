# Schema 验证规则

## 时间戳验证

所有时间戳字段必须符合 ISO 8601 格式：
- `YYYY-MM-DDTHH:MM:SSZ`
- `YYYY-MM-DDTHH:MM:SS+08:00`
- `YYYY-MM-DDTHH:MM:SS.123456Z`

**验证字段**：
- PaperProvenance.ingested_at
- SourcePDF.acquired_at
- ManifestSchema.created_at/updated_at
- GraphInfo.updated_at

## 枚举验证

- `PaperVenue.type`: journal, conference, preprint
- `PaperSource.discovery`: zotero, search, manual
- `PaperChunks.strategy`: section-aware-v1

## 数值范围验证

- `PaperReferences.count`: >= 0
- `PaperMetadata.year`: 1000-2100

## SHA256 验证

必须是 64 位小写十六进制字符串。

**验证字段**：
- SourcePDF.sha256
- PaperProvenance.source_pdf_sha256
- PaperProvenance.canonical_content_sha256
