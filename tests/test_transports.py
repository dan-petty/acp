"""Unit tests for ACP async transport layers and length-prefixed framing."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from acp.protocol.models import ProbePayload, ProtocolFrame
from acp.protocol.transport import (
    FrameSerializer,
    MemoryTransport,
    UnixSocketTransport,
)


@pytest.mark.asyncio
async def test_frame_serializer_roundtrip():
    frame = ProtocolFrame(
        frame_type="ACP_PROBE_REQUEST",
        probe_payload=ProbePayload(
            agent_id="test-agent",
            model_id="test-model",
            context_window_total=32000,
            context_window_available=16000,
            ax_score=0.88,
        ),
    )
    encoded = FrameSerializer.encode_frame(frame)
    reader = asyncio.StreamReader()
    reader.feed_data(encoded)
    reader.feed_eof()

    decoded = await FrameSerializer.read_frame(reader)
    assert (
        decoded.frame_type,
        decoded.probe_payload.agent_id,
        decoded.probe_payload.ax_score,
    ) == (
        "ACP_PROBE_REQUEST",
        "test-agent",
        0.88,
    )


@pytest.mark.asyncio
async def test_memory_transport_duplex_communication():
    client, server = MemoryTransport.create_pair()

    request_frame = ProtocolFrame(frame_type="ACP_PREEMPT_REQUEST")
    await client.send_frame(request_frame)

    received_by_server = await server.receive_frame()
    assert received_by_server.frame_type == "ACP_PREEMPT_REQUEST"

    response_frame = ProtocolFrame(frame_type="ACP_FOLD_RESPONSE")
    await server.send_frame(response_frame)

    received_by_client = await client.receive_frame()
    assert received_by_client.frame_type == "ACP_FOLD_RESPONSE"

    await client.close()
    await server.close()


@pytest.mark.asyncio
async def test_unix_socket_transport_communication():
    with tempfile.TemporaryDirectory() as tmp_dir:
        sock_path = str(Path(tmp_dir) / "acp_test.sock")
        server_received: list[ProtocolFrame] = []

        async def _handle_client(reader, writer):
            transport = UnixSocketTransport(reader, writer)
            frame = await transport.receive_frame()
            server_received.append(frame)
            ack = ProtocolFrame(frame_type="ACP_HANDOFF_RESPONSE")
            await transport.send_frame(ack)
            await transport.close()

        server = await asyncio.start_unix_server(_handle_client, path=sock_path)

        client_transport = await UnixSocketTransport.connect(sock_path)
        send_frame = ProtocolFrame(frame_type="ACP_HANDOFF_REQUEST")
        await client_transport.send_frame(send_frame)

        ack_frame = await client_transport.receive_frame()
        await client_transport.close()

        server.close()
        await server.wait_closed()

        assert (
            len(server_received),
            server_received[0].frame_type,
            ack_frame.frame_type,
        ) == (
            1,
            "ACP_HANDOFF_REQUEST",
            "ACP_HANDOFF_RESPONSE",
        )
