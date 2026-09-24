//! AGTP (draft-hood-independent-agtp) wire protocol framing, request/response codecs, and ACP mappings.

use std::collections::BTreeMap;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

use crate::error::{AcpError, AcpResult};
use crate::models::{EpistemicEnvelope, FoldPayload, ProbePayload, ProtocolFrame, YieldPayload};

/// AGTP wire protocol version string.
pub const AGTP_VERSION: &str = "AGTP/1.0";

/// Maximum allowable header block size in bytes (64 KB).
pub const MAX_HEADER_SIZE_BYTES: usize = 64 * 1024;

/// Maximum allowable body size in bytes (16 MB).
pub const MAX_BODY_SIZE_BYTES: usize = 16 * 1024 * 1024;

/// Valid AGTP/1.0 method verbs.
pub const VALID_AGTP_METHODS: &[&str] = &[
    "QUERY",
    "DISCOVER",
    "DESCRIBE",
    "SUMMARIZE",
    "PLAN",
    "PROPOSE",
    "EXECUTE",
    "DELEGATE",
    "ESCALATE",
    "CONFIRM",
    "SUSPEND",
    "NOTIFY",
];

/// An inbound or outbound AGTP request.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgtpRequest {
    /// Agent intent method verb (e.g., DELEGATE, CONFIRM, ESCALATE).
    pub method: String,
    /// Destination URI or path.
    pub uri: String,
    /// Protocol version string (default AGTP/1.0).
    pub version: String,
    /// Protocol header map.
    pub headers: BTreeMap<String, String>,
    /// Request body payload bytes.
    pub body: Vec<u8>,
}

impl AgtpRequest {
    /// Construct a new AGTP request with validated method verb.
    pub fn new(method: impl Into<String>, uri: impl Into<String>) -> AcpResult<Self> {
        let m = method.into();
        if !VALID_AGTP_METHODS.contains(&m.as_str()) {
            return Err(AcpError::Validation(format!(
                "Invalid or unrecognized AGTP method: {}",
                m
            )));
        }
        Ok(Self {
            method: m,
            uri: uri.into(),
            version: AGTP_VERSION.to_string(),
            headers: BTreeMap::new(),
            body: Vec::new(),
        })
    }
}

/// An inbound or outbound AGTP response.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgtpResponse {
    /// Three-digit numeric status code.
    pub status_code: u16,
    /// Human-readable reason phrase.
    pub reason_phrase: String,
    /// Protocol version string.
    pub version: String,
    /// Protocol header map.
    pub headers: BTreeMap<String, String>,
    /// Response body payload bytes.
    pub body: Vec<u8>,
}

impl AgtpResponse {
    /// Construct a new AGTP response.
    pub fn new(status_code: u16, reason: impl Into<String>) -> Self {
        Self {
            status_code,
            reason_phrase: reason.into(),
            version: AGTP_VERSION.to_string(),
            headers: BTreeMap::new(),
            body: Vec::new(),
        }
    }
}

fn format_headers(headers: &BTreeMap<String, String>, body_len: usize) -> Vec<u8> {
    let mut norm = headers.clone();
    norm.insert("Content-Length".to_string(), body_len.to_string());
    if !norm.contains_key("Content-Type") && body_len > 0 {
        norm.insert(
            "Content-Type".to_string(),
            "application/agtp+json".to_string(),
        );
    }

    let mut out = Vec::new();
    for (k, v) in norm {
        out.extend_from_slice(format!("{}: {}\r\n", k, v).as_bytes());
    }
    out.extend_from_slice(b"\r\n");
    out
}

/// Serialize an AgtpRequest into wire-formatted bytes.
pub fn encode_agtp_request(req: &AgtpRequest) -> Vec<u8> {
    let start_line = format!("{} {} {}\r\n", req.method, req.uri, req.version);
    let mut data = start_line.into_bytes();
    data.extend(format_headers(&req.headers, req.body.len()));
    data.extend_from_slice(&req.body);
    data
}

/// Serialize an AgtpResponse into wire-formatted bytes.
pub fn encode_agtp_response(resp: &AgtpResponse) -> Vec<u8> {
    let start_line = format!(
        "{} {} {}\r\n",
        resp.version, resp.status_code, resp.reason_phrase
    );
    let mut data = start_line.into_bytes();
    data.extend(format_headers(&resp.headers, resp.body.len()));
    data.extend_from_slice(&resp.body);
    data
}

struct ParsedHeaderBlock<'a> {
    lines: Vec<String>,
    headers: BTreeMap<String, String>,
    body: &'a [u8],
}

fn parse_headers_and_body(raw: &[u8]) -> AcpResult<ParsedHeaderBlock<'_>> {
    let delim = b"\r\n\r\n";
    let pos = raw
        .windows(delim.len())
        .position(|window| window == delim)
        .ok_or_else(|| AcpError::Validation("Missing AGTP header termination".to_string()))?;

    let head_str = std::str::from_utf8(&raw[..pos])
        .map_err(|e| AcpError::Validation(format!("Invalid UTF-8 in AGTP headers: {}", e)))?;
    let body = &raw[pos + delim.len()..];

    let lines: Vec<String> = head_str.split("\r\n").map(|s| s.to_string()).collect();
    if lines.is_empty() {
        return Err(AcpError::Validation("Empty AGTP header block".to_string()));
    }

    let mut headers = BTreeMap::new();
    for line in &lines[1..] {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if let Some((k, v)) = trimmed.split_once(':') {
            headers.insert(k.trim().to_string(), v.trim().to_string());
        } else {
            return Err(AcpError::Validation(format!(
                "Malformed AGTP header: {}",
                trimmed
            )));
        }
    }

    let cl = headers
        .get("Content-Length")
        .ok_or_else(|| {
            AcpError::Validation("Missing Content-Length header in AGTP frame".to_string())
        })?
        .parse::<usize>()
        .map_err(|e| AcpError::Validation(format!("Invalid Content-Length: {}", e)))?;

    if cl != body.len() {
        return Err(AcpError::Validation(format!(
            "Content-Length mismatch: expected {}, got {}",
            cl,
            body.len()
        )));
    }

    Ok(ParsedHeaderBlock {
        lines,
        headers,
        body,
    })
}

/// Parse raw wire bytes into an AgtpRequest.
pub fn parse_agtp_request(raw: &[u8]) -> AcpResult<AgtpRequest> {
    let parsed = parse_headers_and_body(raw)?;
    let start_line = &parsed.lines[0];
    let parts: Vec<&str> = start_line.split_whitespace().collect();
    if parts.len() != 3 {
        return Err(AcpError::Validation(format!(
            "Malformed AGTP start line: {}",
            start_line
        )));
    }

    let req = AgtpRequest {
        method: parts[0].to_string(),
        uri: parts[1].to_string(),
        version: parts[2].to_string(),
        headers: parsed.headers,
        body: parsed.body.to_vec(),
    };
    if !VALID_AGTP_METHODS.contains(&req.method.as_str()) {
        return Err(AcpError::Validation(format!(
            "Unrecognized AGTP method: {}",
            req.method
        )));
    }
    Ok(req)
}

/// Parse raw wire bytes into an AgtpResponse.
pub fn parse_agtp_response(raw: &[u8]) -> AcpResult<AgtpResponse> {
    let parsed = parse_headers_and_body(raw)?;
    let start_line = &parsed.lines[0];
    let parts: Vec<&str> = start_line.splitn(3, ' ').collect();
    if parts.len() < 2 {
        return Err(AcpError::Validation(format!(
            "Malformed AGTP status line: {}",
            start_line
        )));
    }

    let status_code = parts[1]
        .parse::<u16>()
        .map_err(|e| AcpError::Validation(format!("Invalid status code: {}", e)))?;
    let reason_phrase = if parts.len() > 2 {
        parts[2].to_string()
    } else {
        "".to_string()
    };

    Ok(AgtpResponse {
        version: parts[0].to_string(),
        status_code,
        reason_phrase,
        headers: parsed.headers,
        body: parsed.body.to_vec(),
    })
}

/// Asynchronously read a single Content-Length framed AGTPRequest from a stream.
pub async fn read_agtp_request<R: AsyncReadExt + Unpin>(reader: &mut R) -> AcpResult<AgtpRequest> {
    let mut buffer = Vec::new();
    let delim = b"\r\n\r\n";

    loop {
        if let Some(pos) = buffer.windows(delim.len()).position(|w| w == delim) {
            let head_str = std::str::from_utf8(&buffer[..pos])
                .map_err(|e| AcpError::Validation(format!("Invalid UTF-8: {}", e)))?;
            let cl = head_str
                .lines()
                .find_map(|l| {
                    let (k, v) = l.split_once(':')?;
                    if k.trim().eq_ignore_ascii_case("Content-Length") {
                        v.trim().parse::<usize>().ok()
                    } else {
                        None
                    }
                })
                .unwrap_or(0);

            if cl > MAX_BODY_SIZE_BYTES {
                return Err(AcpError::FrameTooLarge {
                    size: cl,
                    limit: MAX_BODY_SIZE_BYTES,
                });
            }

            let body_start = pos + delim.len();
            let have_body = buffer.len() - body_start;
            if have_body < cl {
                let needed = cl - have_body;
                let mut rest = vec![0u8; needed];
                reader.read_exact(&mut rest).await?;
                buffer.extend_from_slice(&rest);
            }
            return parse_agtp_request(&buffer);
        }

        let mut chunk = [0u8; 512];
        let n = reader.read(&mut chunk).await?;
        if n == 0 {
            return Err(AcpError::Io(std::io::Error::new(
                std::io::ErrorKind::UnexpectedEof,
                "EOF reached before full AGTP header block",
            )));
        }
        buffer.extend_from_slice(&chunk[..n]);
        if buffer.len() > MAX_HEADER_SIZE_BYTES {
            return Err(AcpError::FrameTooLarge {
                size: buffer.len(),
                limit: MAX_HEADER_SIZE_BYTES,
            });
        }
    }
}

/// Asynchronously write an AGTPRequest to an output stream.
pub async fn write_agtp_request<W: AsyncWriteExt + Unpin>(
    writer: &mut W,
    req: &AgtpRequest,
) -> AcpResult<()> {
    let bytes = encode_agtp_request(req);
    writer.write_all(&bytes).await?;
    writer.flush().await?;
    Ok(())
}

/// Convert an ACP ProtocolFrame into an AgtpRequest.
pub fn frame_to_agtp_request(frame: &ProtocolFrame, uri: &str) -> AcpResult<AgtpRequest> {
    let mut req = AgtpRequest::new("QUERY", uri)?;
    req.headers
        .insert("Session-ID".to_string(), frame.frame_id.clone());
    req.headers.insert(
        "Content-Type".to_string(),
        "application/agtp+json".to_string(),
    );

    match frame.frame_type.as_str() {
        "ACP_HANDOFF_REQUEST" => {
            req.method = "DELEGATE".to_string();
            let env = frame.envelope.as_ref().ok_or_else(|| {
                AcpError::Validation("Missing envelope in ACP_HANDOFF_REQUEST".to_string())
            })?;
            req.headers
                .insert("Traceparent".to_string(), env.traceparent.clone());
            if let Some(ref d) = env.delegation_chain {
                req.headers
                    .insert("Principal-ID".to_string(), d.issuer.clone());
                req.headers
                    .insert("Agent-ID".to_string(), d.subject.clone());
                req.headers
                    .insert("Authority-Scope".to_string(), d.capabilities.join(","));
            }
            req.body = serde_json::to_vec(env)?;
        }
        "ACP_FOLD_REQUEST" => {
            req.method = "CONFIRM".to_string();
            let fold = frame.fold_payload.as_ref().ok_or_else(|| {
                AcpError::Validation("Missing fold_payload in ACP_FOLD_REQUEST".to_string())
            })?;
            req.body = serde_json::to_vec(fold)?;
        }
        "ACP_YIELD_REQUEST" => {
            req.method = "ESCALATE".to_string();
            let y = frame.yield_payload.as_ref().ok_or_else(|| {
                AcpError::Validation("Missing yield_payload in ACP_YIELD_REQUEST".to_string())
            })?;
            req.body = serde_json::to_vec(y)?;
        }
        "ACP_PROBE_REQUEST" => {
            req.method = "DISCOVER".to_string();
            if let Some(ref p) = frame.probe_payload {
                req.headers
                    .insert("Agent-ID".to_string(), p.agent_id.clone());
                req.body = serde_json::to_vec(p)?;
            }
        }
        "ACP_PREEMPT_REQUEST" => {
            req.method = "NOTIFY".to_string();
        }
        other => {
            return Err(AcpError::Validation(format!(
                "No AGTP request mapping for frame type: {}",
                other
            )));
        }
    }

    Ok(req)
}

/// Convert an AgtpRequest into an ACP ProtocolFrame.
pub fn agtp_request_to_frame(req: &AgtpRequest) -> AcpResult<ProtocolFrame> {
    let session_id = req.headers.get("Session-ID").cloned().unwrap_or_default();
    match req.method.as_str() {
        "DELEGATE" => {
            let env: EpistemicEnvelope = serde_json::from_slice(&req.body)?;
            let mut f = ProtocolFrame::new("ACP_HANDOFF_REQUEST");
            f.frame_id = session_id;
            f.envelope = Some(env);
            Ok(f)
        }
        "CONFIRM" => {
            let fold: FoldPayload = serde_json::from_slice(&req.body)?;
            let mut f = ProtocolFrame::new("ACP_FOLD_REQUEST");
            f.frame_id = session_id;
            f.fold_payload = Some(fold);
            Ok(f)
        }
        "ESCALATE" => {
            let y: YieldPayload = serde_json::from_slice(&req.body)?;
            let mut f = ProtocolFrame::new("ACP_YIELD_REQUEST");
            f.frame_id = session_id;
            f.yield_payload = Some(y);
            Ok(f)
        }
        "DISCOVER" => {
            let p: Option<ProbePayload> = if !req.body.is_empty() {
                Some(serde_json::from_slice(&req.body)?)
            } else {
                None
            };
            let mut f = ProtocolFrame::new("ACP_PROBE_REQUEST");
            f.frame_id = session_id;
            f.probe_payload = p;
            Ok(f)
        }
        "NOTIFY" => {
            let mut f = ProtocolFrame::new("ACP_PREEMPT_REQUEST");
            f.frame_id = session_id;
            Ok(f)
        }
        other => Err(AcpError::Validation(format!(
            "Unsupported AGTP method for ACP frame mapping: {}",
            other
        ))),
    }
}
