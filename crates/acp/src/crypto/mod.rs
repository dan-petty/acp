//! Cryptographic attestation and capability attenuation for ATP delegation chains.

use std::collections::HashSet;

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use rand::rngs::OsRng;

use crate::error::{AcpError, AcpResult};
use crate::models::DelegationChain;

/// Compute deterministic canonical byte payload for signing an authority delegation.
pub fn compute_canonical_payload(
    issuer: &str,
    subject: &str,
    capabilities: &[String],
    attenuated_delegate: Option<&str>,
) -> Vec<u8> {
    let mut sorted_caps = capabilities.to_vec();
    sorted_caps.sort();
    let caps_str = sorted_caps.join(",");
    let delegate_str = attenuated_delegate.unwrap_or("");
    format!("{issuer}\n{subject}\n{delegate_str}\n{caps_str}").into_bytes()
}

/// Generate a new Ed25519 keypair, returning hex-encoded `(private_seed_hex, public_key_hex)`.
pub fn generate_keypair() -> (String, String) {
    let mut csprng = OsRng;
    let signing_key = SigningKey::generate(&mut csprng);
    let verifying_key = signing_key.verifying_key();
    (
        hex::encode(signing_key.to_bytes()),
        hex::encode(verifying_key.to_bytes()),
    )
}

/// Sign an authority delegation chain using a 32-byte Ed25519 private key seed (hex).
pub fn sign_delegation(
    private_seed_hex: &str,
    issuer: String,
    subject: String,
    capabilities: Vec<String>,
    attenuated_delegate: Option<String>,
) -> AcpResult<DelegationChain> {
    let seed_bytes = hex::decode(private_seed_hex)
        .map_err(|e| AcpError::Crypto(format!("Invalid private key hex: {e}")))?;
    let seed_array: [u8; 32] = seed_bytes
        .as_slice()
        .try_into()
        .map_err(|_| AcpError::Crypto("Private seed must be exactly 32 bytes".to_string()))?;

    let signing_key = SigningKey::from_bytes(&seed_array);
    let payload = compute_canonical_payload(
        &issuer,
        &subject,
        &capabilities,
        attenuated_delegate.as_deref(),
    );
    let signature: Signature = signing_key.sign(&payload);

    Ok(DelegationChain {
        issuer,
        subject,
        attenuated_delegate,
        capabilities,
        proof: hex::encode(signature.to_bytes()),
    })
}

/// Verify an Ed25519 signature on an ATP DelegationChain using the issuer's public key (hex).
pub fn verify_delegation(chain: &DelegationChain, issuer_public_key_hex: &str) -> bool {
    let pubkey_bytes = match hex::decode(issuer_public_key_hex) {
        Ok(b) => b,
        Err(_) => return false,
    };
    let pubkey_array: [u8; 32] = match pubkey_bytes.as_slice().try_into() {
        Ok(arr) => arr,
        Err(_) => return false,
    };
    let verifying_key = match VerifyingKey::from_bytes(&pubkey_array) {
        Ok(vk) => vk,
        Err(_) => return false,
    };

    let sig_bytes = match hex::decode(&chain.proof) {
        Ok(b) => b,
        Err(_) => return false,
    };
    let sig_array: [u8; 64] = match sig_bytes.as_slice().try_into() {
        Ok(arr) => arr,
        Err(_) => return false,
    };
    let signature = Signature::from_bytes(&sig_array);

    let payload = compute_canonical_payload(
        &chain.issuer,
        &chain.subject,
        &chain.capabilities,
        chain.attenuated_delegate.as_deref(),
    );

    verifying_key.verify(&payload, &signature).is_ok()
}

/// Verify that a child delegation chain attenuates parent authority without privilege escalation.
pub fn verify_attenuation(parent: &DelegationChain, child: &DelegationChain) -> bool {
    let is_subject_issuer = child.issuer == parent.subject;
    let parent_set: HashSet<&str> = parent.capabilities.iter().map(String::as_str).collect();
    let is_subset = child
        .capabilities
        .iter()
        .all(|cap| parent_set.contains(cap.as_str()));
    is_subject_issuer && is_subset
}
