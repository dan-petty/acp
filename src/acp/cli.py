"""Command-line interface for the Agentic Communication Protocol (ACP).

Provides utilities to validate, inspect, and certify Epistemic State Envelopes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from acp.protocol.models import ACP_VERSION, EpistemicEnvelope


def _build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="acp",
        description="Agentic Communication Protocol (ACP) validation and inspection CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # acp validate <envelope.json>
    validate_p = subparsers.add_parser("validate", help="Validate an Epistemic State Envelope file.")
    validate_p.add_argument("file", type=Path, help="Path to JSON file containing envelope.")

    # acp inspect <envelope.json>
    inspect_p = subparsers.add_parser(
        "inspect", help="Display human- and agent-readable summary of an envelope."
    )
    inspect_p.add_argument("file", type=Path, help="Path to JSON file containing envelope.")

    # acp version
    subparsers.add_parser("version", help="Print ACP protocol version.")

    # acp mcp
    subparsers.add_parser("mcp", help="Start ACP Model Context Protocol (MCP) server over standard I/O.")

    return parser


def _load_envelope(path: Path) -> EpistemicEnvelope:
    """Read and deserialize an envelope from disk."""
    if not path.is_file():
        raise FileNotFoundError(f"Envelope file not found: {path}")
    raw_content = path.read_text(encoding="utf-8")
    data = json.loads(raw_content)
    return EpistemicEnvelope.model_validate(data)


def _cmd_validate(path: Path) -> int:
    """Execute envelope validation."""
    try:
        envelope = _load_envelope(path)
        sys.stdout.write(
            f"✅ Envelope '{envelope.envelope_id}' is structurally valid (ACP v{envelope.acp_version}).\n"
        )
        return 0
    except (ValidationError, json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"❌ Envelope validation failed: {exc}\n")
        return 1


def _cmd_inspect(path: Path) -> int:
    """Inspect and summarize an envelope."""
    try:
        env = _load_envelope(path)
        leash = env.budget_leash
        output = (
            f"=== ACP Epistemic Envelope: {env.envelope_id} ===\n"
            f"Version:      {env.acp_version}\n"
            f"Traceparent:  {env.traceparent}\n"
            f"Goal:         {env.telos.goal}\n"
            f"Repository:   {env.workspace_context.repository} @ {env.workspace_context.commit_base[:8]}\n"
            f"Budget Leash:\n"
            f"  - Max Tokens: {leash.token_limit}\n"
            f"  - Max Cost:   ${leash.max_cost_usd:.2f}\n"
            f"  - Max Tools:  {leash.max_tool_invocations}\n"
            f"Exit Criteria ({len(env.telos.exit_criteria)}):\n"
        )
        for criterion in env.telos.exit_criteria:
            output += f"  * {criterion}\n"
        sys.stdout.write(output)
        return 0
    except (ValidationError, json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"❌ Failed to inspect envelope: {exc}\n")
        return 1


def _cmd_mcp() -> int:
    """Start MCP server on standard I/O."""
    from acp.mcp.server import run_stdio_server

    run_stdio_server()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI execution entrypoint."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        sys.stdout.write(f"ACP v{ACP_VERSION}\n")
        return 0
    if args.command == "validate":
        return _cmd_validate(args.file)
    if args.command == "inspect":
        return _cmd_inspect(args.file)
    if args.command == "mcp":
        return _cmd_mcp()

    return 0


if __name__ == "__main__":
    sys.exit(main())
