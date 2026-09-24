"""Unit tests for the ACP MCP (Model Context Protocol) gateway server."""

from __future__ import annotations

import io
import json

from acp.mcp.server import ACPMCPServer, run_stdio_server
from acp.protocol.crypto import generate_keypair, sign_delegation


def test_mcp_initialize():
    """Verify MCP initialize lifecycle response."""
    server = ACPMCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    }
    resp = server.handle_request(req)
    assert (
        resp["id"],
        resp["result"]["serverInfo"]["name"],
        resp["result"]["protocolVersion"],
    ) == (1, "acp-mcp", "2024-11-05")


def test_mcp_tools_list():
    """Verify tools/list exposes all registered ACP protocol tools."""
    server = ACPMCPServer()
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    resp = server.handle_request(req)
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    assert (
        resp["id"],
        "acp_probe" in tool_names,
        "acp_create_envelope" in tool_names,
        "acp_verify_delegation" in tool_names,
        "acp_fold" in tool_names,
        "acp_yield" in tool_names,
    ) == (2, True, True, True, True, True)


def test_mcp_tool_probe():
    """Verify executing acp_probe tool."""
    server = ACPMCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "acp_probe",
            "arguments": {
                "agent_id": "agent:worker-01",
                "model_id": "claude-3-7-sonnet",
                "context_window_available": 64000,
                "required_tokens": 16000,
                "ax_score": 0.95,
                "min_ax_score": 0.80,
            },
        },
    }
    resp = server.handle_request(req)
    data = json.loads(resp["result"]["content"][0]["text"])
    assert (resp["id"], data["status"], data["agent_id"]) == (3, "CERTIFIED", "agent:worker-01")


def test_mcp_tool_create_envelope():
    """Verify executing acp_create_envelope tool."""
    server = ACPMCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "acp_create_envelope",
            "arguments": {
                "goal": "Refactor router",
                "exit_criteria": ["pytest passes"],
                "token_limit": 8000,
                "max_cost_usd": 0.10,
                "repository": "dan-petty/acp",
                "commit_base": "abc1234",
            },
        },
    }
    resp = server.handle_request(req)
    data = json.loads(resp["result"]["content"][0]["text"])
    assert (
        resp["id"],
        data["telos"]["goal"],
        data["budget_leash"]["token_limit"],
    ) == (4, "Refactor router", 8000)


def test_mcp_tool_verify_delegation():
    """Verify executing acp_verify_delegation tool."""
    server = ACPMCPServer()
    seed_hex, pub_hex = generate_keypair()
    chain = sign_delegation(
        private_seed_hex=seed_hex,
        issuer="user:dan@example.com",
        subject="agent:worker",
        capabilities=["repo:read"],
    )
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "acp_verify_delegation",
            "arguments": {
                "delegation_chain": chain.model_dump(),
                "issuer_public_key_hex": pub_hex,
            },
        },
    }
    resp = server.handle_request(req)
    data = json.loads(resp["result"]["content"][0]["text"])
    assert (resp["id"], data["is_valid"], data["subject"]) == (5, True, "agent:worker")


def test_mcp_tool_fold_and_yield():
    """Verify executing acp_fold and acp_yield tools."""
    server = ACPMCPServer()
    fold_req = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "acp_fold",
            "arguments": {
                "patch_diff": "diff --git ...",
                "invariants_certified": ["M<=6"],
                "tokens_spent": 1200,
                "cost_usd": 0.015,
            },
        },
    }
    fold_resp = server.handle_request(fold_req)
    fold_data = json.loads(fold_resp["result"]["content"][0]["text"])

    yield_req = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "acp_yield",
            "arguments": {
                "reason": "Capability cliff",
                "cliff_category": "CAPABILITY_CEILING",
                "counterexample_input": "input_a",
                "expected": "output_b",
                "failing_actual": "output_c",
            },
        },
    }
    yield_resp = server.handle_request(yield_req)
    yield_data = json.loads(yield_resp["result"]["content"][0]["text"])

    assert (
        fold_data["status"],
        fold_data["tokens_spent"],
        yield_data["cliff_category"],
    ) == ("SUCCESS", 1200, "CAPABILITY_CEILING")


def test_mcp_run_stdio_server():
    """Verify line-by-line stdio server stream processing."""
    req1 = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    req2 = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
    input_stream = io.StringIO(f"{req1}\n\n{req2}\n")
    output_stream = io.StringIO()

    run_stdio_server(input_stream=input_stream, output_stream=output_stream)
    lines = [json.loads(line) for line in output_stream.getvalue().strip().split("\n")]
    assert (len(lines), lines[0]["id"], lines[1]["id"]) == (2, 1, 2)


def test_mcp_unknown_method_and_unknown_tool():
    """Verify error responses for unrecognized RPC methods and tools."""
    server = ACPMCPServer()
    method_req = {"jsonrpc": "2.0", "id": 10, "method": "non_existent_method"}
    method_resp = server.handle_request(method_req)

    tool_req = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {"name": "invalid_tool", "arguments": {}},
    }
    tool_resp = server.handle_request(tool_req)

    assert (
        method_resp["error"]["code"],
        tool_resp["error"]["code"],
        server.handle_request({"method": "notifications/initialized"}),
    ) == (-32601, -32000, None)
