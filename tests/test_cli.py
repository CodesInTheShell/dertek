from typer.testing import CliRunner

from dertek.cli.app import app

runner = CliRunner()


def test_help_lists_approval_mode_option_and_choices() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--approval-mode" in result.stdout
    assert "on-request" in result.stdout
    assert "never" in result.stdout
    assert "auto" in result.stdout


def test_invalid_approval_mode_is_rejected() -> None:
    result = runner.invoke(app, ["--approval-mode", "unsafe-value", "hello"])
    assert result.exit_code == 2
