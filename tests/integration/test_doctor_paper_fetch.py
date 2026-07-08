from click.testing import CliRunner

from paperbase.cli.main import main


def test_doctor_reports_paper_fetch_status(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["--base-dir", str(tmp_path), "doctor"])

    assert result.exit_code == 0
    assert "paper-fetch" in result.output
