use acp::crypto::{generate_keypair, sign_delegation, verify_attenuation, verify_delegation};
use acp::models::DelegationChain;

#[test]
fn test_keypair_generation_length() {
    let (priv_hex, pub_hex) = generate_keypair();
    assert_eq!((priv_hex.len(), pub_hex.len()), (64, 64));
}

#[test]
fn test_sign_and_verify_roundtrip() {
    let (priv_hex, pub_hex) = generate_keypair();
    let chain = sign_delegation(
        &priv_hex,
        "user:dan@example.com".to_string(),
        "agent:orchestrator".to_string(),
        vec!["repo:read".to_string(), "repo:write".to_string()],
        Some("agent:worker".to_string()),
    )
    .expect("Signing failed");

    let is_valid = verify_delegation(&chain, &pub_hex);
    assert!(is_valid);
}

#[test]
fn test_tamper_detection() {
    let (priv_hex, pub_hex) = generate_keypair();
    let chain = sign_delegation(
        &priv_hex,
        "user:dan@example.com".to_string(),
        "agent:orchestrator".to_string(),
        vec!["repo:read".to_string()],
        None,
    )
    .expect("Signing failed");

    let mut tampered_caps = chain.clone();
    tampered_caps.capabilities.push("admin:all".to_string());

    let mut tampered_subj = chain.clone();
    tampered_subj.subject = "agent:attacker".to_string();

    let mut tampered_sig = chain.clone();
    tampered_sig.proof = "00".repeat(64);

    assert!(!verify_delegation(&tampered_caps, &pub_hex));
    assert!(!verify_delegation(&tampered_subj, &pub_hex));
    assert!(!verify_delegation(&tampered_sig, &pub_hex));
    assert!(!verify_delegation(&chain, &"00".repeat(32)));
}

#[test]
fn test_attenuation_verification() {
    let parent = DelegationChain {
        issuer: "user:dan@example.com".to_string(),
        subject: "agent:orchestrator".to_string(),
        attenuated_delegate: None,
        capabilities: vec![
            "repo:read".to_string(),
            "repo:write".to_string(),
            "test:run".to_string(),
        ],
        proof: "sig_parent_123".to_string(),
    };

    let valid_child = DelegationChain {
        issuer: "agent:orchestrator".to_string(),
        subject: "agent:worker".to_string(),
        attenuated_delegate: None,
        capabilities: vec!["repo:read".to_string(), "test:run".to_string()],
        proof: "sig_child_123".to_string(),
    };

    let escalated_child = DelegationChain {
        issuer: "agent:orchestrator".to_string(),
        subject: "agent:worker".to_string(),
        attenuated_delegate: None,
        capabilities: vec!["repo:read".to_string(), "cloud:deploy".to_string()],
        proof: "sig_child_124".to_string(),
    };

    let mismatched_issuer = DelegationChain {
        issuer: "agent:stranger".to_string(),
        subject: "agent:worker".to_string(),
        attenuated_delegate: None,
        capabilities: vec!["repo:read".to_string()],
        proof: "sig_child_125".to_string(),
    };

    assert!(verify_attenuation(&parent, &valid_child));
    assert!(!verify_attenuation(&parent, &escalated_child));
    assert!(!verify_attenuation(&parent, &mismatched_issuer));
}

#[test]
fn test_cross_compatibility_python_signature() {
    let pub_hex = "8a88e3dd7409f195fd52db2d3cba5d72ca6709bf1d94121bf3748801b40f6f5c";
    let proof = "27cd711b342ed09ed4b2c6fb94fb50dc047785c5f387fa4c2f5422f9e1ce1ece79b6274da190da632665324cc8fd0f9f54ac183a91a054a36e8cf6e5b1d54408";
    let chain = DelegationChain {
        issuer: "user:dan@example.com".to_string(),
        subject: "agent:orchestrator".to_string(),
        attenuated_delegate: Some("agent:worker".to_string()),
        capabilities: vec!["repo:read".to_string(), "repo:write".to_string()],
        proof: proof.to_string(),
    };
    assert!(verify_delegation(&chain, pub_hex));
}
