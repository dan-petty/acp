"""Orchestrator agent for the ACP dual-agent demonstration exhibit."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from acp.protocol.crypto import generate_keypair, sign_delegation
from acp.protocol.models import (
    ACP_VERSION,
    BudgetLeash,
    EpistemicEnvelope,
    InvariantContract,
    ProtocolFrame,
    ReasoningLedgerEntry,
    Telos,
    WorkspaceContext,
)
from acp.protocol.transport import AGTPTransport


class Orchestrator:
    """Supervisory orchestrator synthesizing epistemic envelopes and delegating tasks."""

    def __init__(self) -> None:
        self.priv_seed_hex, self.pub_key_hex = generate_keypair()

    def build_envelope(self) -> EpistemicEnvelope:
        """Construct a validated epistemic envelope with anti-amnesia reasoning ledger."""
        delegation = sign_delegation(
            private_seed_hex=self.priv_seed_hex,
            issuer="user:dan@example.com",
            subject="agent:orchestrator",
            capabilities=["repo:read", "repo:write", "test:run"],
            attenuated_delegate="agent:worker",
        )

        return EpistemicEnvelope(
            acp_version=ACP_VERSION,
            envelope_id=str(uuid4()),
            traceparent=f"00-{uuid4().hex}-{uuid4().hex[:16]}-01",
            delegation_chain=delegation,
            budget_leash=BudgetLeash(
                token_limit=4000,
                max_cost_usd=0.05,
                max_tool_invocations=5,
                max_retry_depth=2,
            ),
            telos=Telos(
                goal="Refactor procedural router to table-driven dispatch",
                exit_criteria=["pytest tests/test_router.py passes", "cyclomatic complexity M <= 4"],
            ),
            invariant_contract=InvariantContract(
                positive_invariants=["100% test pass", "deterministic routing"],
                negative_constraints=["no unconstrained kwargs", "no regex backtracking"],
            ),
            workspace_context=WorkspaceContext(
                repository="dan-petty/acp",
                commit_base="88d3063c685252f4e4a79ecfb92f1b0e890e698f",
                working_patch="diff --git a/router.py ...",
                active_symbols=["router::dispatch"],
            ),
            compacted_reasoning_ledger=[
                ReasoningLedgerEntry(
                    hypotheses_evaluated=1,
                    falsified=["Dynamic regex compiler caused ReDoS vulnerability SEC-009"],
                    active_approach="Frozen table dictionary dispatch with pure predicate matching",
                )
            ],
        )

    async def delegate_task(self, socket_path: Path) -> ProtocolFrame:
        """Connect to sandboxed worker over UDS and transmit AGTP DELEGATE frame."""
        envelope = self.build_envelope()
        transport = await AGTPTransport.connect_unix(str(socket_path), target_uri="/v1/tasks/refactor")
        try:
            handoff_frame = ProtocolFrame(frame_type="ACP_HANDOFF_REQUEST", envelope=envelope)
            await transport.send_frame(handoff_frame)
            return await transport.receive_frame()
        finally:
            await transport.close()
