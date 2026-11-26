"""Cryptographic attestation and capability attenuation for ACP delegation chains."""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from acp.protocol.models import DelegationChain


def generate_keypair() -> tuple[str, str]:
    """Generate a new Ed25519 keypair returning hex-encoded (private_seed, public_key)."""
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes_raw()
    public_bytes = private_key.public_key().public_bytes_raw()
    return private_bytes.hex(), public_bytes.hex()


def compute_canonical_payload(
    issuer: str,
    subject: str,
    capabilities: list[str],
    attenuated_delegate: str | None = None,
) -> bytes:
    """Compute the deterministic canonical byte payload for signing a delegation."""
    sorted_caps = ",".join(sorted(capabilities))
    delegate_str = attenuated_delegate or ""
    canonical = f"{issuer}\n{subject}\n{delegate_str}\n{sorted_caps}"
    return canonical.encode("utf-8")


def sign_delegation(
    private_seed_hex: str,
    issuer: str,
    subject: str,
    capabilities: list[str],
    attenuated_delegate: str | None = None,
) -> DelegationChain:
    """Sign an authority delegation with an Ed25519 private key seed."""
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_seed_hex))
    payload = compute_canonical_payload(issuer, subject, capabilities, attenuated_delegate)
    signature = private_key.sign(payload)
    return DelegationChain(
        issuer=issuer,
        subject=subject,
        attenuated_delegate=attenuated_delegate,
        capabilities=capabilities,
        proof=signature.hex(),
    )


def verify_delegation(chain: DelegationChain, issuer_public_key_hex: str) -> bool:
    """Verify an Ed25519 signature on an ATP DelegationChain."""
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(issuer_public_key_hex))
        payload = compute_canonical_payload(
            chain.issuer, chain.subject, chain.capabilities, chain.attenuated_delegate
        )
        public_key.verify(bytes.fromhex(chain.proof), payload)
        return True
    except InvalidSignature, ValueError:
        return False


def verify_attenuation(parent: DelegationChain, child: DelegationChain) -> bool:
    """Verify that a child delegation chain attenuates parent authority without privilege escalation."""
    is_subject_issuer = child.issuer == parent.subject
    parent_caps = set(parent.capabilities)
    child_caps = set(child.capabilities)
    is_subset = child_caps.issubset(parent_caps)
    return is_subject_issuer and is_subset
