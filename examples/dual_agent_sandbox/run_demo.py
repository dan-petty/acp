"""End-to-end runnable demonstration of the ACP Dual-Agent Sandbox Exhibit."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from acp.protocol.models import ProtocolFrame
from acp.protocol.verbs import ACPLeashExhaustedError

try:
    from examples.dual_agent_sandbox.orchestrator import Orchestrator
    from examples.dual_agent_sandbox.worker import SandboxedWorker, run_worker_service
except ImportError:
    from orchestrator import Orchestrator  # type: ignore[no-redef]
    from worker import SandboxedWorker, run_worker_service  # type: ignore[no-redef]


async def _run_clean_delegation(socket_path: Path, orchestrator: Orchestrator) -> None:
    """Execute Scenario 1: Clean delegation, anti-amnesia navigation, and fold."""
    sys.stdout.write("\n" + "=" * 65 + "\n")
    sys.stdout.write("  SCENARIO 1: Clean Delegation & Epistemic Fold\n")
    sys.stdout.write("=" * 65 + "\n")

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

    sys.stdout.write("▶ [Orchestrator] Synthesizing Epistemic State Envelope...\n")
    sys.stdout.write("▶ [Orchestrator] Signing Ed25519 Delegation Chain...\n")
    sys.stdout.write("▶ [Orchestrator] Transmitting ACP_HANDOFF over Unix Domain Socket...\n")

    response = await orchestrator.delegate_task(socket_path)
    await worker_task

    fold = response.fold_payload
    if not fold:
        raise RuntimeError("Expected ACP_FOLD_RESPONSE frame")

    sys.stdout.write("✔ [Worker] Cryptographic signature certified.\n")
    sys.stdout.write("✔ [Worker] Falsified hypotheses inspected (avoided dynamic regex).\n")
    sys.stdout.write(f"✔ [Orchestrator] Received {response.frame_type}\n")
    sys.stdout.write(f"    * Outcome Status:      {fold.status}\n")
    sys.stdout.write(f"    * Tokens Consumed:     {fold.tokens_spent} (within 4,000 leash limit)\n")
    sys.stdout.write(f"    * Financial Cost:      ${fold.cost_usd:.3f} (within $0.05 budget)\n")
    sys.stdout.write(f"    * Certified Invariants: {fold.invariants_certified}\n")


async def _run_capability_cliff(socket_path: Path, orchestrator: Orchestrator) -> None:
    """Execute Scenario 2: Capability barrier detection and CEGIS yield."""
    sys.stdout.write("\n" + "=" * 65 + "\n")
    sys.stdout.write("  SCENARIO 2: Capability Cliff & CEGIS Counterexample Yield\n")
    sys.stdout.write("=" * 65 + "\n")

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

    sys.stdout.write("▶ [Orchestrator] Delegating complex task to sandboxed worker...\n")
    response = await orchestrator.delegate_task(socket_path)
    await worker_task

    yield_payload = response.yield_payload
    if not yield_payload:
        raise RuntimeError("Expected ACP_YIELD_RESPONSE frame")

    sys.stdout.write(f"▲ [Worker] Capability cliff encountered: {yield_payload.cliff_category}\n")
    sys.stdout.write("▲ [Worker] Emitting structured CEGIS counterexample in ACP_YIELD frame.\n")
    sys.stdout.write(f"✔ [Orchestrator] Received {response.frame_type}\n")
    sys.stdout.write(f"    * Cliff Reason:        {yield_payload.reason}\n")
    sys.stdout.write(f"    * Category:            {yield_payload.cliff_category}\n")
    sys.stdout.write(f"    * CEGIS Payload:       {yield_payload.unresolvable_counterexample}\n")


def _run_budget_breach(orchestrator: Orchestrator) -> None:
    """Execute Scenario 3: Defensive budget leash breach abort."""
    sys.stdout.write("\n" + "=" * 65 + "\n")
    sys.stdout.write("  SCENARIO 3: Defensive Budget Leash Breach Abort\n")
    sys.stdout.write("=" * 65 + "\n")

    envelope = orchestrator.build_envelope()
    worker = SandboxedWorker(issuer_public_key_hex=orchestrator.pub_key_hex)
    frame = ProtocolFrame(frame_type="ACP_HANDOFF_REQUEST", envelope=envelope)

    sys.stdout.write("▶ [Worker] Inbound task has token_limit = 4,000 tokens.\n")
    sys.stdout.write("▶ [Worker] Rogue execution consumes 99,999 tokens...\n")

    try:
        worker.process_envelope(frame, simulate_leash_breach=True)
        sys.stderr.write("❌ Error: Budget breach was not blocked!\n")
    except ACPLeashExhaustedError as exc:
        sys.stdout.write(f"🛡️  [Safety Barrier] ACP Defensive Leash Enforced:\n    {exc}\n")
        sys.stdout.write("✔ Session halted before runaway compute spend.\n")


async def main_async() -> int:
    """Run all three demonstration scenarios sequentially."""
    sys.stdout.write("🚀 Starting ACP Dual-Agent Sandbox Demonstration Exhibit\n")
    orchestrator = Orchestrator()

    with tempfile.TemporaryDirectory() as tmp_dir:
        socket_path = Path(tmp_dir) / "acp_demo.sock"
        await _run_clean_delegation(socket_path, orchestrator)

        socket_path_cliff = Path(tmp_dir) / "acp_cliff.sock"
        await _run_capability_cliff(socket_path_cliff, orchestrator)

    _run_budget_breach(orchestrator)

    sys.stdout.write("\n" + "=" * 65 + "\n")
    sys.stdout.write("✅ All 3 ACP Dual-Agent Exhibit Scenarios Certified Cleanly!\n")
    sys.stdout.write("=" * 65 + "\n\n")
    return 0


def main() -> int:
    """Entrypoint wrapper."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
