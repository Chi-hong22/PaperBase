import re
from pathlib import Path

from click.testing import CliRunner

from paperbase.cli.main import main
from paperbase.config.loader import load_config

PROJECT_ROOT = Path(__file__).parents[2]


def _documented_pdf_config() -> str:
    document = (PROJECT_ROOT / "docs" / "remote-document-parsing.md").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"<!-- remote-config-example:start -->\s*```yaml\s*\n(.*?)\n```",
        document,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


def test_documented_config_loads_and_config_show_masks_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("OXR_API_KEY", "example-secret-primary")
    monkeypatch.setenv("OXR_FALLBACK_API_KEY", "example-secret-secondary")
    config_path = tmp_path / "config" / "paperbase.yaml"
    config_path.parent.mkdir()
    config_path.write_text(_documented_pdf_config(), encoding="utf-8")

    config = load_config(config_path)
    shown = CliRunner().invoke(
        main,
        ["--base-dir", str(tmp_path), "config", "show"],
    )

    assert config.conversion.pdf.parser == "local"
    assert [item.name for item in config.conversion.pdf.remote.providers] == [
        "oxr-primary",
        "oxr-secondary",
    ]
    assert [item.timeout for item in config.conversion.pdf.remote.providers] == [300, 300]
    assert shown.exit_code == 0, shown.output
    assert "oxr-primary" in shown.output and "oxr-secondary" in shown.output
    assert "example-secret-primary" not in shown.output
    assert "example-secret-secondary" not in shown.output


def test_documented_parser_override_matches_ingest_help():
    result = CliRunner().invoke(main, ["ingest", "--help"])

    assert result.exit_code == 0, result.output
    assert "--pdf-parser [local|remote]" in result.output
