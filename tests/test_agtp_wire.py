"""Unit tests for AGTP (draft-hood-independent-agtp) wire protocol codec and transport."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from acp.protocol.agtp_wire import (
    AGTPRequest,
    AGTPResponse,
    agtp_request_to_frame,
    agtp_response_to_frame,
    encode_agtp_request,
    encode_agtp_response,
    frame_to_agtp_request,
    frame_to_agtp_response,
    parse_agtp_request,
    parse_agtp_response,
    read_agtp_request,
    read_agtp_response,
)
from acp.protocol.models import (
    ACP_VERSION,
    BudgetLeash,
    DelegationChain,
    EpistemicEnvelope,
    FoldPayload,
    InvariantContract,
    ProbePayload,
    ProtocolFrame,
    Telos,
    WorkspaceContext,
    YieldPayload,
)
from acp.protocol.transport import AGTPTransport


def _sample_envelope() -> EpistemicEnvelope:
    return EpistemicEnvelope(
        acp_version=ACP_VERSION,
        envelope_id="agtp-test-01",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        delegation_chain=DelegationChain(
            issuer="user:dan@example.com",
            subject="agent:worker",
            capabilities=["repo:read", "repo:write"],
            proof="test_proof_signature_001",
        ),
        budget_leash=BudgetLeash(token_limit=5000, max_cost_usd=0.05, max_tool_invocations=4),
        telos=Telos(goal="Test AGTP", exit_criteria=["assert ok"]),
        invariant_contract=InvariantContract(),
        workspace_context=WorkspaceContext(repository="dan-petty/acp", commit_base="1234567"),
    )


def test_agtp_request_encode_and_parse():
    req = AGTPRequest(
        method="DELEGATE",
        uri="/v1/tasks/refactor",
        headers={"Agent-ID": "agent:worker", "Session-ID": "sess-123"},
        body=b'{"task": "refactor"}',
    )
    raw = encode_agtp_request(req)
    assert b"DELEGATE /v1/tasks/refactor AGTP/1.0\r\n" in raw
    assert b"Content-Length: 20\r\n" in raw

    parsed = parse_agtp_request(raw)
    assert (
        parsed.method,
        parsed.uri,
        parsed.headers["Agent-ID"],
        parsed.headers["Content-Length"],
        parsed.body,
    ) == ("DELEGATE", "/v1/tasks/refactor", "agent:worker", "20", b'{"task": "refactor"}')


def test_agtp_response_encode_and_parse():
    resp = AGTPResponse(
        status_code=200,
        reason_phrase="OK",
        headers={"Session-ID": "sess-456"},
        body=b'{"result": "success"}',
    )
    raw = encode_agtp_response(resp)
    assert b"AGTP/1.0 200 OK\r\n" in raw
    assert b"Content-Length: 21\r\n" in raw

    parsed = parse_agtp_response(raw)
    assert (parsed.status_code, parsed.reason_phrase, parsed.body) == (
        200,
        "OK",
        b'{"result": "success"}',
    )


def test_agtp_invalid_method_rejected():
    with pytest.raises(ValueError) as exc:
        AGTPRequest(method="INVALID_VERB", uri="/test")
    assert "Invalid or unrecognized AGTP method" in str(exc.value)


def test_agtp_content_length_mismatch_rejected():
    raw = b"DELEGATE /test AGTP/1.0\r\nContent-Length: 50\r\n\r\nshort body"
    with pytest.raises(ValueError) as exc:
        parse_agtp_request(raw)
    assert "Content-Length mismatch" in str(exc.value)


def test_agtp_missing_content_length_rejected():
    raw = b"DELEGATE /test AGTP/1.0\r\nAgent-ID: test\r\n\r\nbody"
    with pytest.raises(ValueError) as exc:
        parse_agtp_request(raw)
    assert "mandates explicit Content-Length" in str(exc.value)


@pytest.mark.asyncio
async def test_read_agtp_stream_framing():
    req = AGTPRequest(
        method="EXECUTE",
        uri="/run",
        headers={"Agent-ID": "agent:tester"},
        body=b"payload_data",
    )
    encoded = encode_agtp_request(req)

    reader = asyncio.StreamReader()
    reader.feed_data(encoded)
    reader.feed_eof()

    read_req = await read_agtp_request(reader)
    assert (read_req.method, read_req.uri, read_req.body) == ("EXECUTE", "/run", b"payload_data")


@pytest.mark.asyncio
async def test_read_agtp_response_stream_framing():
    resp = AGTPResponse(
        status_code=422,
        reason_phrase="Unprocessable Entity",
        body=b"escalation_data",
    )
    encoded = encode_agtp_response(resp)

    reader = asyncio.StreamReader()
    reader.feed_data(encoded)
    reader.feed_eof()

    read_resp = await read_agtp_response(reader)
    assert (read_resp.status_code, read_resp.reason_phrase, read_resp.body) == (
        422,
        "Unprocessable Entity",
        b"escalation_data",
    )


def test_protocol_frame_to_agtp_delegate_roundtrip():
    envelope = _sample_envelope()
    frame = ProtocolFrame(frame_type="ACP_HANDOFF_REQUEST", envelope=envelope)

    agtp_req = frame_to_agtp_request(frame, target_uri="/v1/tasks/delegate")
    assert (
        agtp_req.method,
        agtp_req.uri,
        agtp_req.headers["Agent-ID"],
        agtp_req.headers["Principal-ID"],
        agtp_req.headers["Authority-Scope"],
    ) == (
        "DELEGATE",
        "/v1/tasks/delegate",
        "agent:worker",
        "user:dan@example.com",
        "repo:read,repo:write",
    )

    reconstructed_frame = agtp_request_to_frame(agtp_req)
    assert (
        reconstructed_frame.frame_type,
        reconstructed_frame.envelope.envelope_id,
        reconstructed_frame.envelope.telos.goal,
    ) == (
        "ACP_HANDOFF_REQUEST",
        "agtp-test-01",
        "Test AGTP",
    )


def test_protocol_frame_to_agtp_fold_and_yield_roundtrip():
    fold_p = FoldPayload(status="SUCCESS", patch_diff="+ok", invariants_certified=["M<=4"])
    fold_frame = ProtocolFrame(frame_type="ACP_FOLD_RESPONSE", fold_payload=fold_p)

    agtp_resp = frame_to_agtp_response(fold_frame)
    assert (agtp_resp.status_code, agtp_resp.reason_phrase) == (200, "OK")

    reconstructed_fold = agtp_response_to_frame(agtp_resp)
    assert (
        reconstructed_fold.frame_type,
        reconstructed_fold.fold_payload.status,
        reconstructed_fold.fold_payload.patch_diff,
    ) == ("ACP_FOLD_RESPONSE", "SUCCESS", "+ok")

    yield_p = YieldPayload(reason="Cliff", cliff_category="CAPABILITY_CEILING")
    yield_frame = ProtocolFrame(frame_type="ACP_YIELD_RESPONSE", yield_payload=yield_p)

    agtp_yield_resp = frame_to_agtp_response(yield_frame)
    assert (agtp_yield_resp.status_code, agtp_yield_resp.reason_phrase) == (422, "Unprocessable Entity")

    reconstructed_yield = agtp_response_to_frame(agtp_yield_resp)
    assert (
        reconstructed_yield.frame_type,
        reconstructed_yield.yield_payload.cliff_category,
    ) == ("ACP_YIELD_RESPONSE", "CAPABILITY_CEILING")


@pytest.mark.asyncio
async def test_agtp_transport_duplex_unix_socket():
    with tempfile.TemporaryDirectory() as tmp_dir:
        sock_path = str(Path(tmp_dir) / "agtp_wire.sock")
        envelope = _sample_envelope()
        server_frames: list[ProtocolFrame] = []

        async def _server_handler(reader, writer):
            transport = AGTPTransport(reader, writer, is_client=False)
            frame = await transport.receive_frame()
            server_frames.append(frame)

            fold_resp = ProtocolFrame(
                frame_type="ACP_FOLD_RESPONSE",
                fold_payload=FoldPayload(status="SUCCESS", patch_diff="+refactored"),
            )
            await transport.send_frame(fold_resp)
            await transport.close()

        server = await asyncio.start_unix_server(_server_handler, path=sock_path)

        client_transport = await AGTPTransport.connect_unix(sock_path, target_uri="/v1/tasks/delegate")
        req_frame = ProtocolFrame(frame_type="ACP_HANDOFF_REQUEST", envelope=envelope)
        await client_transport.send_frame(req_frame)

        reply = await client_transport.receive_frame()
        await client_transport.close()

        server.close()
        await server.wait_closed()

        assert (
            len(server_frames),
            server_frames[0].frame_type,
            reply.frame_type,
            reply.fold_payload.status,
        ) == (
            1,
            "ACP_HANDOFF_REQUEST",
            "ACP_FOLD_RESPONSE",
            "SUCCESS",
        )


def test_agtp_fold_and_yield_request_roundtrip():
    fold_p = FoldPayload(status="SUCCESS", patch_diff="+delta")
    fold_frame = ProtocolFrame(frame_type="ACP_FOLD_REQUEST", fold_payload=fold_p)
    fold_req = frame_to_agtp_request(fold_frame)

    yield_p = YieldPayload(reason="Ceiling", cliff_category="CAPABILITY_CEILING")
    yield_frame = ProtocolFrame(frame_type="ACP_YIELD_REQUEST", yield_payload=yield_p)
    yield_req = frame_to_agtp_request(yield_frame)

    assert (
        fold_req.method,
        agtp_request_to_frame(fold_req).frame_type,
        yield_req.method,
        agtp_request_to_frame(yield_req).frame_type,
    ) == (
        "CONFIRM",
        "ACP_FOLD_REQUEST",
        "ESCALATE",
        "ACP_YIELD_REQUEST",
    )


def test_agtp_probe_and_preempt_request_roundtrip():
    probe_p = ProbePayload(
        agent_id="agent:test",
        model_id="gpt-5",
        context_window_total=100000,
        context_window_available=50000,
    )
    probe_frame = ProtocolFrame(frame_type="ACP_PROBE_REQUEST", probe_payload=probe_p)
    probe_req = frame_to_agtp_request(probe_frame)

    preempt_frame = ProtocolFrame(frame_type="ACP_PREEMPT_REQUEST")
    preempt_req = frame_to_agtp_request(preempt_frame)

    assert (
        probe_req.method,
        agtp_request_to_frame(probe_req).frame_type,
        preempt_req.method,
        agtp_request_to_frame(preempt_req).frame_type,
    ) == (
        "DISCOVER",
        "ACP_PROBE_REQUEST",
        "NOTIFY",
        "ACP_PREEMPT_REQUEST",
    )


def test_agtp_all_response_verbs_roundtrip():
    # Handoff response (202 Accepted)
    handoff_frame = ProtocolFrame(frame_type="ACP_HANDOFF_RESPONSE")
    handoff_resp = frame_to_agtp_response(handoff_frame)
    assert handoff_resp.status_code == 202
    assert agtp_response_to_frame(handoff_resp).frame_type == "ACP_HANDOFF_RESPONSE"

    # Probe response (200 with probe_payload)
    probe_p = ProbePayload(
        agent_id="agent:resp",
        model_id="gemini",
        context_window_total=64000,
        context_window_available=32000,
    )
    probe_frame = ProtocolFrame(frame_type="ACP_PROBE_RESPONSE", probe_payload=probe_p)
    probe_resp = frame_to_agtp_response(probe_frame)
    assert probe_resp.status_code == 200
    parsed_probe = agtp_response_to_frame(probe_resp)
    assert (parsed_probe.frame_type, parsed_probe.probe_payload.agent_id) == (
        "ACP_PROBE_RESPONSE",
        "agent:resp",
    )


def test_agtp_mapping_error_handling():
    # Unsupported frame types for request conversion
    invalid_frame = ProtocolFrame(frame_type="ACP_PROBE_RESPONSE")
    with pytest.raises(ValueError):
        frame_to_agtp_request(invalid_frame)

    # Missing payload when required
    empty_fold_frame = ProtocolFrame(frame_type="ACP_FOLD_REQUEST")
    with pytest.raises(ValueError):
        frame_to_agtp_request(empty_fold_frame)

    empty_yield_frame = ProtocolFrame(frame_type="ACP_YIELD_REQUEST")
    with pytest.raises(ValueError):
        frame_to_agtp_request(empty_yield_frame)

    empty_handoff_frame = ProtocolFrame(frame_type="ACP_HANDOFF_REQUEST")
    with pytest.raises(ValueError):
        frame_to_agtp_request(empty_handoff_frame)

    # Unsupported AGTP response status code
    with pytest.raises(ValueError):
        agtp_response_to_frame(AGTPResponse(status_code=500, reason_phrase="Internal Server Error"))
