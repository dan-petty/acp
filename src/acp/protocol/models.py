"""Core data models and schemas for the Agentic Communication Protocol (ACP).

Implements Pydantic v2 models for Epistemic State Envelopes (ESE), budget
leashes, invariant contracts, CEGIS counterexamples, and protocol frames.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Final
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

ACP_VERSION: Final[str] = "1.0.0"
_TRACEPARENT_PATTERN: Final[re.Pattern[str]] = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


class BaseACPModel(BaseModel):
    """Base model enforcing strict negative constraints and immutability."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )


class DelegationChain(BaseACPModel):
    """Cryptographic authority and capability delegation chain."""

    issuer: str = Field(..., max_length=256, description="Originating principal.")
    subject: str = Field(..., max_length=256, description="Target delegate agent.")
    attenuated_delegate: str | None = Field(None, max_length=256, description="Downstream subagent slot.")
    capabilities: list[str] = Field(default_factory=list, description="Permitted capability scopes.")
    proof: str = Field(..., min_length=16, description="Cryptographic proof token.")


class BudgetLeash(BaseACPModel):
    """Resource bounds and execution limits."""

    token_limit: int = Field(..., ge=1, description="Hard token expenditure ceiling.")
    max_cost_usd: float = Field(..., ge=0.0, description="Financial expenditure cap in USD.")
    max_tool_invocations: int = Field(default=10, ge=1, description="Maximum tool execution count.")
    deadline_utc: datetime | None = Field(None, description="Hard wall-clock UTC execution deadline.")
    max_retry_depth: int = Field(default=3, ge=0, le=10, description="Maximum retry count.")


class Telos(BaseACPModel):
    """Goal and deterministic completion criteria."""

    goal: str = Field(..., min_length=3, description="Target objective or task specification.")
    exit_criteria: list[str] = Field(..., min_length=1, description="Falsifiable acceptance assertions.")


class CEGISCounterexample(BaseACPModel):
    """Formal counterexample discovered during verification."""

    input: str = Field(..., description="Failing stimulus or AST invocation input.")
    expected: str = Field(..., description="Expected specification behavior.")
    failing_actual: str = Field(..., description="Actual observed failing response or exception.")
    rationale: str | None = Field(None, description="Hypothesis explaining mechanism of failure.")


class InvariantContract(BaseACPModel):
    """Positive invariants and negative constraints defining the problem space."""

    positive_invariants: list[str] = Field(default_factory=list, description="Required passing invariants.")
    negative_constraints: list[str] = Field(default_factory=list, description="Forbidden failure domains.")
    cegis_counterexamples: list[CEGISCounterexample] = Field(
        default_factory=list, description="Accumulated failing counterexamples."
    )


class WorkspaceContext(BaseACPModel):
    """Git workspace, commit baseline, and AST symbol references."""

    repository: str = Field(..., description="Repository slug (e.g. 'dan-petty/acp').")
    commit_base: str = Field(..., description="Baseline git commit SHA.")
    working_patch: str | None = Field(None, description="Unified patch diff of in-flight changes.")
    active_symbols: list[str] = Field(default_factory=list, description="Target qualified AST symbols.")


class ReasoningLedgerEntry(BaseACPModel):
    """Compacted record of evaluated, falsified, and active hypotheses."""

    hypotheses_evaluated: int = Field(default=1, ge=1, description="Count of hypotheses tested.")
    falsified: list[str] = Field(default_factory=list, description="List of falsified approaches.")
    active_approach: str = Field(..., max_length=1024, description="Active working strategy.")


class EpistemicEnvelope(BaseACPModel):
    """The central ACP Epistemic State Envelope (ESE)."""

    acp_version: str = Field(default=ACP_VERSION, description="Protocol version.")
    envelope_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique envelope UUID.")
    traceparent: str = Field(..., description="W3C Distributed Traceparent context string.")
    delegation_chain: DelegationChain | None = Field(None, description="Authority delegation proof.")
    budget_leash: BudgetLeash = Field(..., description="Resource bounding leash.")
    telos: Telos = Field(..., description="Task intent and exit criteria.")
    invariant_contract: InvariantContract = Field(..., description="Invariant gates and counterexamples.")
    workspace_context: WorkspaceContext = Field(..., description="Workspace code and AST context.")
    compacted_reasoning_ledger: list[ReasoningLedgerEntry] = Field(
        default_factory=list, description="Compacted decision memory."
    )

    @field_validator("traceparent")
    @classmethod
    def _validate_traceparent(cls, value: str) -> str:
        """Validate W3C traceparent formatting."""
        if not _TRACEPARENT_PATTERN.match(value):
            raise ValueError(
                f"Invalid W3C traceparent '{value}'. Expected format '00-<32hex>-<16hex>-<2hex>'."
            )
        return value


class ProbePayload(BaseACPModel):
    """Agent Experience (AX) peer probe discovery payload."""

    agent_id: str = Field(..., max_length=256)
    model_id: str = Field(..., max_length=256)
    context_window_total: int = Field(..., ge=1000)
    context_window_available: int = Field(..., ge=0)
    supported_isolation: list[str] = Field(default_factory=list)
    ax_score: float = Field(default=1.0, ge=0.0, le=1.0)
    available_tools: list[str] = Field(default_factory=list)


class FoldPayload(BaseACPModel):
    """Structured epistemic result returned on task completion."""

    status: str = Field(..., pattern="^(SUCCESS|FAILED|ESCALATED)$")
    patch_diff: str = Field(default="", description="Resulting unified git diff.")
    invariants_certified: list[str] = Field(default_factory=list)
    tokens_spent: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    discovered_counterexamples: list[CEGISCounterexample] = Field(default_factory=list)


class YieldPayload(BaseACPModel):
    """Structured escalation payload emitted upon capability boundary collision."""

    reason: str = Field(..., max_length=1024)
    cliff_category: str = Field(
        ...,
        pattern="^(CAPABILITY_CEILING|BUDGET_EXHAUSTION|CIRCULAR_DEPENDENCY|SECURITY_VIOLATION)$",
    )
    unresolvable_counterexample: str | None = Field(None, max_length=4096)


class ProtocolFrame(BaseACPModel):
    """Wire envelope framing all ACP lifecycle messages."""

    frame_type: str = Field(
        ...,
        pattern="^(ACP_PROBE_REQUEST|ACP_PROBE_RESPONSE|ACP_HANDOFF_REQUEST|ACP_HANDOFF_RESPONSE|ACP_FOLD_REQUEST|ACP_FOLD_RESPONSE|ACP_YIELD_REQUEST|ACP_YIELD_RESPONSE|ACP_PREEMPT_REQUEST)$",
    )
    frame_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    envelope: EpistemicEnvelope | None = None
    probe_payload: ProbePayload | None = None
    fold_payload: FoldPayload | None = None
    yield_payload: YieldPayload | None = None
