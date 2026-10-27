from click.testing import CliRunner

import paperbase.cli.commands.ingest as ingest_command
from paperbase.cli.main import main


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
