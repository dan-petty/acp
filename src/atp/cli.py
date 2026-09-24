"""Command-line interface for the Agentic Transfer Protocol (ATP).

Provides utilities to validate, inspect, and certify Epistemic State Envelopes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from atp.protocol.models import ATP_VERSION, EpistemicEnvelope


def _build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="atp",
        description="Agentic Transfer Protocol (ATP) validation and inspection CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # atp validate <envelope.json>
    validate_p = subparsers.add_parser("validate", help="Validate an Epistemic State Envelope file.")
    validate_p.add_argument("file", type=Path, help="Path to JSON file containing envelope.")

    # atp inspect <envelope.json>
    inspect_p = subparsers.add_parser(
        "inspect", help="Display human- and agent-readable summary of an envelope."
    )
    inspect_p.add_argument("file", type=Path, help="Path to JSON file containing envelope.")

    # atp version
    subparsers.add_parser("version", help="Print ATP protocol version.")

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
            f"✅ Envelope '{envelope.envelope_id}' is structurally valid (ATP v{envelope.atp_version}).\n"
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
            f"=== ATP Epistemic Envelope: {env.envelope_id} ===\n"
            f"Version:      {env.atp_version}\n"
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


def main(argv: Sequence[str] | None = None) -> int:
    """CLI execution entrypoint."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        sys.stdout.write(f"ATP v{ATP_VERSION}\n")
        return 0
    if args.command == "validate":
        return _cmd_validate(args.file)
    if args.command == "inspect":
        return _cmd_inspect(args.file)

    return 0


if __name__ == "__main__":
    sys.exit(main())
