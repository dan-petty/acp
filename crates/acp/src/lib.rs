//! Agentic Communication Protocol (ACP) Rust Reference Implementation.
//!
//! A high-performance, memory-safe, and compile-time type-checked protocol engine
//! for cognitive state migration, attenuated authority delegation, and closed-loop
//! epistemic synchronization.

#![forbid(unsafe_code)]
#![warn(missing_docs)]

pub mod crypto;
pub mod error;
pub mod fsm;
pub mod models;
pub mod transport;

pub use crypto::{
    compute_canonical_payload, generate_keypair, sign_delegation, verify_attenuation,
    verify_delegation,
};
pub use error::{AcpError, AcpResult};
pub use fsm::{
    evaluate_peer_compatibility, Executing, Folded, Idle, PeerCertified, Preempted, Probing,
    Session, SessionCheckpoint, Suspended, Yielded, DEFAULT_MIN_AX_SCORE,
};
pub use models::{
    BudgetLeash, CEGISCounterexample, DelegationChain, EpistemicEnvelope, FoldPayload,
    InvariantContract, ProbePayload, ProtocolFrame, ReasoningLedgerEntry, Telos, WorkspaceContext,
    YieldPayload, ACP_VERSION,
};
pub use transport::{
    agtp::{
        agtp_request_to_frame, encode_agtp_request, encode_agtp_response, frame_to_agtp_request,
        parse_agtp_request, parse_agtp_response, read_agtp_request, write_agtp_request,
        AgtpRequest, AgtpResponse, VALID_AGTP_METHODS,
    },
    read_frame, write_frame, MemoryTransport, ProtocolFrameCodec, MAX_FRAME_SIZE_BYTES,
};
