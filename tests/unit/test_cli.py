from typer.testing import CliRunner

from booksite.cli import app


def test_doctor_reports_core_runtime_without_crashing() -> None:
    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Python" in result.stdout
    assert "PyMuPDF" in result.stdout
