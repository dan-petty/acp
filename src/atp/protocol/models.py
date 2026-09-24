"""Core data models and schemas for the Agentic Transfer Protocol (ATP).

Implements Pydantic v2 models for Epistemic State Envelopes (ESE), budget
leashes, invariant contracts, CEGIS counterexamples, and protocol frames.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Final
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

ATP_VERSION: Final[str] = "1.0.0"
_TRACEPARENT_PATTERN: Final[re.Pattern[str]] = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


class BaseATPModel(BaseModel):
    """Base model enforcing strict negative constraints and immutability."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )


class DelegationChain(BaseATPModel):
    """Cryptographic authority and capability delegation chain."""

    issuer: str = Field(..., max_length=256, description="Originating principal.")
    subject: str = Field(..., max_length=256, description="Target delegate agent.")
    attenuated_delegate: str | None = Field(None, max_length=256, description="Downstream subagent slot.")
    capabilities: list[str] = Field(default_factory=list, description="Permitted capability scopes.")
    proof: str = Field(..., min_length=16, description="Cryptographic proof token.")


class BudgetLeash(BaseATPModel):
    """Multidimensional resource and execution constraints."""

    token_limit: int = Field(..., ge=100, description="Max token allocation.")
    max_cost_usd: float = Field(..., ge=0.0, description="Hard spend ceiling in USD.")
    max_tool_invocations: int = Field(..., ge=1, description="Max permitted tool calls.")
    deadline_utc: datetime | None = Field(None, description="ISO 8601 execution deadline.")
    max_retry_depth: int = Field(default=3, ge=0, description="Max self-correction iterations.")


class Telos(BaseATPModel):
    """Goal intent and verifiable exit criteria."""

    goal: str = Field(..., min_length=5, max_length=2048, description="Target objective.")
    exit_criteria: list[str] = Field(..., min_length=1, description="Falsifiable exit assertions.")


class CEGISCounterexample(BaseATPModel):
    """Concrete failing counterexample guiding inductive synthesis."""

    input: str = Field(..., max_length=4096, description="Failing invocation input.")
    expected: str = Field(..., max_length=4096, description="Expected invariant output.")
    failing_actual: str = Field(..., max_length=4096, description="Observed faulty behavior.")
    rationale: str | None = Field(None, max_length=1024, description="Failure analysis.")


class InvariantContract(BaseATPModel):
    """Positive invariants, negative constraints, and CEGIS counterexamples."""

    positive_invariants: list[str] = Field(default_factory=list, description="Required passing invariants.")
    negative_constraints: list[str] = Field(default_factory=list, description="Forbidden failure domains.")
    cegis_counterexamples: list[CEGISCounterexample] = Field(
        default_factory=list, description="Accumulated negative counterexamples."
    )


class WorkspaceContext(BaseATPModel):
    """Git workspace state and target symbol anchors."""

    repository: str = Field(..., max_length=256, description="Target repository.")
    commit_base: str = Field(..., min_length=7, max_length=64, description="Base Git commit SHA.")
    working_patch: str | None = Field(None, description="Unified patch diff of in-flight changes.")
    active_symbols: list[str] = Field(default_factory=list, description="Target qualified AST symbols.")


class ReasoningLedgerEntry(BaseATPModel):
    """Compacted record of evaluated and falsified problem-solving approaches."""

    hypotheses_evaluated: int = Field(..., ge=0, description="Total hypotheses tested.")
    falsified: list[str] = Field(default_factory=list, description="Falsified strategies.")
    active_approach: str = Field(..., max_length=1024, description="Active working strategy.")


class EpistemicEnvelope(BaseATPModel):
    """The central ATP Epistemic State Envelope (ESE)."""

    atp_version: str = Field(default=ATP_VERSION, description="Protocol version.")
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


class ProbePayload(BaseATPModel):
    """Agent Experience (AX) peer probe discovery payload."""

    agent_id: str = Field(..., max_length=256)
    model_id: str = Field(..., max_length=256)
    context_window_total: int = Field(..., ge=1000)
    context_window_available: int = Field(..., ge=0)
    supported_isolation: list[str] = Field(default_factory=list)
    ax_score: float = Field(default=1.0, ge=0.0, le=1.0)
    available_tools: list[str] = Field(default_factory=list)


class FoldPayload(BaseATPModel):
    """Structured epistemic result returned on task completion."""

    status: str = Field(..., pattern="^(SUCCESS|FAILED|ESCALATED)$")
    patch_diff: str = Field(default="", description="Resulting unified git diff.")
    invariants_certified: list[str] = Field(default_factory=list)
    tokens_spent: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    discovered_counterexamples: list[CEGISCounterexample] = Field(default_factory=list)


class YieldPayload(BaseATPModel):
    """Structured escalation payload emitted upon capability boundary collision."""

    reason: str = Field(..., max_length=1024)
    cliff_category: str = Field(
        ...,
        pattern="^(CAPABILITY_CEILING|BUDGET_EXHAUSTION|CIRCULAR_DEPENDENCY|SECURITY_VIOLATION)$",
    )
    unresolvable_counterexample: str | None = Field(None, max_length=4096)


class ProtocolFrame(BaseATPModel):
    """Wire envelope framing all ATP lifecycle messages."""

    frame_type: str = Field(
        ...,
        pattern="^(ATP_PROBE_REQUEST|ATP_PROBE_RESPONSE|ATP_HANDOFF_REQUEST|ATP_HANDOFF_RESPONSE|ATP_FOLD_REQUEST|ATP_FOLD_RESPONSE|ATP_YIELD_REQUEST|ATP_YIELD_RESPONSE|ATP_PREEMPT_REQUEST)$",
    )
    frame_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    envelope: EpistemicEnvelope | None = None
    probe_payload: ProbePayload | None = None
    fold_payload: FoldPayload | None = None
    yield_payload: YieldPayload | None = None
