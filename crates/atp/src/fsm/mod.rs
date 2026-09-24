//! Compile-time type-state finite state machine for ATP execution sessions.

use std::marker::PhantomData;

use serde::{Deserialize, Serialize};

use crate::error::{AtpError, AtpResult};
use crate::models::{EpistemicEnvelope, FoldPayload, ProbePayload, YieldPayload};

/// Default minimum acceptable Agent Experience (AX) score for peer delegation.
pub const DEFAULT_MIN_AX_SCORE: f64 = 0.75;

/// Type-state marker indicating an idle, unstarted session.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Idle;

/// Type-state marker indicating that active peer discovery / capability probing is in progress.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Probing;

/// Type-state marker indicating peer certification has passed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PeerCertified;

/// Type-state marker indicating an actively running cognitive session.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Executing;

/// Type-state marker indicating a paused execution preserved via checkpoint.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Suspended;

/// Type-state marker indicating completed execution folded into a result.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Folded;

/// Type-state marker indicating capability cliff escalation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Yielded;

/// Type-state marker indicating out-of-band supervisor abort.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Preempted;

/// Serialized session checkpoint for pausing and resuming in-flight executions.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SessionCheckpoint {
    /// The original or updated epistemic envelope.
    pub envelope: EpistemicEnvelope,
    /// Total tokens consumed up to this checkpoint.
    pub tokens_consumed: u64,
    /// Cumulative cost in USD incurred.
    pub cost_accumulated_usd: f64,
    /// Cumulative tool invocations made.
    pub tool_invocations: u32,
}

/// An active delegation session parameterized by compile-time type-state.
#[derive(Debug)]
pub struct Session<State> {
    /// Active epistemic envelope governing execution.
    pub envelope: EpistemicEnvelope,
    /// Total tokens consumed so far.
    pub tokens_consumed: u64,
    /// Total USD cost incurred so far.
    pub cost_accumulated_usd: f64,
    /// Total tool invocations made so far.
    pub tool_invocations: u32,
    _marker: PhantomData<State>,
}

impl Session<Idle> {
    /// Create a new session in the Idle state.
    pub fn new(envelope: EpistemicEnvelope) -> Self {
        Self {
            envelope,
            tokens_consumed: 0,
            cost_accumulated_usd: 0.0,
            tool_invocations: 0,
            _marker: PhantomData,
        }
    }

    /// Advance directly from Idle to Executing once handoff is certified.
    pub fn begin_execution(self) -> Session<Executing> {
        Session {
            envelope: self.envelope,
            tokens_consumed: self.tokens_consumed,
            cost_accumulated_usd: self.cost_accumulated_usd,
            tool_invocations: self.tool_invocations,
            _marker: PhantomData,
        }
    }
}

impl Session<Executing> {
    /// Account for resource consumption and enforce budget bounds.
    pub fn record_usage(&mut self, tokens: u64, cost_usd: f64, tools_called: u32) -> AtpResult<()> {
        let leash = &self.envelope.budget_leash;
        self.tokens_consumed += tokens;
        self.cost_accumulated_usd += cost_usd;
        self.tool_invocations += tools_called;

        if self.tokens_consumed > leash.token_limit {
            return Err(AtpError::LeashExhausted(format!(
                "Token limit breached: consumed {} > max {}",
                self.tokens_consumed, leash.token_limit
            )));
        }
        if self.cost_accumulated_usd > leash.max_cost_usd {
            return Err(AtpError::LeashExhausted(format!(
                "Cost cap breached: accumulated ${:.3} > max ${:.3}",
                self.cost_accumulated_usd, leash.max_cost_usd
            )));
        }
        if self.tool_invocations > leash.max_tool_invocations {
            return Err(AtpError::LeashExhausted(format!(
                "Tool invocations breached: {} > max {}",
                self.tool_invocations, leash.max_tool_invocations
            )));
        }

        Ok(())
    }

    /// Fold completed work into a structured epistemic response.
    pub fn fold(
        self,
        patch_diff: String,
        certified_invariants: Vec<String>,
    ) -> (FoldPayload, Session<Folded>) {
        let payload = FoldPayload {
            status: "SUCCESS".to_string(),
            patch_diff,
            invariants_certified: certified_invariants,
            tokens_spent: self.tokens_consumed,
            cost_usd: self.cost_accumulated_usd,
            discovered_counterexamples: Vec::new(),
        };
        let next_session = Session {
            envelope: self.envelope,
            tokens_consumed: self.tokens_consumed,
            cost_accumulated_usd: self.cost_accumulated_usd,
            tool_invocations: self.tool_invocations,
            _marker: PhantomData,
        };
        (payload, next_session)
    }

    /// Escalate execution upon encountering a capability ceiling.
    pub fn yield_cliff(
        self,
        reason: String,
        cliff_category: String,
        counterexample: Option<String>,
    ) -> (YieldPayload, Session<Yielded>) {
        let payload = YieldPayload {
            reason,
            cliff_category,
            unresolvable_counterexample: counterexample,
        };
        let next_session = Session {
            envelope: self.envelope,
            tokens_consumed: self.tokens_consumed,
            cost_accumulated_usd: self.cost_accumulated_usd,
            tool_invocations: self.tool_invocations,
            _marker: PhantomData,
        };
        (payload, next_session)
    }

    /// Suspend execution into a persistent checkpoint.
    pub fn suspend(self) -> (SessionCheckpoint, Session<Suspended>) {
        let checkpoint = SessionCheckpoint {
            envelope: self.envelope.clone(),
            tokens_consumed: self.tokens_consumed,
            cost_accumulated_usd: self.cost_accumulated_usd,
            tool_invocations: self.tool_invocations,
        };
        let next_session = Session {
            envelope: self.envelope,
            tokens_consumed: self.tokens_consumed,
            cost_accumulated_usd: self.cost_accumulated_usd,
            tool_invocations: self.tool_invocations,
            _marker: PhantomData,
        };
        (checkpoint, next_session)
    }

    /// Preempt execution via out-of-band supervisor abort.
    pub fn preempt(self) -> Session<Preempted> {
        Session {
            envelope: self.envelope,
            tokens_consumed: self.tokens_consumed,
            cost_accumulated_usd: self.cost_accumulated_usd,
            tool_invocations: self.tool_invocations,
            _marker: PhantomData,
        }
    }
}

impl Session<Suspended> {
    /// Resume execution from a suspended state.
    pub fn resume(self) -> Session<Executing> {
        Session {
            envelope: self.envelope,
            tokens_consumed: self.tokens_consumed,
            cost_accumulated_usd: self.cost_accumulated_usd,
            tool_invocations: self.tool_invocations,
            _marker: PhantomData,
        }
    }

    /// Reconstruct an executing session from a checkpoint.
    pub fn from_checkpoint(checkpoint: SessionCheckpoint) -> Session<Executing> {
        Session {
            envelope: checkpoint.envelope,
            tokens_consumed: checkpoint.tokens_consumed,
            cost_accumulated_usd: checkpoint.cost_accumulated_usd,
            tool_invocations: checkpoint.tool_invocations,
            _marker: PhantomData,
        }
    }
}

/// Verify if a peer probe satisfies required capability and AX thresholds.
pub fn evaluate_peer_compatibility(
    probe: &ProbePayload,
    required_tokens: u64,
    min_ax_score: f64,
) -> AtpResult<()> {
    if probe.ax_score < min_ax_score {
        return Err(AtpError::PeerIncompatible(format!(
            "Peer AX score {:.2} below minimum {:.2}",
            probe.ax_score, min_ax_score
        )));
    }
    if probe.context_window_available < required_tokens {
        return Err(AtpError::PeerIncompatible(format!(
            "Peer available context ({}) below required {}",
            probe.context_window_available, required_tokens
        )));
    }
    Ok(())
}
