"""Sandboxed worker subagent for the ACP dual-agent demonstration exhibit."""

from __future__ import annotations

import asyncio
from pathlib import Path

from acp.protocol.crypto import verify_delegation
from acp.protocol.models import (
    CEGISCounterexample,
    EpistemicEnvelope,
    FoldPayload,
    ProtocolFrame,
    YieldPayload,
)
from acp.protocol.transport import AGTPTransport
from acp.protocol.verbs import ACPSession


def _verify_envelope_auth(envelope: EpistemicEnvelope, issuer_public_key_hex: str) -> None:
    """Verify cryptographic delegation chain on envelope if present."""
    if envelope.delegation_chain and not verify_delegation(envelope.delegation_chain, issuer_public_key_hex):
        raise PermissionError("Ed25519 cryptographic delegation verification failed!")


def _synthesize_cliff_yield(session: ACPSession) -> ProtocolFrame:
    """Synthesize structured capability cliff yield frame."""
    counterexample = CEGISCounterexample(
        input="dispatch('/legacy/endpoint')",
        expected="HTTP 200",
        failing_actual="HTTP 500",
        rationale="Unresolvable legacy recursion cycle in downstream subsystem",
    )
    yield_payload = YieldPayload(
        reason="Subsystem recursion exceeds local sandbox capability",
        cliff_category="CAPABILITY_CEILING",
        unresolvable_counterexample=counterexample.model_dump_json(),
    )
    session.transition_to("YIELDED")
    return ProtocolFrame(frame_type="ACP_YIELD_RESPONSE", yield_payload=yield_payload)


def _synthesize_normal_fold(session: ACPSession) -> ProtocolFrame:
    """Synthesize successful fold frame after refactoring under budget."""
    session.record_usage(tokens=1420, cost_usd=0.018, tools_called=2)
    fold_payload = FoldPayload(
        status="SUCCESS",
        patch_diff="diff --git a/router.py ...\n+TABLE_DISPATCH = {...}",
        invariants_certified=["M <= 4", "100% test pass"],
        tokens_spent=session.tokens_consumed,
        cost_usd=session.cost_accumulated_usd,
    )
    session.transition_to("FOLDED")
    return ProtocolFrame(frame_type="ACP_FOLD_RESPONSE", fold_payload=fold_payload)


class SandboxedWorker:
    """Simulated sandboxed subagent executing tasks under ACP governance."""

    def __init__(self, issuer_public_key_hex: str) -> None:
        self.issuer_public_key_hex = issuer_public_key_hex

    def process_envelope(
        self,
        frame: ProtocolFrame,
        simulate_cliff: bool = False,
        simulate_leash_breach: bool = False,
    ) -> ProtocolFrame:
        """Process an inbound ACP_HANDOFF frame and return a response frame."""
        envelope = frame.envelope
        if not envelope:
            raise ValueError("Inbound frame missing EpistemicEnvelope")

        _verify_envelope_auth(envelope, self.issuer_public_key_hex)

        session = ACPSession(envelope)
        session.transition_to("EXECUTING")

        if simulate_leash_breach:
            session.record_usage(tokens=99999, cost_usd=10.0, tools_called=50)

        if simulate_cliff:
            return _synthesize_cliff_yield(session)

        return _synthesize_normal_fold(session)


async def run_worker_service(
    socket_path: Path,
    issuer_public_key_hex: str,
    ready_event: asyncio.Event | None = None,
    mode: str = "normal",
) -> None:
    """Run worker daemon listening on a Unix domain socket for one session."""
    worker = SandboxedWorker(issuer_public_key_hex=issuer_public_key_hex)
    finished = asyncio.Event()

    async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        transport = AGTPTransport(reader, writer, is_client=False)
        try:
            frame = await transport.receive_frame()
            resp_frame = worker.process_envelope(
                frame,
                simulate_cliff=(mode == "cliff"),
                simulate_leash_breach=(mode == "breach"),
            )
            await transport.send_frame(resp_frame)
        finally:
            await transport.close()
            finished.set()

    server = await asyncio.start_unix_server(_handle_client, path=str(socket_path))
    if ready_event:
        ready_event.set()

    try:
        await finished.wait()
    finally:
        server.close()
        await server.wait_closed()
