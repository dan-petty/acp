//! Integration tests for AGTP wire codec and framing in Rust.

use tokio::io::AsyncWriteExt;

use acp::transport::agtp::{
    agtp_request_to_frame, encode_agtp_request, encode_agtp_response, frame_to_agtp_request,
    parse_agtp_request, parse_agtp_response, read_agtp_request, AgtpRequest, AgtpResponse,
};
use acp::{
    BudgetLeash, EpistemicEnvelope, InvariantContract, ProtocolFrame, Telos, WorkspaceContext,
    ACP_VERSION,
};

fn sample_envelope() -> EpistemicEnvelope {
    EpistemicEnvelope {
        acp_version: ACP_VERSION.to_string(),
        envelope_id: "agtp-rust-test-01".to_string(),
        traceparent: "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01".to_string(),
        delegation_chain: None,
        budget_leash: BudgetLeash {
            token_limit: 4000,
            max_cost_usd: 0.05,
            deadline_utc: None,
            max_tool_invocations: 5,
            max_retry_depth: 2,
        },
        telos: Telos {
            goal: "Refactor router in Rust".to_string(),
            exit_criteria: vec!["cargo test passes".to_string()],
        },
        invariant_contract: InvariantContract::default(),
        workspace_context: WorkspaceContext {
            repository: "dan-petty/acp".to_string(),
            commit_base: "abcdef123456".to_string(),
            working_patch: None,
            active_symbols: vec!["router::dispatch".to_string()],
        },
        compacted_reasoning_ledger: vec![],
    }
}

#[test]
fn test_agtp_request_encode_and_parse_roundtrip() {
    let mut req = AgtpRequest::new("DELEGATE", "/v1/tasks/delegate").unwrap();
    req.headers
        .insert("Agent-ID".to_string(), "agent:worker".to_string());
    req.headers
        .insert("Session-ID".to_string(), "sess-999".to_string());
    req.body = b"{\"hello\": \"world\"}".to_vec();

    let bytes = encode_agtp_request(&req);
    let wire_str = String::from_utf8_lossy(&bytes);
    assert!(wire_str.contains("DELEGATE /v1/tasks/delegate AGTP/1.0\r\n"));
    assert!(wire_str.contains("Content-Length: 18\r\n"));

    let parsed = parse_agtp_request(&bytes).unwrap();
    assert_eq!(parsed.method, "DELEGATE");
    assert_eq!(parsed.uri, "/v1/tasks/delegate");
    assert_eq!(parsed.headers.get("Agent-ID").unwrap(), "agent:worker");
    assert_eq!(parsed.body, b"{\"hello\": \"world\"}");
}

#[test]
fn test_agtp_response_encode_and_parse_roundtrip() {
    let mut resp = AgtpResponse::new(200, "OK");
    resp.headers
        .insert("Session-ID".to_string(), "sess-999".to_string());
    resp.body = b"{\"status\": \"CONFIRMED\"}".to_vec();

    let bytes = encode_agtp_response(&resp);
    let wire_str = String::from_utf8_lossy(&bytes);
    assert!(wire_str.contains("AGTP/1.0 200 OK\r\n"));

    let parsed = parse_agtp_response(&bytes).unwrap();
    assert_eq!(parsed.status_code, 200);
    assert_eq!(parsed.reason_phrase, "OK");
    assert_eq!(parsed.body, b"{\"status\": \"CONFIRMED\"}");
}

#[test]
fn test_agtp_content_length_mismatch_rejected() {
    let malformed = b"DELEGATE /run AGTP/1.0\r\nContent-Length: 100\r\n\r\nshort";
    let res = parse_agtp_request(malformed);
    assert!(res.is_err());
}

#[test]
fn test_frame_to_agtp_delegate_request_mapping() {
    let env = sample_envelope();
    let mut frame = ProtocolFrame::new("ACP_HANDOFF_REQUEST");
    frame.envelope = Some(env);

    let agtp_req = frame_to_agtp_request(&frame, "/v1/agent").unwrap();
    assert_eq!(agtp_req.method, "DELEGATE");
    assert_eq!(agtp_req.uri, "/v1/agent");
    assert_eq!(
        agtp_req.headers.get("Traceparent").unwrap(),
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    );

    let reconstructed = agtp_request_to_frame(&agtp_req).unwrap();
    assert_eq!(reconstructed.frame_type, "ACP_HANDOFF_REQUEST");
    let rec_env = reconstructed.envelope.unwrap();
    assert_eq!(rec_env.telos.goal, "Refactor router in Rust");
}

#[tokio::test]
async fn test_agtp_async_stream_read() {
    let mut req = AgtpRequest::new("EXECUTE", "/v1/action").unwrap();
    req.body = b"payload_bytes".to_vec();
    let bytes = encode_agtp_request(&req);

    let (mut client, mut server) = tokio::io::duplex(1024);
    tokio::spawn(async move {
        client.write_all(&bytes).await.unwrap();
    });

    let read_req = read_agtp_request(&mut server).await.unwrap();
    assert_eq!(read_req.method, "EXECUTE");
    assert_eq!(read_req.body, b"payload_bytes");
}
