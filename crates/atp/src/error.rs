//! Error types and result aliases for the Agentic Transfer Protocol (ATP).

use thiserror::Error;

/// Core error enumeration for ATP protocol operations.
#[derive(Debug, Error)]
pub enum AtpError {
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
}

/// Convenience result alias for ATP operations.
pub type AtpResult<T> = Result<T, AtpError>;
