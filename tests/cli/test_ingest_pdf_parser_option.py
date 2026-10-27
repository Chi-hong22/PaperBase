from click.testing import CliRunner

import paperbase.cli.commands.ingest as ingest_command
from paperbase.cli.main import main
from paperbase.core.identity import generate_storage_id, normalize_paper_id
from paperbase.core.manifest import load_manifest
from paperbase.core.paths import PaperPaths
from paperbase.core.pdf_conversion import ReadyConversionOutcome


def test_pdf_parser_option_is_forwarded_to_local_pdf_ingest(monkeypatch, tmp_path):
    input_pdf = tmp_path / "sample.pdf"
    input_pdf.write_bytes(b"synthetic PDF")
    calls = []

    monkeypatch.setattr(
        ingest_command,
        "_ingest_local_pdf",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "ingest", "--file", str(input_pdf), "--pdf-parser", "remote"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0][1]["pdf_parser"] == "remote"


def test_pdf_parser_option_is_forwarded_through_batch(monkeypatch, tmp_path):
    batch_file = tmp_path / "papers.txt"
    batch_file.write_text("10.1234/example\n", encoding="utf-8")
    calls = []

    monkeypatch.setattr(
        ingest_command,
        "_ingest_batch",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "ingest", "--batch", str(batch_file), "--pdf-parser", "local"],
    )

    assert result.exit_code == 0, result.output
    assert calls[0][1]["pdf_parser"] == "local"


def test_config_show_never_displays_remote_api_key(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secret = "test-remote-secret-do-not-print"
    (config_dir / "paperbase.yaml").write_text(
        "conversion:\n  pdf:\n    remote:\n      providers:\n"
        "        - name: primary\n          provider: oxr\n"
        f"          api_key: {secret}\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "config", "show"],
    )

    assert result.exit_code == 0, result.output
    assert secret not in result.output
    assert "primary" in result.output


def test_local_ingest_keeps_existing_pipeline_when_converter_is_none(monkeypatch, tmp_path):
    class ReadyWithMissingConverter(ReadyConversionOutcome):
        converter = None
        converter_version = None

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"synthetic PDF")
    paper_id = normalize_paper_id("10.1234/missing-converter")
    storage_id = generate_storage_id(paper_id)
    metadata = {
        "title": "Local parser fallback",
        "authors": ["Ada Lovelace"],
        "year": 2026,
        "doi": "10.1234/missing-converter",
        "abstract": "Synthetic metadata for the local parser fallback test.",
    }
    monkeypatch.setattr(ingest_command, "extract_pdf_metadata", lambda _: metadata)
    monkeypatch.setattr(
        ingest_command,
        "progressPdfConversion",
        lambda *_args, **_kwargs: ReadyWithMissingConverter(
            markdown="# Local parser fallback\n\n" + ("Body evidence. " * 100)
        ),
    )
    monkeypatch.setattr(ingest_command, "ReadyConversionOutcome", ReadyWithMissingConverter)

    result = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "ingest", "--file", str(pdf_path), "--no-graph"],
    )

    assert result.exit_code == 0, result.output
    paths = PaperPaths(storage_id=storage_id, base_dir=tmp_path)
    manifest = load_manifest(paths.manifest_json)
    assert manifest.pipeline.converter == "markitdown"
    assert manifest.pipeline.converter_version == "0.0.1"
