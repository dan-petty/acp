"""Transport adapters and length-prefixed stream framing for ATP.

Implements in-memory duplex channels for subagent testing and asynchronous
Unix Domain Socket transports for local process-isolated IPC.
"""

from __future__ import annotations

import asyncio
import json
import struct
from abc import ABC, abstractmethod
from typing import Final

from atp.protocol.models import ProtocolFrame

# 4-byte big-endian unsigned integer prefix
_HEADER_STRUCT: Final[struct.Struct] = struct.Struct("!I")
_HEADER_SIZE: Final[int] = _HEADER_STRUCT.size
MAX_FRAME_SIZE_BYTES: Final[int] = 16 * 1024 * 1024  # 16 MB boundary limit


class FrameSerializer:
    """Serializes and deserializes ProtocolFrames with length-prefixed headers."""

    @staticmethod
    def encode_frame(frame: ProtocolFrame) -> bytes:
        """Encode a ProtocolFrame to length-prefixed bytes."""
        payload_bytes = frame.model_dump_json().encode("utf-8")
        size = len(payload_bytes)
        if size > MAX_FRAME_SIZE_BYTES:
            raise ValueError(f"Frame size ({size} bytes) exceeds limit of {MAX_FRAME_SIZE_BYTES} bytes.")
        return _HEADER_STRUCT.pack(size) + payload_bytes

    @staticmethod
    async def read_frame(reader: asyncio.StreamReader) -> ProtocolFrame:
        """Read a single length-prefixed frame from an asyncio StreamReader."""
        header = await reader.readexactly(_HEADER_SIZE)
        (size,) = _HEADER_STRUCT.unpack(header)
        if size > MAX_FRAME_SIZE_BYTES:
            raise ValueError(f"Received frame size ({size} bytes) exceeds safety limit.")

        payload_bytes = await reader.readexactly(size)
        raw_json = json.loads(payload_bytes.decode("utf-8"))
        return ProtocolFrame.model_validate(raw_json)


class ATPTransport(ABC):
    """Abstract base transport interface for ATP communications."""

    @abstractmethod
    async def send_frame(self, frame: ProtocolFrame) -> None:
        """Send a protocol frame across the transport."""

    @abstractmethod
    async def receive_frame(self) -> ProtocolFrame:
        """Receive a protocol frame from the transport."""

    @abstractmethod
    async def close(self) -> None:
        """Gracefully terminate transport resources."""


class MemoryTransport(ATPTransport):
    """In-memory duplex queue transport for high-speed subagent IPC."""

    def __init__(
        self,
        inbound: asyncio.Queue[ProtocolFrame],
        outbound: asyncio.Queue[ProtocolFrame],
    ) -> None:
        self._inbound: asyncio.Queue[ProtocolFrame] = inbound
        self._outbound: asyncio.Queue[ProtocolFrame] = outbound
        self._closed: bool = False

    @classmethod
    def create_pair(cls) -> tuple[MemoryTransport, MemoryTransport]:
        """Create a connected pair of in-memory transports."""
        queue_a: asyncio.Queue[ProtocolFrame] = asyncio.Queue()
        queue_b: asyncio.Queue[ProtocolFrame] = asyncio.Queue()
        client = cls(inbound=queue_b, outbound=queue_a)
        server = cls(inbound=queue_a, outbound=queue_b)
        return client, server

    async def send_frame(self, frame: ProtocolFrame) -> None:
        """Push frame into outbound queue."""
        if self._closed:
            raise RuntimeError("Cannot send on closed MemoryTransport.")
        await self._outbound.put(frame)

    async def receive_frame(self) -> ProtocolFrame:
        """Await and pop frame from inbound queue."""
        if self._closed and self._inbound.empty():
            raise RuntimeError("Cannot receive on closed MemoryTransport.")
        return await self._inbound.get()

    async def close(self) -> None:
        """Mark transport as closed."""
        self._closed = True


class UnixSocketTransport(ATPTransport):
    """Asynchronous Unix Domain Socket stream transport."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader: asyncio.StreamReader = reader
        self._writer: asyncio.StreamWriter = writer

    @classmethod
    async def connect(cls, socket_path: str) -> UnixSocketTransport:
        """Connect to an existing ATP Unix Domain Socket server."""
        reader, writer = await asyncio.open_unix_connection(socket_path)
        return cls(reader, writer)

    async def send_frame(self, frame: ProtocolFrame) -> None:
        """Serialize and transmit frame over stream."""
        data = FrameSerializer.encode_frame(frame)
        self._writer.write(data)
        await self._writer.drain()

    async def receive_frame(self) -> ProtocolFrame:
        """Read and decode frame from stream."""
        return await FrameSerializer.read_frame(self._reader)

    async def close(self) -> None:
        """Close socket stream writer."""
        self._writer.close()
        await self._writer.wait_closed()
