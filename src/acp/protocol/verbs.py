"""Protocol verbs, finite state machine, and lifecycle transitions for ACP.

Manages peer compatibility evaluation, execution leases, budget monitoring,
structured fold returns, and capability cliff escalations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final

from acp.protocol.models import (
    BudgetLeash,
    EpistemicEnvelope,
    FoldPayload,
    ProbePayload,
    YieldPayload,
)

DEFAULT_MIN_AX_SCORE: Final[float] = 0.75


class ACPState(StrEnum):
    """ACP lifecycle session states."""

    IDLE = "IDLE"
    PROBING = "PROBING"
    PEER_CERTIFIED = "PEER_CERTIFIED"
    EXECUTING = "EXECUTING"
    SUSPENDED = "SUSPENDED"
    FOLDED = "FOLDED"
    YIELDED = "YIELDED"
    PREEMPTED = "PREEMPTED"


class ACPProtocolError(Exception):
    """Base exception for ACP protocol violations."""


class ACPLeashExhaustedError(ACPProtocolError):
    """Raised when an execution breaches its budget leash."""


class ACPCapabilityCliffError(ACPProtocolError):
    """Raised when an agent encounters an insurmountable capability ceiling."""


class ACPInvalidStateTransitionError(ACPProtocolError):
    """Raised when an illegal FSM state transition is requested."""


_VALID_TRANSITIONS: Final[dict[ACPState, frozenset[ACPState]]] = {
    ACPState.IDLE: frozenset({ACPState.PROBING, ACPState.EXECUTING}),
    ACPState.PROBING: frozenset({ACPState.PEER_CERTIFIED, ACPState.IDLE}),
    ACPState.PEER_CERTIFIED: frozenset({ACPState.EXECUTING, ACPState.IDLE}),
    ACPState.EXECUTING: frozenset(
        {
            ACPState.SUSPENDED,
            ACPState.FOLDED,
            ACPState.YIELDED,
            ACPState.PREEMPTED,
        }
    ),
    ACPState.SUSPENDED: frozenset({ACPState.EXECUTING, ACPState.PREEMPTED}),
    ACPState.FOLDED: frozenset(),
    ACPState.YIELDED: frozenset(),
    ACPState.PREEMPTED: frozenset(),
}


def evaluate_peer_compatibility(
    probe: ProbePayload,
    required_tokens: int = 1000,
    min_ax_score: float = DEFAULT_MIN_AX_SCORE,
) -> tuple[bool, str]:
    """Determine if a peer agent meets capacity, AX score, and headroom invariants."""
    if probe.ax_score < min_ax_score:
        return (
            False,
            f"Peer AX score {probe.ax_score:.2f} is below minimum required {min_ax_score:.2f}.",
        )
    if probe.context_window_available < required_tokens:
        return (
            False,
            f"Peer available context ({probe.context_window_available}) is below required {required_tokens}.",
        )
    return (True, "Peer certified compatible.")


class ACPSession:
    """Manages an active ACP delegation lifecycle and enforces budget constraints."""

    def __init__(self, envelope: EpistemicEnvelope) -> None:
        self.envelope: EpistemicEnvelope = envelope
        self.state: ACPState = ACPState.IDLE
        self.tokens_consumed: int = 0
        self.cost_accumulated_usd: float = 0.0
        self.tool_invocations: int = 0
        self.start_time: datetime = datetime.now(UTC)

    def transition_to(self, new_state: ACPState) -> None:
        """Advance the session FSM to a new state if valid."""
        allowed = _VALID_TRANSITIONS.get(self.state, frozenset())
        if new_state not in allowed:
            raise ACPInvalidStateTransitionError(f"Cannot transition from {self.state} to {new_state}.")
        self.state = new_state

    def record_usage(self, tokens: int = 0, cost_usd: float = 0.0, tools_called: int = 0) -> None:
        """Account for consumed resources and assert leash compliance."""
        leash: BudgetLeash = self.envelope.budget_leash
        self.tokens_consumed += tokens
        self.cost_accumulated_usd += cost_usd
        self.tool_invocations += tools_called

        self._check_budget_bounds(leash)

    def _check_budget_bounds(self, leash: BudgetLeash) -> None:
        """Enforce strict bounding checks against budget leashes."""
        if self.tokens_consumed > leash.token_limit:
            raise ACPLeashExhaustedError(
                f"Token limit breached: consumed {self.tokens_consumed} > max {leash.token_limit}."
            )
        if self.cost_accumulated_usd > leash.max_cost_usd:
            raise ACPLeashExhaustedError(
                f"Cost cap breached: accumulated ${self.cost_accumulated_usd:.3f} > max ${leash.max_cost_usd:.3f}."
            )
        if self.tool_invocations > leash.max_tool_invocations:
            raise ACPLeashExhaustedError(
                f"Tool invocation limit breached: {self.tool_invocations} > max {leash.max_tool_invocations}."
            )

    def fold(
        self,
        patch_diff: str,
        certified_invariants: list[str],
    ) -> FoldPayload:
        """Fold completed work into a structured epistemic response."""
        self.transition_to(ACPState.FOLDED)
        return FoldPayload(
            status="SUCCESS",
            patch_diff=patch_diff,
            invariants_certified=certified_invariants,
            tokens_spent=self.tokens_consumed,
            cost_usd=round(self.cost_accumulated_usd, 4),
        )

    def yield_cliff(
        self,
        reason: str,
        cliff_category: str,
        counterexample: str | None = None,
    ) -> YieldPayload:
        """Escalate execution due to an insurmountable capability barrier."""
        self.transition_to(ACPState.YIELDED)
        return YieldPayload(
            reason=reason,
            cliff_category=cliff_category,
            unresolvable_counterexample=counterexample,
        )

    def suspend(self) -> dict[str, Any]:
        """Serialize current in-flight session into a checkpoint payload."""
        self.transition_to(ACPState.SUSPENDED)
        return {
            "envelope": self.envelope.model_dump(mode="json"),
            "tokens_consumed": self.tokens_consumed,
            "cost_accumulated_usd": self.cost_accumulated_usd,
            "tool_invocations": self.tool_invocations,
            "suspended_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def resume(cls, checkpoint: dict[str, Any]) -> ACPSession:
        """Reconstruct an active session from a suspended checkpoint."""
        envelope = EpistemicEnvelope.model_validate(checkpoint["envelope"])
        session = cls(envelope)
        session.tokens_consumed = checkpoint["tokens_consumed"]
        session.cost_accumulated_usd = checkpoint["cost_accumulated_usd"]
        session.tool_invocations = checkpoint["tool_invocations"]
        session.state = ACPState.SUSPENDED
        session.transition_to(ACPState.EXECUTING)
        return session
