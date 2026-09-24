"""End-to-end tests for the ACP dual-agent sandbox exhibit."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from acp.protocol.models import ProtocolFrame
from acp.protocol.verbs import ACPLeashExhaustedError
from examples.dual_agent_sandbox.orchestrator import Orchestrator
from examples.dual_agent_sandbox.worker import SandboxedWorker, run_worker_service


@pytest.mark.asyncio
async def test_dual_agent_clean_delegation():
    """Verify end-to-end delegation and fold over Unix Domain Socket."""
    orchestrator = Orchestrator()
    with tempfile.TemporaryDirectory() as tmp_dir:
        socket_path = Path(tmp_dir) / "test_acp.sock"
        ready = asyncio.Event()

        worker_task = asyncio.create_task(
            run_worker_service(
                socket_path=socket_path,
                issuer_public_key_hex=orchestrator.pub_key_hex,
                ready_event=ready,
                mode="normal",
            )
        )
        await ready.wait()

        response = await orchestrator.delegate_task(socket_path)
        await worker_task

        fold = response.fold_payload
        assert fold is not None
        assert (
            response.frame_type,
            fold.status,
            fold.tokens_spent <= 4000,
            "M <= 4" in fold.invariants_certified,
        ) == (
            "ACP_FOLD_RESPONSE",
            "SUCCESS",
            True,
            True,
        )


@pytest.mark.asyncio
async def test_dual_agent_capability_cliff():
    """Verify capability cliff detection and CEGIS yield over UDS."""
    orchestrator = Orchestrator()
    with tempfile.TemporaryDirectory() as tmp_dir:
        socket_path = Path(tmp_dir) / "test_acp_cliff.sock"
        ready = asyncio.Event()

        worker_task = asyncio.create_task(
            run_worker_service(
                socket_path=socket_path,
                issuer_public_key_hex=orchestrator.pub_key_hex,
                ready_event=ready,
                mode="cliff",
            )
        )
        await ready.wait()

        response = await orchestrator.delegate_task(socket_path)
        await worker_task

        yield_payload = response.yield_payload
        assert yield_payload is not None
        assert (
            response.frame_type,
            yield_payload.cliff_category,
            "recursion" in yield_payload.reason,
        ) == (
            "ACP_YIELD_RESPONSE",
            "CAPABILITY_CEILING",
            True,
        )


def test_dual_agent_budget_leash_breach():
    """Verify defensive abort on token budget leash breach."""
    orchestrator = Orchestrator()
    envelope = orchestrator.build_envelope()
    worker = SandboxedWorker(issuer_public_key_hex=orchestrator.pub_key_hex)
    frame = ProtocolFrame(frame_type="ACP_HANDOFF_REQUEST", envelope=envelope)

    with pytest.raises(ACPLeashExhaustedError) as exc_info:
        worker.process_envelope(frame, simulate_leash_breach=True)

    assert "Token limit breached" in str(exc_info.value)
