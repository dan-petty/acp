//! Agentic Transfer Protocol (ATP) Rust Reference Implementation.
//!
//! A high-performance, memory-safe, and compile-time type-checked protocol engine
//! for cognitive state migration, attenuated authority delegation, and closed-loop
//! epistemic synchronization.

#![forbid(unsafe_code)]
#![warn(missing_docs)]

pub mod error;
pub mod fsm;
pub mod models;
pub mod transport;

pub use error::{AtpError, AtpResult};
pub use fsm::{
    evaluate_peer_compatibility, Executing, Folded, Idle, PeerCertified, Preempted, Probing,
    Session, SessionCheckpoint, Suspended, Yielded, DEFAULT_MIN_AX_SCORE,
};
pub use models::{
    BudgetLeash, CEGISCounterexample, DelegationChain, EpistemicEnvelope, FoldPayload,
    InvariantContract, ProbePayload, ProtocolFrame, ReasoningLedgerEntry, Telos, WorkspaceContext,
    YieldPayload, ATP_VERSION,
};
pub use transport::{
    read_frame, write_frame, MemoryTransport, ProtocolFrameCodec, MAX_FRAME_SIZE_BYTES,
};
