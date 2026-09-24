"""Unit tests for ACP Ed25519 cryptographic attestation and attenuation."""

from __future__ import annotations

from acp.protocol.crypto import (
    generate_keypair,
    sign_delegation,
    verify_attenuation,
    verify_delegation,
)
from acp.protocol.models import DelegationChain


def test_keypair_generation():
    """Verify generated keypairs conform to 32-byte hex string format."""
    seed_hex, pubkey_hex = generate_keypair()
    assert (len(seed_hex), len(pubkey_hex)) == (64, 64)


def test_sign_and_verify_delegation():
    """Verify that signed delegations pass verification with the issuer public key."""
    seed_hex, pubkey_hex = generate_keypair()
    chain = sign_delegation(
        private_seed_hex=seed_hex,
        issuer="user:dan@example.com",
        subject="agent:orchestrator",
        capabilities=["repo:read", "repo:write"],
        attenuated_delegate="agent:worker",
    )
    is_valid = verify_delegation(chain, pubkey_hex)
    assert (chain.issuer, chain.subject, is_valid) == (
        "user:dan@example.com",
        "agent:orchestrator",
        True,
    )


def test_verify_delegation_tamper_detection():
    """Verify that tampering with any field or signature invalidates verification."""
    seed_hex, pubkey_hex = generate_keypair()
    chain = sign_delegation(
        private_seed_hex=seed_hex,
        issuer="user:dan@example.com",
        subject="agent:orchestrator",
        capabilities=["repo:read"],
    )
    tampered_caps = chain.model_copy(update={"capabilities": ["repo:read", "admin:all"]})
    tampered_subj = chain.model_copy(update={"subject": "agent:attacker"})
    tampered_sig = chain.model_copy(update={"proof": "00" * 64})

    results = (
        verify_delegation(tampered_caps, pubkey_hex),
        verify_delegation(tampered_subj, pubkey_hex),
        verify_delegation(tampered_sig, pubkey_hex),
        verify_delegation(chain, "00" * 32),
    )
    assert results == (False, False, False, False)


def test_capability_attenuation():
    """Verify that child delegations can only attenuate permissions."""
    parent = DelegationChain(
        issuer="user:dan@example.com",
        subject="agent:orchestrator",
        capabilities=["repo:read", "repo:write", "test:run"],
        proof="signature_parent_001",
    )

    valid_child = DelegationChain(
        issuer="agent:orchestrator",
        subject="agent:worker",
        capabilities=["repo:read", "test:run"],
        proof="signature_child_001",
    )

    escalated_child = DelegationChain(
        issuer="agent:orchestrator",
        subject="agent:worker",
        capabilities=["repo:read", "cloud:deploy"],
        proof="signature_child_002",
    )

    mismatched_issuer_child = DelegationChain(
        issuer="agent:stranger",
        subject="agent:worker",
        capabilities=["repo:read"],
        proof="signature_child_003",
    )

    assert (
        verify_attenuation(parent, valid_child),
        verify_attenuation(parent, escalated_child),
        verify_attenuation(parent, mismatched_issuer_child),
    ) == (True, False, False)
