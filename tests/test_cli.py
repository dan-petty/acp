"""Unit tests for ATP CLI commands."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from atp.cli import main
from atp.protocol.models import (
    ATP_VERSION,
    BudgetLeash,
    EpistemicEnvelope,
    InvariantContract,
    Telos,
    WorkspaceContext,
)


def _write_temp_envelope(valid: bool = True) -> Path:
    """Helper writing a valid or corrupted envelope to a temp file."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        if valid:
            env = EpistemicEnvelope(
                atp_version=ATP_VERSION,
                envelope_id="cli-test-01",
                traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                budget_leash=BudgetLeash(token_limit=8000, max_cost_usd=0.15, max_tool_invocations=5),
                telos=Telos(goal="CLI test verification", exit_criteria=["exit 0"]),
                invariant_contract=InvariantContract(),
                workspace_context=WorkspaceContext(repository="dan-petty/atp", commit_base="1234567"),
            )
            tmp.write(env.model_dump_json())
        else:
            tmp.write("{ invalid json")
        return Path(tmp.name)


def test_cli_version():
    with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        code = main(["version"])
    assert (code, f"ATP v{ATP_VERSION}" in mock_stdout.getvalue()) == (0, True)


def test_cli_validate_success():
    path = _write_temp_envelope(valid=True)
    try:
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = main(["validate", str(path)])
        assert (code, "structurally valid" in mock_stdout.getvalue()) == (0, True)
    finally:
        path.unlink()


def test_cli_validate_failure():
    path = _write_temp_envelope(valid=False)
    try:
        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            code = main(["validate", str(path)])
        assert (code, "validation failed" in mock_stderr.getvalue()) == (1, True)
    finally:
        path.unlink()


def test_cli_inspect_success():
    path = _write_temp_envelope(valid=True)
    try:
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = main(["inspect", str(path)])
        output = mock_stdout.getvalue()
        assert (
            code,
            "CLI test verification" in output,
            "Max Tokens: 8000" in output,
        ) == (
            0,
            True,
            True,
        )
    finally:
        path.unlink()
