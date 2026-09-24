//! Error types and result aliases for the Agentic Communication Protocol (ACP).

use thiserror::Error;

/// Core error enumeration for ACP protocol operations.
#[derive(Debug, Error)]
pub enum AcpError {
    /// Budget leash constraints breached.
    #[error("Budget leash exhausted: {0}")]
    LeashExhausted(String),

    /// W3C traceparent context failed specification format.
    #[error("Invalid W3C traceparent context: {0}")]
    InvalidTraceparent(String),

    /// Invalid FSM state transition attempted.
    #[error("Invalid FSM lifecycle transition: {0}")]
    InvalidTransition(String),

    /// Peer failed compatibility or Agent Experience (AX) requirements.
    #[error("Peer incompatibility: {0}")]
    PeerIncompatible(String),

    /// Wire protocol frame size exceeded safety threshold.
    #[error("Frame size {size} bytes exceeds safety limit of {limit} bytes")]
    FrameTooLarge {
        /// Actual size of received frame payload in bytes.
        size: usize,
        /// Maximum allowable safety limit in bytes.
        limit: usize,
    },

    /// Frame serialization or deserialization failure.
    #[error("Frame deserialization or serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    /// Underlying transport stream I/O failure.
    #[error("Underlying I/O error: {0}")]
    Io(#[from] std::io::Error),

    /// Cryptographic signing, verification, or decoding error.
    #[error("Cryptographic attestation error: {0}")]
    Crypto(String),

    /// Validation error on protocol frames, methods, or headers.
    #[error("Validation error: {0}")]
    Validation(String),
}

/// Convenience result alias for ACP operations.
pub type AcpResult<T> = Result<T, AcpError>;
