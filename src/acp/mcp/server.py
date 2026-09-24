"""Model Context Protocol (MCP) server exposing ACP protocol operations as tools."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any, TextIO
from uuid import uuid4

from acp.protocol.crypto import verify_delegation
from acp.protocol.models import (
    ACP_VERSION,
    BudgetLeash,
    CEGISCounterexample,
    DelegationChain,
    EpistemicEnvelope,
    FoldPayload,
    InvariantContract,
    ProbePayload,
    Telos,
    WorkspaceContext,
    YieldPayload,
)
from acp.protocol.verbs import evaluate_peer_compatibility

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"

TOOLS_METADATA: list[dict[str, Any]] = [
    {
        "name": "acp_probe",
        "description": "Evaluate peer agent capability, context headroom, and AX score compatibility.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "model_id": {"type": "string"},
                "context_window_available": {"type": "integer"},
                "required_tokens": {"type": "integer"},
                "ax_score": {"type": "number", "default": 1.0},
                "min_ax_score": {"type": "number", "default": 0.75},
            },
            "required": ["agent_id", "model_id", "context_window_available", "required_tokens"],
            "additionalProperties": False,
        },
    },
    {
        "name": "acp_create_envelope",
        "description": "Create a validated Epistemic State Envelope for task delegation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "exit_criteria": {"type": "array", "items": {"type": "string"}},
                "token_limit": {"type": "integer"},
                "max_cost_usd": {"type": "number"},
                "repository": {"type": "string"},
                "commit_base": {"type": "string"},
                "positive_invariants": {"type": "array", "items": {"type": "string"}},
                "negative_constraints": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["goal", "exit_criteria", "token_limit", "max_cost_usd", "repository", "commit_base"],
            "additionalProperties": False,
        },
    },
    {
        "name": "acp_verify_delegation",
        "description": "Cryptographically verify an Ed25519 delegation chain proof.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "delegation_chain": {"type": "object"},
                "issuer_public_key_hex": {"type": "string"},
            },
            "required": ["delegation_chain", "issuer_public_key_hex"],
            "additionalProperties": False,
        },
    },
    {
        "name": "acp_fold",
        "description": "Synthesize a structured epistemic fold payload upon task completion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch_diff": {"type": "string"},
                "invariants_certified": {"type": "array", "items": {"type": "string"}},
                "tokens_spent": {"type": "integer"},
                "cost_usd": {"type": "number"},
            },
            "required": ["patch_diff", "invariants_certified", "tokens_spent", "cost_usd"],
            "additionalProperties": False,
        },
    },
    {
        "name": "acp_yield",
        "description": "Escalate a capability barrier with a structured CEGIS counterexample.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "cliff_category": {
                    "type": "string",
                    "enum": [
                        "CAPABILITY_CEILING",
                        "BUDGET_EXHAUSTION",
                        "CIRCULAR_DEPENDENCY",
                        "SECURITY_VIOLATION",
                    ],
                },
                "counterexample_input": {"type": "string"},
                "expected": {"type": "string"},
                "failing_actual": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["reason", "cliff_category", "counterexample_input", "expected", "failing_actual"],
            "additionalProperties": False,
        },
    },
]


def _handle_tool_probe(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute acp_probe tool."""
    probe = ProbePayload(
        agent_id=arguments["agent_id"],
        model_id=arguments["model_id"],
        context_window_total=arguments.get("context_window_total", 128000),
        context_window_available=arguments["context_window_available"],
        ax_score=arguments.get("ax_score", 1.0),
    )
    evaluate_peer_compatibility(
        probe=probe,
        required_tokens=arguments["required_tokens"],
        min_ax_score=arguments.get("min_ax_score", 0.75),
    )
    return {"status": "CERTIFIED", "agent_id": probe.agent_id, "ax_score": probe.ax_score}


def _handle_tool_create_envelope(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute acp_create_envelope tool."""
    envelope = EpistemicEnvelope(
        acp_version=ACP_VERSION,
        envelope_id=str(uuid4()),
        traceparent=f"00-{uuid4().hex}-{uuid4().hex[:16]}-01",
        budget_leash=BudgetLeash(
            token_limit=arguments["token_limit"],
            max_cost_usd=arguments["max_cost_usd"],
            max_tool_invocations=arguments.get("max_tool_invocations", 10),
        ),
        telos=Telos(goal=arguments["goal"], exit_criteria=arguments["exit_criteria"]),
        invariant_contract=InvariantContract(
            positive_invariants=arguments.get("positive_invariants", []),
            negative_constraints=arguments.get("negative_constraints", []),
        ),
        workspace_context=WorkspaceContext(
            repository=arguments["repository"],
            commit_base=arguments["commit_base"],
        ),
    )
    return json.loads(envelope.model_dump_json())


def _handle_tool_verify_delegation(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute acp_verify_delegation tool."""
    chain = DelegationChain(**arguments["delegation_chain"])
    is_valid = verify_delegation(chain, arguments["issuer_public_key_hex"])
    return {"is_valid": is_valid, "issuer": chain.issuer, "subject": chain.subject}


def _handle_tool_fold(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute acp_fold tool."""
    fold = FoldPayload(
        status="SUCCESS",
        patch_diff=arguments["patch_diff"],
        invariants_certified=arguments["invariants_certified"],
        tokens_spent=arguments["tokens_spent"],
        cost_usd=arguments["cost_usd"],
    )
    return json.loads(fold.model_dump_json())


def _handle_tool_yield(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute acp_yield tool."""
    counterexample = CEGISCounterexample(
        input=arguments["counterexample_input"],
        expected=arguments["expected"],
        failing_actual=arguments["failing_actual"],
        rationale=arguments.get("rationale"),
    )
    payload = YieldPayload(
        reason=arguments["reason"],
        cliff_category=arguments["cliff_category"],
        unresolvable_counterexample=counterexample.model_dump_json(),
    )
    return json.loads(payload.model_dump_json())


TOOL_DISPATCH: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "acp_probe": _handle_tool_probe,
    "acp_create_envelope": _handle_tool_create_envelope,
    "acp_verify_delegation": _handle_tool_verify_delegation,
    "acp_fold": _handle_tool_fold,
    "acp_yield": _handle_tool_yield,
}


class ACPMCPServer:
    """Standard JSON-RPC 2.0 MCP server for ACP."""

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single JSON-RPC MCP request dictionary."""
        req_id = request.get("id")
        method = request.get("method", "")

        dispatch_table: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "ping": lambda _: {},
        }

        if method == "notifications/initialized":
            return None

        handler = dispatch_table.get(method)
        if not handler:
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        try:
            result = handler(request.get("params", {}))
            return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": result}
        except Exception as exc:
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    def _handle_initialize(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "acp-mcp", "version": ACP_VERSION},
        }

    def _handle_tools_list(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"tools": TOOLS_METADATA}

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = TOOL_DISPATCH.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")

        output = handler(arguments)
        return {"content": [{"type": "text", "text": json.dumps(output, indent=2)}], "isError": False}


def _process_stdio_line(server: ACPMCPServer, line: str) -> str | None:
    """Parse and dispatch a single JSON-RPC line, returning serialized response or None."""
    clean_line = line.strip()
    if not clean_line:
        return None
    try:
        request = json.loads(clean_line)
    except json.JSONDecodeError:
        return None
    response = server.handle_request(request)
    return (json.dumps(response) + "\n") if response is not None else None


def run_stdio_server(input_stream: TextIO | None = None, output_stream: TextIO | None = None) -> None:
    """Run MCP server reading JSON-RPC lines from input and writing to output."""
    in_stream = input_stream or sys.stdin
    out_stream = output_stream or sys.stdout
    server = ACPMCPServer()

    for line in in_stream:
        payload = _process_stdio_line(server, line)
        if payload is not None:
            out_stream.write(payload)
            out_stream.flush()
