from paperbase.schemas.manifest import ManifestSchema, PaperState, SourceArtifact


def test_manifest_accepts_online_source_artifacts():
    artifact = SourceArtifact(
        path="./source/paper-fetch.json",
        kind="paper-fetch-json",
        acquired_at="2026-07-08T00:00:00+00:00",
        provider="paper-fetch",
        original_url="https://doi.org/10.1234/example",
        sha256="a" * 64,
    )

    manifest = ManifestSchema(
        paper_id="doi:10.1234/example",
        storage_id="p_example",
        state=PaperState.NORMALIZED,
        source_artifacts=[artifact],
    )

    assert manifest.source_artifacts[0].path == "./source/paper-fetch.json"
    assert manifest.source_artifacts[0].kind == "paper-fetch-json"
    assert manifest.source_artifacts[0].provider == "paper-fetch"
