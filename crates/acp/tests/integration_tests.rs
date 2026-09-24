use acp::{
    evaluate_peer_compatibility, AcpError, BudgetLeash, CEGISCounterexample, DelegationChain,
    EpistemicEnvelope, InvariantContract, MemoryTransport, ProbePayload, ProtocolFrame,
    ReasoningLedgerEntry, Session, Telos, WorkspaceContext, ACP_VERSION,
};

fn sample_envelope() -> EpistemicEnvelope {
    EpistemicEnvelope {
        acp_version: ACP_VERSION.to_string(),
        envelope_id: "rust-test-01".to_string(),
        traceparent: "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01".to_string(),
        delegation_chain: Some(DelegationChain {
            issuer: "user:dan@example.com".to_string(),
            subject: "agent:rust-engine".to_string(),
            attenuated_delegate: None,
            capabilities: vec!["repo:read".to_string(), "repo:write".to_string()],
            proof: "ucan:eyJhbGciOiJFUzI1NksInR5cCI6IkpXVCJ9...".to_string(),
        }),
        budget_leash: BudgetLeash {
            token_limit: 10000,
            max_cost_usd: 0.20,
            max_tool_invocations: 5,
            deadline_utc: None,
            max_retry_depth: 3,
        },
        telos: Telos {
            goal: "Verify Rust type-state ACP engine".to_string(),
            exit_criteria: vec!["cargo test passes 100%".to_string()],
        },
        invariant_contract: InvariantContract {
            positive_invariants: vec!["type_state_fsm".to_string()],
            negative_constraints: vec!["no_runtime_type_error".to_string()],
            cegis_counterexamples: vec![CEGISCounterexample {
                input: "session.fold() on Idle".to_string(),
                expected: "Compile error".to_string(),
                failing_actual: "N/A".to_string(),
                rationale: Some("Prevented by affine type-state".to_string()),
            }],
        },
        workspace_context: WorkspaceContext {
            repository: "dan-petty/acp".to_string(),
            commit_base: "88d3063c685252f4e4a79ecfb92f1b0e890e698f".to_string(),
            working_patch: None,
            active_symbols: vec!["acp::fsm::Session".to_string()],
        },
        compacted_reasoning_ledger: vec![ReasoningLedgerEntry {
            hypotheses_evaluated: 1,
            falsified: vec![],
            active_approach: "Compile-time PhantomData type-state".to_string(),
        }],
    }
}

#[test]
fn test_serde_roundtrip_envelope() {
    let envelope = sample_envelope();
    let json_str = serde_json::to_string_pretty(&envelope).expect("Failed to serialize");
    let deserialized: EpistemicEnvelope =
        serde_json::from_str(&json_str).expect("Failed to deserialize");

    assert_eq!(envelope, deserialized);
    assert!(deserialized.validate().is_ok());
}

#[test]
fn test_negative_schema_bounds_deny_unknown_fields() {
    let mut value = serde_json::to_value(sample_envelope()).expect("To value");
    value
        .as_object_mut()
        .unwrap()
        .insert("hallucinated_property".to_string(), serde_json::json!(true));

    let result: Result<EpistemicEnvelope, _> = serde_json::from_value(value);
    assert!(result.is_err());
}

#[test]
fn test_typestate_fsm_execution_and_fold() {
    let envelope = sample_envelope();
    let session = Session::new(envelope);

    let mut executing = session.begin_execution();
    assert!(executing.record_usage(500, 0.01, 1).is_ok());

    let (fold_payload, folded_session) = executing.fold(
        "diff --git a/lib.rs b/lib.rs".to_string(),
        vec!["type_state_verified".to_string()],
    );

    assert_eq!(fold_payload.status, "SUCCESS");
    assert_eq!(fold_payload.tokens_spent, 500);
    assert_eq!(folded_session.tokens_consumed, 500);
}

#[test]
fn test_budget_leash_exhaustion() {
    let envelope = sample_envelope();
    let session = Session::new(envelope);
    let mut executing = session.begin_execution();

    let err = executing.record_usage(20000, 0.05, 1).unwrap_err();
    match err {
        AcpError::LeashExhausted(msg) => assert!(msg.contains("Token limit breached")),
        other => panic!("Expected LeashExhausted, got {:?}", other),
    }
}

#[test]
fn test_checkpoint_suspend_and_resume() {
    let envelope = sample_envelope();
    let session = Session::new(envelope);
    let mut executing = session.begin_execution();
    executing.record_usage(120, 0.002, 1).unwrap();

    let (checkpoint, _suspended) = executing.suspend();
    assert_eq!(checkpoint.tokens_consumed, 120);

    let resumed = Session::from_checkpoint(checkpoint);
    assert_eq!(resumed.tokens_consumed, 120);
    assert_eq!(resumed.envelope.envelope_id, "rust-test-01");
}

#[test]
fn test_peer_compatibility_check() {
    let probe_ok = ProbePayload {
        agent_id: "rust-agent-01".to_string(),
        model_id: "claude-3-5-sonnet".to_string(),
        context_window_total: 200000,
        context_window_available: 100000,
        supported_isolation: vec!["ISOLATION_ROOTLESS_CONTAINER".to_string()],
        ax_score: 0.95,
        available_tools: vec!["ast_refactor".to_string()],
    };
    assert!(evaluate_peer_compatibility(&probe_ok, 1000, 0.75).is_ok());

    let probe_low_ax = ProbePayload {
        ax_score: 0.60,
        ..probe_ok
    };
    assert!(evaluate_peer_compatibility(&probe_low_ax, 1000, 0.75).is_err());
}

#[tokio::test]
async fn test_memory_transport_duplex() {
    let (mut client, mut server) = MemoryTransport::pair(16);

    let frame_out = ProtocolFrame {
        frame_type: "ACP_PREEMPT_REQUEST".to_string(),
        frame_id: "frame-01".to_string(),
        timestamp_utc: chrono::Utc::now(),
        envelope: None,
        probe_payload: None,
        fold_payload: None,
        yield_payload: None,
    };

    client.send(frame_out.clone()).await.unwrap();
    let received_server = server.receive().await.unwrap();
    assert_eq!(received_server.frame_type, "ACP_PREEMPT_REQUEST");

    let response_frame = ProtocolFrame {
        frame_type: "ACP_FOLD_RESPONSE".to_string(),
        ..frame_out
    };
    server.send(response_frame).await.unwrap();
    let received_client = client.receive().await.unwrap();
    assert_eq!(received_client.frame_type, "ACP_FOLD_RESPONSE");
}
