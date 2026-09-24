"""Wire protocol encoder, decoder, and stream framer for AGTP (draft-hood-independent-agtp).

Implements the HTTP-style AGTP/1.0 protocol floor with strict Content-Length framing,
agent intent methods, and structured agent headers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from acp.protocol.models import (
    EpistemicEnvelope,
    FoldPayload,
    ProbePayload,
    ProtocolFrame,
    YieldPayload,
)

CRLF: Final[bytes] = b"\r\n"
DOUBLE_CRLF: Final[bytes] = b"\r\n\r\n"
AGTP_VERSION: Final[str] = "AGTP/1.0"
MAX_HEADER_SIZE_BYTES: Final[int] = 64 * 1024  # 64 KB header cap
MAX_BODY_SIZE_BYTES: Final[int] = 16 * 1024 * 1024  # 16 MB body cap

AGTP_METHODS: Final[frozenset[str]] = frozenset(
    {
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
    }
)


@dataclass(frozen=True)
class AGTPRequest:
    """Represents an inbound or outbound AGTP/1.0 request."""

    method: str
    uri: str
    version: str = AGTP_VERSION
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def __post_init__(self) -> None:
        if self.method not in AGTP_METHODS:
            raise ValueError(f"Invalid or unrecognized AGTP method: {self.method}")


@dataclass(frozen=True)
class AGTPResponse:
    """Represents an inbound or outbound AGTP/1.0 response."""

    status_code: int
    reason_phrase: str
    version: str = AGTP_VERSION
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


def _serialize_header_block(headers: dict[str, str], body_len: int) -> bytes:
    """Serialize headers to normalized bytes, ensuring Content-Length is present."""
    norm_headers = {k.strip(): v.strip() for k, v in headers.items()}
    norm_headers["Content-Length"] = str(body_len)
    if "Content-Type" not in norm_headers and body_len > 0:
        norm_headers["Content-Type"] = "application/agtp+json"

    lines = [f"{k}: {v}".encode() for k, v in norm_headers.items()]
    return CRLF.join(lines) + DOUBLE_CRLF


def encode_agtp_request(req: AGTPRequest) -> bytes:
    """Serialize an AGTPRequest into wire-formatted bytes."""
    start_line = f"{req.method} {req.uri} {req.version}".encode() + CRLF
    headers_block = _serialize_header_block(req.headers, len(req.body))
    return start_line + headers_block + req.body


def encode_agtp_response(resp: AGTPResponse) -> bytes:
    """Serialize an AGTPResponse into wire-formatted bytes."""
    start_line = f"{resp.version} {resp.status_code} {resp.reason_phrase}".encode() + CRLF
    headers_block = _serialize_header_block(resp.headers, len(resp.body))
    return start_line + headers_block + resp.body


def _parse_raw_headers(header_lines: list[str]) -> dict[str, str]:
    """Parse raw header lines into key-value pairs."""
    headers: dict[str, str] = {}
    for line in header_lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        key, sep, val = line_clean.partition(":")
        if not sep:
            raise ValueError(f"Malformed AGTP header line: {line_clean}")
        headers[key.strip()] = val.strip()
    return headers


def parse_agtp_request(raw_bytes: bytes) -> AGTPRequest:
    """Parse raw bytes containing a full AGTP request."""
    head_bytes, sep, body = raw_bytes.partition(DOUBLE_CRLF)
    if not sep:
        raise ValueError("Missing header termination in AGTP request")

    head_str = head_bytes.decode("utf-8")
    lines = head_str.split("\r\n")
    start_line = lines[0].strip().split()
    if len(start_line) != 3:
        raise ValueError(f"Malformed AGTP request start line: {lines[0]}")

    method, uri, version = start_line
    headers = _parse_raw_headers(lines[1:])
    _validate_content_length(headers, len(body))
    return AGTPRequest(method=method, uri=uri, version=version, headers=headers, body=body)


def parse_agtp_response(raw_bytes: bytes) -> AGTPResponse:
    """Parse raw bytes containing a full AGTP response."""
    head_bytes, sep, body = raw_bytes.partition(DOUBLE_CRLF)
    if not sep:
        raise ValueError("Missing header termination in AGTP response")

    head_str = head_bytes.decode("utf-8")
    lines = head_str.split("\r\n")
    parts = lines[0].strip().split(maxsplit=2)
    if len(parts) < 2:
        raise ValueError(f"Malformed AGTP response status line: {lines[0]}")

    version = parts[0]
    status_code = int(parts[1])
    reason = parts[2] if len(parts) > 2 else ""
    headers = _parse_raw_headers(lines[1:])
    _validate_content_length(headers, len(body))
    return AGTPResponse(
        status_code=status_code, reason_phrase=reason, version=version, headers=headers, body=body
    )


def _validate_content_length(headers: dict[str, str], actual_body_len: int) -> None:
    """Verify that Content-Length header is present and matches the body byte length."""
    content_len_str = headers.get("Content-Length")
    if content_len_str is None:
        raise ValueError("AGTP wire format mandates explicit Content-Length header")
    expected_len = int(content_len_str)
    if expected_len != actual_body_len:
        raise ValueError(f"Content-Length mismatch: expected {expected_len}, got {actual_body_len}")


async def _read_header_block(reader: asyncio.StreamReader) -> bytes:
    """Read stream until DOUBLE_CRLF delimiter is encountered."""
    buffer = bytearray()
    while DOUBLE_CRLF not in buffer:
        chunk = await reader.read(512)
        if not chunk:
            raise EOFError("Connection closed before complete AGTP header block")
        buffer.extend(chunk)
        if len(buffer) > MAX_HEADER_SIZE_BYTES:
            raise ValueError(f"AGTP header block exceeds limit of {MAX_HEADER_SIZE_BYTES} bytes")
    return bytes(buffer)


async def read_agtp_request(reader: asyncio.StreamReader) -> AGTPRequest:
    """Read a single Content-Length framed AGTPRequest from an asyncio stream."""
    buffer = await _read_header_block(reader)
    head_bytes, _, remainder = buffer.partition(DOUBLE_CRLF)

    head_str = head_bytes.decode("utf-8")
    lines = head_str.split("\r\n")
    start_line = lines[0].strip().split()
    if len(start_line) != 3:
        raise ValueError(f"Malformed AGTP start line: {lines[0]}")

    method, uri, version = start_line
    headers = _parse_raw_headers(lines[1:])

    content_len = int(headers.get("Content-Length", "0"))
    if content_len > MAX_BODY_SIZE_BYTES:
        raise ValueError(f"Body size ({content_len}) exceeds maximum limit ({MAX_BODY_SIZE_BYTES})")

    needed = content_len - len(remainder)
    body = remainder + (await reader.readexactly(needed) if needed > 0 else b"")
    return AGTPRequest(method=method, uri=uri, version=version, headers=headers, body=body[:content_len])


async def read_agtp_response(reader: asyncio.StreamReader) -> AGTPResponse:
    """Read a single Content-Length framed AGTPResponse from an asyncio stream."""
    buffer = await _read_header_block(reader)
    head_bytes, _, remainder = buffer.partition(DOUBLE_CRLF)

    head_str = head_bytes.decode("utf-8")
    lines = head_str.split("\r\n")
    parts = lines[0].strip().split(maxsplit=2)
    if len(parts) < 2:
        raise ValueError(f"Malformed AGTP status line: {lines[0]}")

    version = parts[0]
    status_code = int(parts[1])
    reason = parts[2] if len(parts) > 2 else ""
    headers = _parse_raw_headers(lines[1:])

    content_len = int(headers.get("Content-Length", "0"))
    if content_len > MAX_BODY_SIZE_BYTES:
        raise ValueError(f"Body size ({content_len}) exceeds maximum limit ({MAX_BODY_SIZE_BYTES})")

    needed = content_len - len(remainder)
    body = remainder + (await reader.readexactly(needed) if needed > 0 else b"")
    return AGTPResponse(
        status_code=status_code,
        reason_phrase=reason,
        version=version,
        headers=headers,
        body=body[:content_len],
    )


def _build_delegate_request(frame: ProtocolFrame, uri: str, headers: dict[str, str]) -> AGTPRequest:
    if not frame.envelope:
        raise ValueError("Missing envelope in ACP_HANDOFF_REQUEST")
    env = frame.envelope
    headers["Traceparent"] = env.traceparent
    if env.delegation_chain:
        headers["Principal-ID"] = env.delegation_chain.issuer
        headers["Agent-ID"] = env.delegation_chain.subject
        headers["Authority-Scope"] = ",".join(env.delegation_chain.capabilities)
    return AGTPRequest(
        method="DELEGATE", uri=uri, headers=headers, body=env.model_dump_json().encode("utf-8")
    )


def _build_fold_request(frame: ProtocolFrame, uri: str, headers: dict[str, str]) -> AGTPRequest:
    if not frame.fold_payload:
        raise ValueError("Missing fold_payload in ACP_FOLD_REQUEST")
    return AGTPRequest(
        method="CONFIRM",
        uri=uri,
        headers=headers,
        body=frame.fold_payload.model_dump_json().encode("utf-8"),
    )


def _build_yield_request(frame: ProtocolFrame, uri: str, headers: dict[str, str]) -> AGTPRequest:
    if not frame.yield_payload:
        raise ValueError("Missing yield_payload in ACP_YIELD_REQUEST")
    return AGTPRequest(
        method="ESCALATE",
        uri=uri,
        headers=headers,
        body=frame.yield_payload.model_dump_json().encode("utf-8"),
    )


def _build_probe_request(frame: ProtocolFrame, uri: str, headers: dict[str, str]) -> AGTPRequest:
    body = b""
    if frame.probe_payload:
        headers["Agent-ID"] = frame.probe_payload.agent_id
        body = frame.probe_payload.model_dump_json().encode("utf-8")
    return AGTPRequest(method="DISCOVER", uri=uri, headers=headers, body=body)


def _build_preempt_request(_frame: ProtocolFrame, uri: str, headers: dict[str, str]) -> AGTPRequest:
    return AGTPRequest(method="NOTIFY", uri=uri, headers=headers, body=b"")


REQUEST_BUILDERS: dict[str, Callable[[ProtocolFrame, str, dict[str, str]], AGTPRequest]] = {
    "ACP_HANDOFF_REQUEST": _build_delegate_request,
    "ACP_FOLD_REQUEST": _build_fold_request,
    "ACP_YIELD_REQUEST": _build_yield_request,
    "ACP_PROBE_REQUEST": _build_probe_request,
    "ACP_PREEMPT_REQUEST": _build_preempt_request,
}


def frame_to_agtp_request(frame: ProtocolFrame, target_uri: str = "/v1/agent") -> AGTPRequest:
    """Convert an ACP ProtocolFrame into an AGTPRequest."""
    builder = REQUEST_BUILDERS.get(frame.frame_type)
    if not builder:
        raise ValueError(f"No AGTP request mapping for frame type: {frame.frame_type}")
    headers = {
        "Session-ID": frame.frame_id,
        "Content-Type": "application/agtp+json",
    }
    return builder(frame, target_uri, headers)


def _parse_delegate_request(req: AGTPRequest) -> ProtocolFrame:
    env = EpistemicEnvelope.model_validate_json(req.body.decode("utf-8"))
    return ProtocolFrame(
        frame_type="ACP_HANDOFF_REQUEST",
        frame_id=req.headers.get("Session-ID", ""),
        envelope=env,
    )


def _parse_confirm_request(req: AGTPRequest) -> ProtocolFrame:
    fold = FoldPayload.model_validate_json(req.body.decode("utf-8"))
    return ProtocolFrame(
        frame_type="ACP_FOLD_REQUEST",
        frame_id=req.headers.get("Session-ID", ""),
        fold_payload=fold,
    )


def _parse_escalate_request(req: AGTPRequest) -> ProtocolFrame:
    yield_p = YieldPayload.model_validate_json(req.body.decode("utf-8"))
    return ProtocolFrame(
        frame_type="ACP_YIELD_REQUEST",
        frame_id=req.headers.get("Session-ID", ""),
        yield_payload=yield_p,
    )


def _parse_discover_request(req: AGTPRequest) -> ProtocolFrame:
    probe = ProbePayload.model_validate_json(req.body.decode("utf-8")) if req.body else None
    return ProtocolFrame(
        frame_type="ACP_PROBE_REQUEST",
        frame_id=req.headers.get("Session-ID", ""),
        probe_payload=probe,
    )


def _parse_notify_request(req: AGTPRequest) -> ProtocolFrame:
    return ProtocolFrame(
        frame_type="ACP_PREEMPT_REQUEST",
        frame_id=req.headers.get("Session-ID", ""),
    )


REQUEST_PARSERS: dict[str, Callable[[AGTPRequest], ProtocolFrame]] = {
    "DELEGATE": _parse_delegate_request,
    "CONFIRM": _parse_confirm_request,
    "ESCALATE": _parse_escalate_request,
    "DISCOVER": _parse_discover_request,
    "NOTIFY": _parse_notify_request,
}


def agtp_request_to_frame(req: AGTPRequest) -> ProtocolFrame:
    """Convert an AGTPRequest into an ACP ProtocolFrame."""
    parser = REQUEST_PARSERS.get(req.method)
    if not parser:
        raise ValueError(f"Unsupported AGTP method for ACP frame mapping: {req.method}")
    return parser(req)


def _build_fold_response(frame: ProtocolFrame, headers: dict[str, str]) -> AGTPResponse:
    if not frame.fold_payload:
        raise ValueError("Missing fold_payload in ACP_FOLD_RESPONSE")
    return AGTPResponse(
        status_code=200,
        reason_phrase="OK",
        headers=headers,
        body=frame.fold_payload.model_dump_json().encode("utf-8"),
    )


def _build_yield_response(frame: ProtocolFrame, headers: dict[str, str]) -> AGTPResponse:
    if not frame.yield_payload:
        raise ValueError("Missing yield_payload in ACP_YIELD_RESPONSE")
    return AGTPResponse(
        status_code=422,
        reason_phrase="Unprocessable Entity",
        headers=headers,
        body=frame.yield_payload.model_dump_json().encode("utf-8"),
    )


def _build_probe_response(frame: ProtocolFrame, headers: dict[str, str]) -> AGTPResponse:
    body = frame.probe_payload.model_dump_json().encode("utf-8") if frame.probe_payload else b""
    return AGTPResponse(status_code=200, reason_phrase="OK", headers=headers, body=body)


def _build_handoff_response(_frame: ProtocolFrame, headers: dict[str, str]) -> AGTPResponse:
    return AGTPResponse(status_code=202, reason_phrase="Accepted", headers=headers, body=b"")


RESPONSE_BUILDERS: dict[str, Callable[[ProtocolFrame, dict[str, str]], AGTPResponse]] = {
    "ACP_FOLD_RESPONSE": _build_fold_response,
    "ACP_YIELD_RESPONSE": _build_yield_response,
    "ACP_PROBE_RESPONSE": _build_probe_response,
    "ACP_HANDOFF_RESPONSE": _build_handoff_response,
}


def frame_to_agtp_response(frame: ProtocolFrame) -> AGTPResponse:
    """Convert an ACP ProtocolFrame into an AGTPResponse."""
    builder = RESPONSE_BUILDERS.get(frame.frame_type)
    if not builder:
        raise ValueError(f"No AGTP response mapping for frame type: {frame.frame_type}")
    headers = {
        "Session-ID": frame.frame_id,
        "Content-Type": "application/agtp+json",
    }
    return builder(frame, headers)


def _parse_200_response(resp: AGTPResponse, session_id: str) -> ProtocolFrame:
    body_str = resp.body.decode("utf-8")
    try:
        fold = FoldPayload.model_validate_json(body_str)
        return ProtocolFrame(frame_type="ACP_FOLD_RESPONSE", frame_id=session_id, fold_payload=fold)
    except Exception:
        probe = ProbePayload.model_validate_json(body_str)
        return ProtocolFrame(frame_type="ACP_PROBE_RESPONSE", frame_id=session_id, probe_payload=probe)


def agtp_response_to_frame(resp: AGTPResponse) -> ProtocolFrame:
    """Convert an AGTPResponse into an ACP ProtocolFrame."""
    session_id = resp.headers.get("Session-ID", "")
    if resp.status_code == 202:
        return ProtocolFrame(frame_type="ACP_HANDOFF_RESPONSE", frame_id=session_id)
    if resp.status_code == 422:
        yield_p = YieldPayload.model_validate_json(resp.body.decode("utf-8"))
        return ProtocolFrame(frame_type="ACP_YIELD_RESPONSE", frame_id=session_id, yield_payload=yield_p)
    if resp.status_code == 200:
        return _parse_200_response(resp, session_id)
    raise ValueError(f"Unsupported AGTP response status code: {resp.status_code}")
