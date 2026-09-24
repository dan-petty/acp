//! Core data structures, schemas, and framing models for ATP.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::error::{AtpError, AtpResult};

/// Active specification version of the Agentic Transfer Protocol.
pub const ATP_VERSION: &str = "1.0.0";

/// Authority delegation chain with cryptographic proof token.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DelegationChain {
    /// Originating authority (DID or public key URI).
    pub issuer: String,
    /// Intended target agent recipient.
    pub subject: String,
    /// Optional attenuated downstream delegate.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub attenuated_delegate: Option<String>,
    /// Permitted capability identifiers.
    #[serde(default)]
    pub capabilities: Vec<String>,
    /// Cryptographic proof token (UCAN or Macaroon signature).
    pub proof: String,
}

/// Resource bounding leash for agent execution.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BudgetLeash {
    /// Maximum allowed token consumption.
    pub token_limit: u64,
    /// Maximum allowed financial cost in USD.
    pub max_cost_usd: f64,
    /// Maximum allowed external tool invocations.
    pub max_tool_invocations: u32,
    /// Hard execution deadline in UTC timestamp.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub deadline_utc: Option<DateTime<Utc>>,
    /// Maximum retry depth before yielding.
    #[serde(default = "default_retry_depth")]
    pub max_retry_depth: u32,
}

fn default_retry_depth() -> u32 {
    3
}

/// Task intent and falsifiable completion criteria.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Telos {
    /// Clear natural-language or structured objective.
    pub goal: String,
    /// Deterministic, falsifiable exit criteria strings.
    pub exit_criteria: Vec<String>,
}

/// Failing counterexample discovered during verification.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CEGISCounterexample {
    /// Input stimulus that induced failure.
    pub input: String,
    /// Expected behavior or specification assertion.
    pub expected: String,
    /// Actual observed failing response.
    pub failing_actual: String,
    /// Optional explanation of failure mechanism.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rationale: Option<String>,
}

/// Positive invariants, negative constraints, and counterexample cases.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InvariantContract {
    /// Assertions that must remain true (e.g. tests pass).
    #[serde(default)]
    pub positive_invariants: Vec<String>,
    /// Conditions that must never occur (e.g. no private leaks).
    #[serde(default)]
    pub negative_constraints: Vec<String>,
    /// Synthesized counterexamples discovered via CEGIS loops.
    #[serde(default)]
    pub cegis_counterexamples: Vec<CEGISCounterexample>,
}

/// Git workspace context and modified symbol anchors.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkspaceContext {
    /// Repository identifier (e.g. `dan-petty/atp`).
    pub repository: String,
    /// Base commit SHA before current modifications.
    pub commit_base: String,
    /// Unified git diff of in-flight work.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub working_patch: Option<String>,
    /// Code symbols currently under modification.
    #[serde(default)]
    pub active_symbols: Vec<String>,
}

/// Compacted history of problem-solving hypotheses and falsified attempts.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReasoningLedgerEntry {
    /// Count of hypotheses investigated.
    pub hypotheses_evaluated: u32,
    /// Approaches proven unsuccessful and reasons why.
    #[serde(default)]
    pub falsified: Vec<String>,
    /// Strategy currently being pursued.
    pub active_approach: String,
}

/// The Epistemic State Envelope (ESE): unit of cognitive state transfer.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EpistemicEnvelope {
    /// Protocol version string.
    #[serde(default = "default_version")]
    pub atp_version: String,
    /// Unique envelope identifier (UUIDv4).
    #[serde(default = "default_uuid")]
    pub envelope_id: String,
    /// W3C distributed trace context header string.
    pub traceparent: String,
    /// Attenuated delegation token.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub delegation_chain: Option<DelegationChain>,
    /// Resource consumption boundaries.
    pub budget_leash: BudgetLeash,
    /// Goal and completion criteria.
    pub telos: Telos,
    /// Certified invariants and anti-regression constraints.
    pub invariant_contract: InvariantContract,
    /// Git workspace and repository anchoring.
    pub workspace_context: WorkspaceContext,
    /// Compacted history of problem-solving paths.
    #[serde(default)]
    pub compacted_reasoning_ledger: Vec<ReasoningLedgerEntry>,
}

fn default_version() -> String {
    ATP_VERSION.to_string()
}

fn default_uuid() -> String {
    Uuid::new_v4().to_string()
}

impl EpistemicEnvelope {
    /// Verify W3C traceparent formatting.
    pub fn validate(&self) -> AtpResult<()> {
        if !self.traceparent.starts_with("00-") || self.traceparent.len() != 55 {
            return Err(AtpError::InvalidTraceparent(self.traceparent.clone()));
        }
        Ok(())
    }
}

/// Peer discovery and Agent Experience (AX) probe payload.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProbePayload {
    /// Peer agent identifier.
    pub agent_id: String,
    /// Primary foundation model backing the agent.
    pub model_id: String,
    /// Total context window size in tokens.
    pub context_window_total: u64,
    /// Available headroom in tokens.
    pub context_window_available: u64,
    /// Supported isolation environments (e.g. bubblewrap, gVisor, firecracker).
    #[serde(default)]
    pub supported_isolation: Vec<String>,
    /// Composite Agent Experience quality score (0.0 - 1.0).
    #[serde(default = "default_ax_score")]
    pub ax_score: f64,
    /// Tool signatures available in this peer environment.
    #[serde(default)]
    pub available_tools: Vec<String>,
}

fn default_ax_score() -> f64 {
    1.0
}

/// Structured epistemic result folded back upstream.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FoldPayload {
    /// Terminal outcome status (SUCCESS, PARTIAL, ABORTED).
    pub status: String,
    /// Final unified patch diff.
    #[serde(default)]
    pub patch_diff: String,
    /// List of invariants certified passing.
    #[serde(default)]
    pub invariants_certified: Vec<String>,
    /// Cumulative tokens consumed.
    #[serde(default)]
    pub tokens_spent: u64,
    /// Cumulative financial cost in USD.
    #[serde(default)]
    pub cost_usd: f64,
    /// Failing counterexamples discovered.
    #[serde(default)]
    pub discovered_counterexamples: Vec<CEGISCounterexample>,
}

/// Capability barrier escalation payload.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct YieldPayload {
    /// Natural-language rationale for escalation.
    pub reason: String,
    /// Category of capability barrier encountered.
    pub cliff_category: String,
    /// Counterexample that could not be resolved.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub unresolvable_counterexample: Option<String>,
}

/// Wire envelope framing all ATP messages.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProtocolFrame {
    /// Protocol frame verb or message type.
    pub frame_type: String,
    /// Frame sequence identifier.
    #[serde(default = "default_uuid")]
    pub frame_id: String,
    /// Frame emission timestamp in UTC.
    #[serde(default = "Utc::now")]
    pub timestamp_utc: DateTime<Utc>,
    /// Embedded epistemic state envelope (for HANDOFF frames).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub envelope: Option<EpistemicEnvelope>,
    /// Embedded probe payload (for PROBE frames).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub probe_payload: Option<ProbePayload>,
    /// Embedded fold payload (for FOLD frames).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fold_payload: Option<FoldPayload>,
    /// Embedded yield payload (for YIELD frames).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub yield_payload: Option<YieldPayload>,
}
