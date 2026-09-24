"""Unit tests for ATP Epistemic State Envelope schema and model validation."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from atp.protocol.models import (
    ATP_VERSION,
    BudgetLeash,
    CEGISCounterexample,
    DelegationChain,
    EpistemicEnvelope,
    InvariantContract,
    ReasoningLedgerEntry,
    Telos,
    WorkspaceContext,
)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "spec" / "schemas" / "v1" / "envelope.json"


def _make_sample_envelope() -> EpistemicEnvelope:
    """Construct a clean, valid sample EpistemicEnvelope."""
    return EpistemicEnvelope(
        atp_version=ATP_VERSION,
        envelope_id="test-env-001",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        delegation_chain=DelegationChain(
            issuer="user:dan@example.com",
            subject="agent:orchestrator",
            capabilities=["repo:read", "repo:write"],
            proof="ucan:eyJhbGciOiJFUzI1NksInR5cCI6IkpXVCJ9.eyJpc3MiOiJkaWQ...",
        ),
        budget_leash=BudgetLeash(
            token_limit=16000,
            max_cost_usd=0.25,
            max_tool_invocations=10,
            max_retry_depth=3,
        ),
        telos=Telos(
            goal="Refactor dispatch table",
            exit_criteria=["pytest tests/ passes", "M <= 4"],
        ),
        invariant_contract=InvariantContract(
            positive_invariants=["clean_tests"],
            negative_constraints=["no_kwargs"],
            cegis_counterexamples=[
                CEGISCounterexample(
                    input="dispatch('invalid')",
                    expected="KeyError",
                    failing_actual="None",
                    rationale="Missing default handler",
                )
            ],
        ),
        workspace_context=WorkspaceContext(
            repository="dan-petty/atp",
            commit_base="88d3063c685252f4e4a79ecfb92f1b0e890e698f",
            working_patch="diff --git a/test.py b/test.py",
            active_symbols=["atp.protocol.models::EpistemicEnvelope"],
        ),
        compacted_reasoning_ledger=[
            ReasoningLedgerEntry(
                hypotheses_evaluated=2,
                falsified=["procedural dispatch"],
                active_approach="dictionary dispatch",
            )
        ],
    )


def test_valid_envelope_roundtrip_and_json_schema():
    envelope = _make_sample_envelope()
    data = json.loads(envelope.model_dump_json())

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=schema)

    reconstructed = EpistemicEnvelope.model_validate(data)
    assert (
        reconstructed.envelope_id,
        reconstructed.telos.goal,
        len(reconstructed.invariant_contract.cegis_counterexamples),
    ) == (
        "test-env-001",
        "Refactor dispatch table",
        1,
    )


def test_invalid_traceparent_rejected():
    with pytest.raises(ValidationError) as exc_info:
        EpistemicEnvelope(
            traceparent="invalid-traceparent",
            budget_leash=BudgetLeash(token_limit=1000, max_cost_usd=0.1, max_tool_invocations=5),
            telos=Telos(goal="Test goal", exit_criteria=["exit"]),
            invariant_contract=InvariantContract(),
            workspace_context=WorkspaceContext(repository="dan-petty/atp", commit_base="1234567"),
        )
    assert "Invalid W3C traceparent" in str(exc_info.value)


def test_permissive_attributes_strictly_forbidden():
    data = json.loads(_make_sample_envelope().model_dump_json())
    data["hallucinated_field"] = "dangerous"

    with pytest.raises(ValidationError):
        EpistemicEnvelope.model_validate(data)
