# RFC 0002: AGTP Wire Protocol Binding Specification

- **Document Version**: `1.0.0-draft`
- **Status**: Standard Proposal
- **Date**: 2026-09-24
- **Authors**: Dan Petty & Antigravity (Google DeepMind)
- **Repository**: [`dan-petty/acp`](https://github.com/dan-petty/acp)
- **Companion Draft**: IETF `draft-hood-independent-agtp` (Chris Hood, Nomotic, Inc.)

---

## 1. Abstract & Motivation

The **Agent Transfer Protocol (AGTP)**, as defined in IETF *`draft-hood-independent-agtp`*, provides an agent-native application-layer transport protocol designed to replace HTTP for autonomous AI agent traffic. Operating over TCP/TLS and QUIC on IANA-assigned port **4480** (and using the `agtp://` URI scheme), AGTP establishes an eighteen-method protocol floor featuring imperative intent verbs (`DELEGATE`, `ESCALATE`, `CONFIRM`, `SUSPEND`, `DISCOVER`, `NOTIFY`, etc.).

While AGTP solves network-level framing, direct addressing, and session multiplexing, it intentionally leaves payload data unconstrained, explicitly stating:
> *"AGTP is designed to support and carry higher-level agent frameworks (such as MCP, A2A, and ACP) as content types within its method invocations, rather than replacing them."*

This specification defines **RFC 0002: AGTP Wire Protocol Binding for ACP**, standardizing how **Agentic Communication Protocol (ACP)** Epistemic State Envelopes, CEGIS counterexamples, and budget leashes map onto the wire format of AGTP/1.0.

---

## 2. Wire Format & Framing Invariants

In accordance with *`draft-hood-independent-agtp`*:
1. **Header Block**: HTTP-style ASCII/UTF-8 key-value headers separated by CRLF (`\r\n`) and terminated by double CRLF (`\r\n\r\n`).
2. **Strict Content-Length Framing**: All AGTP messages MUST include an explicit `Content-Length` header indicating the exact byte length of the body. Transport-level connection closure MUST NOT be used to signal message termination.
3. **Chunked Encoding Prohibited**: Chunked transfer encoding is explicitly forbidden in AGTP.
4. **Content-Type**: Epistemic state frames carried within AGTP bodies use:
   `Content-Type: application/agtp+json` (or `application/vnd.acp.envelope+json`).

### Wire Syntax Examples:

#### A. Task Delegation (`DELEGATE` Method):
```http
DELEGATE /v1/tasks/refactor AGTP/1.0
Host: worker.local:4480
Agent-ID: agent:orchestrator
Principal-ID: user:dan@example.com
Authority-Scope: repo:read,repo:write,test:run
Session-ID: 7b34da6a-3ce9-29d0-e0e4-73600f067aa0
Traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
Content-Type: application/agtp+json
Content-Length: 1420

{
  "acp_version": "1.0.0",
  "envelope_id": "7b34da6a-3ce9-29d0-e0e4-73600f067aa0",
  "budget_leash": {
    "token_limit": 4000,
    "max_cost_usd": 0.05,
    "max_tool_invocations": 5
  },
  "telos": {
    "goal": "Refactor procedural router to table dispatch",
    "exit_criteria": ["pytest passes", "M <= 4"]
  },
  "invariant_contract": { ... },
  "workspace_context": { ... },
  "compacted_reasoning_ledger": [ ... ]
}
```

#### B. Capability Barrier Escalation (`ESCALATE` / HTTP 422 Response):
```http
AGTP/1.0 422 Unprocessable Entity
Session-ID: 7b34da6a-3ce9-29d0-e0e4-73600f067aa0
Content-Type: application/agtp+json
Content-Length: 326

{
  "reason": "Subsystem recursion exceeds local sandbox capability",
  "cliff_category": "CAPABILITY_CEILING",
  "unresolvable_counterexample": "{\"input\":\"dispatch('/legacy')\",\"expected\":\"200\",\"failing_actual\":\"500\"}"
}
```

#### C. Epistemic Fold Confirmation (`CONFIRM` / HTTP 200 Response):
```http
AGTP/1.0 200 OK
Session-ID: 7b34da6a-3ce9-29d0-e0e4-73600f067aa0
Content-Type: application/agtp+json
Content-Length: 412

{
  "status": "SUCCESS",
  "patch_diff": "diff --git a/router.py ...\n+TABLE_DISPATCH = {...}",
  "invariants_certified": ["M <= 4", "100% test pass"],
  "tokens_spent": 1420,
  "cost_usd": 0.018
}
```

---

## 3. Protocol Verb & Status Code Mapping Table

| ACP Frame Type | AGTP Wire Method | AGTP Wire Status | Payload Carried |
|---|---|---|---|
| `ACP_HANDOFF_REQUEST` | `DELEGATE` | N/A (Request) | `EpistemicEnvelope` |
| `ACP_HANDOFF_RESPONSE` | N/A | `202 Accepted` | None (Empty Body) |
| `ACP_FOLD_REQUEST` | `CONFIRM` | N/A (Request) | `FoldPayload` |
| `ACP_FOLD_RESPONSE` | N/A | `200 OK` | `FoldPayload` |
| `ACP_YIELD_REQUEST` | `ESCALATE` | N/A (Request) | `YieldPayload` |
| `ACP_YIELD_RESPONSE` | N/A | `422 Unprocessable Entity` | `YieldPayload` |
| `ACP_PROBE_REQUEST` | `DISCOVER` | N/A (Request) | `ProbePayload` (Optional) |
| `ACP_PROBE_RESPONSE` | N/A | `200 OK` | `ProbePayload` |
| `ACP_PREEMPT_REQUEST` | `NOTIFY` | N/A (Request) | Out-of-Band Control Frame |

---

## 4. AGTP Header Synthesis & Invariant Rules

1. **`Session-ID`**: Set to the unique `frame_id` / `envelope_id` UUID of the transaction.
2. **`Traceparent`**: Mirrors the W3C traceparent string from `envelope.traceparent`.
3. **`Agent-ID`**: Extracted from `envelope.delegation_chain.subject` (or probe `agent_id`).
4. **`Principal-ID`**: Extracted from `envelope.delegation_chain.issuer`.
5. **`Authority-Scope`**: Formatted as a comma-separated list of cryptographically attested capabilities (`repo:read,repo:write`).
6. **Negative Schema Enforcement**: Bodies MUST be validated with `additionalProperties: false` (or `extra="forbid"` in Pydantic v2). Unrecognized fields trigger an immediate AGTP 400 Bad Request error.

---

## 5. Reference Implementations

This repository provides certified, polyglot reference implementations of the AGTP wire protocol:
- **Python**: [`acp.protocol.agtp_wire`](file:///workspaces/devops-cli/repos/dan-petty/acp/src/acp/protocol/agtp_wire.py) and [`AGTPTransport`](file:///workspaces/devops-cli/repos/dan-petty/acp/src/acp/protocol/transport.py)
- **Rust**: [`crates/acp/src/transport/agtp.rs`](file:///workspaces/devops-cli/repos/dan-petty/acp/crates/acp/src/transport/agtp.rs)
