"""Unit tests for ACP FSM lifecycle transitions and budget leash enforcement."""

from __future__ import annotations

import pytest

from acp.protocol.models import (
    ACP_VERSION,
    BudgetLeash,
    EpistemicEnvelope,
    InvariantContract,
    ProbePayload,
    Telos,
    WorkspaceContext,
)
from acp.protocol.verbs import (
    ACPInvalidStateTransitionError,
    ACPLeashExhaustedError,
    ACPSession,
    ACPState,
    evaluate_peer_compatibility,
)


def _build_test_envelope(
    token_limit: int = 1000,
    max_cost_usd: float = 0.50,
    max_tool_invocations: int = 5,
) -> EpistemicEnvelope:
    """Helper creating minimal test envelope."""
    return EpistemicEnvelope(
        acp_version=ACP_VERSION,
        envelope_id="fsm-test-01",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        budget_leash=BudgetLeash(
            token_limit=token_limit,
            max_cost_usd=max_cost_usd,
            max_tool_invocations=max_tool_invocations,
        ),
        telos=Telos(goal="FSM test", exit_criteria=["assert True"]),
        invariant_contract=InvariantContract(),
        workspace_context=WorkspaceContext(repository="dan-petty/acp", commit_base="abcdef123"),
    )


def test_session_state_transitions_and_fold():
    envelope = _build_test_envelope()
    session = ACPSession(envelope)

    assert session.state == ACPState.IDLE
    session.transition_to(ACPState.EXECUTING)
    assert session.state == ACPState.EXECUTING

    fold_payload = session.fold(
        patch_diff="diff --git a/a.py b/a.py",
        certified_invariants=["invariants_pass"],
    )
    assert (session.state, fold_payload.status, fold_payload.invariants_certified) == (
        ACPState.FOLDED,
        "SUCCESS",
        ["invariants_pass"],
    )


def test_session_illegal_state_transition():
    envelope = _build_test_envelope()
    session = ACPSession(envelope)

    with pytest.raises(ACPInvalidStateTransitionError):
        session.transition_to(ACPState.FOLDED)


def test_token_budget_exhaustion():
    envelope = _build_test_envelope(token_limit=500)
    session = ACPSession(envelope)
    session.transition_to(ACPState.EXECUTING)

    with pytest.raises(ACPLeashExhaustedError) as exc_info:
        session.record_usage(tokens=600)
    assert "Token limit breached" in str(exc_info.value)


def test_cost_budget_exhaustion():
    envelope = _build_test_envelope(max_cost_usd=0.20)
    session = ACPSession(envelope)
    session.transition_to(ACPState.EXECUTING)

    with pytest.raises(ACPLeashExhaustedError) as exc_info:
        session.record_usage(cost_usd=0.25)
    assert "Cost cap breached" in str(exc_info.value)


def test_tool_invocations_exhaustion():
    envelope = _build_test_envelope(max_tool_invocations=2)
    session = ACPSession(envelope)
    session.transition_to(ACPState.EXECUTING)

    with pytest.raises(ACPLeashExhaustedError) as exc_info:
        session.record_usage(tools_called=3)
    assert "Tool invocation limit breached" in str(exc_info.value)


def test_suspend_and_resume_checkpoint():
    envelope = _build_test_envelope()
    session = ACPSession(envelope)
    session.transition_to(ACPState.EXECUTING)
    session.record_usage(tokens=250, cost_usd=0.05, tools_called=2)

    checkpoint = session.suspend()
    assert (session.state, checkpoint["tokens_consumed"]) == (ACPState.SUSPENDED, 250)

    resumed = ACPSession.resume(checkpoint)
    assert (
        resumed.state,
        resumed.tokens_consumed,
        resumed.envelope.envelope_id,
    ) == (
        ACPState.EXECUTING,
        250,
        "fsm-test-01",
    )


def test_evaluate_peer_compatibility():
    probe_pass = ProbePayload(
        agent_id="agent-01",
        model_id="gemini-2.5-pro",
        context_window_total=128000,
        context_window_available=64000,
        ax_score=0.92,
    )
    probe_fail_ax = ProbePayload(
        agent_id="agent-02",
        model_id="legacy-model",
        context_window_total=32000,
        context_window_available=16000,
        ax_score=0.55,
    )

    result_pass = evaluate_peer_compatibility(probe_pass, required_tokens=1000)
    result_fail = evaluate_peer_compatibility(probe_fail_ax, min_ax_score=0.75)

    assert (result_pass[0], result_fail[0]) == (True, False)
