//! Asynchronous transport adapters and length-prefixed stream framing for ATP.

pub mod agtp;

use bytes::{Buf, BufMut, BytesMut};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::sync::mpsc;
use tokio_util::codec::{Decoder, Encoder};

use crate::error::{AcpError, AcpResult};
use crate::models::ProtocolFrame;

/// Maximum allowable frame size in bytes (16 MB) to prevent unbounded memory allocation.
pub const MAX_FRAME_SIZE_BYTES: usize = 16 * 1024 * 1024; // 16 MB

/// Tokio codec for length-prefixed JSON protocol frames.
#[derive(Debug, Default)]
pub struct ProtocolFrameCodec;

impl Decoder for ProtocolFrameCodec {
    type Item = ProtocolFrame;
    type Error = AcpError;

    fn decode(&mut self, src: &mut BytesMut) -> Result<Option<Self::Item>, Self::Error> {
        if src.len() < 4 {
            return Ok(None);
        }

        let mut length_bytes = [0u8; 4];
        length_bytes.copy_from_slice(&src[..4]);
        let length = u32::from_be_bytes(length_bytes) as usize;

        if length > MAX_FRAME_SIZE_BYTES {
            return Err(AcpError::FrameTooLarge {
                size: length,
                limit: MAX_FRAME_SIZE_BYTES,
            });
        }

        if src.len() < 4 + length {
            src.reserve(4 + length - src.len());
            return Ok(None);
        }

        src.advance(4);
        let payload = src.split_to(length);
        let frame: ProtocolFrame = serde_json::from_slice(&payload)?;
        Ok(Some(frame))
    }
}

impl Encoder<ProtocolFrame> for ProtocolFrameCodec {
    type Error = AcpError;

    fn encode(&mut self, item: ProtocolFrame, dst: &mut BytesMut) -> Result<(), Self::Error> {
        let json_bytes = serde_json::to_vec(&item)?;
        let length = json_bytes.len();

        if length > MAX_FRAME_SIZE_BYTES {
            return Err(AcpError::FrameTooLarge {
                size: length,
                limit: MAX_FRAME_SIZE_BYTES,
            });
        }

        dst.reserve(4 + length);
        dst.put_u32(length as u32);
        dst.put_slice(&json_bytes);
        Ok(())
    }
}

/// In-memory bidirectional message channel for high-speed subagent IPC.
pub struct MemoryTransport {
    sender: mpsc::Sender<ProtocolFrame>,
    receiver: mpsc::Receiver<ProtocolFrame>,
}

impl MemoryTransport {
    /// Create a paired duplex channel.
    pub fn pair(buffer: usize) -> (Self, Self) {
        let (tx_a, rx_a) = mpsc::channel(buffer);
        let (tx_b, rx_b) = mpsc::channel(buffer);

        let transport_a = Self {
            sender: tx_a,
            receiver: rx_b,
        };
        let transport_b = Self {
            sender: tx_b,
            receiver: rx_a,
        };
        (transport_a, transport_b)
    }

    /// Send a protocol frame.
    pub async fn send(&self, frame: ProtocolFrame) -> AcpResult<()> {
        self.sender
            .send(frame)
            .await
            .map_err(|e| AcpError::Io(std::io::Error::new(std::io::ErrorKind::BrokenPipe, e)))
    }

    /// Receive the next protocol frame.
    pub async fn receive(&mut self) -> Option<ProtocolFrame> {
        self.receiver.recv().await
    }
}

/// Send a length-prefixed frame over an async stream.
pub async fn write_frame<W: AsyncWriteExt + Unpin>(
    writer: &mut W,
    frame: &ProtocolFrame,
) -> AcpResult<()> {
    let payload = serde_json::to_vec(frame)?;
    let length = payload.len();
    if length > MAX_FRAME_SIZE_BYTES {
        return Err(AcpError::FrameTooLarge {
            size: length,
            limit: MAX_FRAME_SIZE_BYTES,
        });
    }
    writer.write_all(&(length as u32).to_be_bytes()).await?;
    writer.write_all(&payload).await?;
    writer.flush().await?;
    Ok(())
}

/// Read a length-prefixed frame from an async stream.
pub async fn read_frame<R: AsyncReadExt + Unpin>(reader: &mut R) -> AcpResult<ProtocolFrame> {
    let mut header = [0u8; 4];
    reader.read_exact(&mut header).await?;
    let length = u32::from_be_bytes(header) as usize;
    if length > MAX_FRAME_SIZE_BYTES {
        return Err(AcpError::FrameTooLarge {
            size: length,
            limit: MAX_FRAME_SIZE_BYTES,
        });
    }
    let mut buf = vec![0u8; length];
    reader.read_exact(&mut buf).await?;
    let frame: ProtocolFrame = serde_json::from_slice(&buf)?;
    Ok(frame)
}
