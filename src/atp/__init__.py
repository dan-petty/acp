"""Agentic Transfer Protocol (ATP) core package."""

from __future__ import annotations

from atp.protocol.models import (
    ATP_VERSION,
    BudgetLeash,
    CEGISCounterexample,
    DelegationChain,
    EpistemicEnvelope,
    FoldPayload,
    InvariantContract,
    ProbePayload,
    ProtocolFrame,
    ReasoningLedgerEntry,
    Telos,
    WorkspaceContext,
    YieldPayload,
)
from atp.protocol.transport import (
    ATPTransport,
    FrameSerializer,
    MemoryTransport,
    UnixSocketTransport,
)
from atp.protocol.verbs import (
    ATPCapabilityCliffError,
    ATPInvalidStateTransitionError,
    ATPLeashExhaustedError,
    ATPProtocolError,
    ATPSession,
    ATPState,
    evaluate_peer_compatibility,
)

__version__ = ATP_VERSION

__all__ = [
    "ATP_VERSION",
    "ATPCapabilityCliffError",
    "ATPInvalidStateTransitionError",
    "ATPLeashExhaustedError",
    "ATPProtocolError",
    "ATPSession",
    "ATPState",
    "ATPTransport",
    "BudgetLeash",
    "CEGISCounterexample",
    "DelegationChain",
    "EpistemicEnvelope",
    "FoldPayload",
    "FrameSerializer",
    "InvariantContract",
    "MemoryTransport",
    "ProbePayload",
    "ProtocolFrame",
    "ReasoningLedgerEntry",
    "Telos",
    "UnixSocketTransport",
    "WorkspaceContext",
    "YieldPayload",
    "__version__",
    "evaluate_peer_compatibility",
]
