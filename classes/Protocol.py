from __future__ import annotations

import logging
import pickle
import socket
from contextlib import suppress


logger = logging.getLogger(__name__)


MAX_HEADER_BYTES = 12
MAX_FRAME_BYTES = 2_000_000


class Protocol:
    def __init__(self, sock: socket.socket):
        """Initialize a non-blocking TCP connection with internal buffers."""
        self.sock = sock
        self.sock.setblocking(False)
        self.closed = False
        self._recv_buffer = b""
        self._send_buffer = b""

    def queue_message(self, payload: dict) -> None:
        """Serialize and queue one pickled payload for transmission."""
        body = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        header = f"{len(body)}#".encode("ascii")
        self._send_buffer += header + body

    def flush(self) -> None:
        """Send queued bytes until blocked or fully flushed."""
        while self._send_buffer and not self.closed:
            try:
                sent = self.sock.send(self._send_buffer)
            except (BlockingIOError, InterruptedError):
                break
            except OSError as exc:
                self.closed = True
                logger.warning("Socket send failed: %s", exc)
                raise ConnectionError(str(exc)) from exc
            if sent <= 0:
                self.closed = True
                logger.warning("Socket closed while sending queued data")
                raise ConnectionError("Socket closed while sending")
            self._send_buffer = self._send_buffer[sent:]

    def poll_messages(self) -> list[dict]:
        """Read bytes and return decoded length-prefixed pickled messages."""
        messages: list[dict] = []
        while not self.closed:
            try:
                chunk = self.sock.recv(self._next_read_size())
            except (BlockingIOError, InterruptedError):
                break
            except OSError as exc:
                self.closed = True
                logger.warning("Socket receive failed: %s", exc)
                raise ConnectionError(str(exc)) from exc
            if not chunk:
                self.closed = True
                logger.info("Socket closed by remote peer")
                break
            self._recv_buffer += chunk

        while True:
            sep_idx = self._recv_buffer.find(b"#")
            if sep_idx < 0:
                if len(self._recv_buffer) > MAX_HEADER_BYTES:
                    self.closed = True
                    raise ConnectionError("Invalid frame header (missing '#')")
                break

            if sep_idx == 0 or sep_idx > MAX_HEADER_BYTES:
                self.closed = True
                raise ConnectionError("Invalid frame header length")

            header = self._recv_buffer[:sep_idx]
            if not header.isdigit():
                self.closed = True
                raise ConnectionError("Invalid frame header digits")

            body_len = int(header)
            if body_len > MAX_FRAME_BYTES:
                self.closed = True
                raise ConnectionError("Frame too large")

            frame_end = sep_idx + 1 + body_len
            if len(self._recv_buffer) < frame_end:
                break

            body = self._recv_buffer[sep_idx + 1:frame_end]
            self._recv_buffer = self._recv_buffer[frame_end:]
            try:
                msg = pickle.loads(body)
            except Exception:
                logger.warning("Failed to unpickle inbound frame")
                continue
            if not isinstance(msg, dict):
                logger.warning(
                    "Discarded inbound frame with unsupported payload type: %s",
                    type(msg).__name__,
                )
                continue
            messages.append(msg)
        return messages

    def _next_read_size(self) -> int:
        """Choose a recv size based on current frame parsing progress."""
        sep_idx = self._recv_buffer.find(b"#")
        if sep_idx < 0:
            return 1
        if sep_idx == 0 or sep_idx > MAX_HEADER_BYTES:
            return 1
        header = self._recv_buffer[:sep_idx]
        if not header.isdigit():
            return 1
        body_len = int(header)
        if body_len > MAX_FRAME_BYTES:
            return 1
        frame_end = sep_idx + 1 + body_len
        remaining = frame_end - len(self._recv_buffer)
        return max(1, remaining)

    def close(self) -> None:
        """Close the underlying socket and mark the connection as closed."""
        if self.closed and self.sock.fileno() < 0:
            return
        with suppress(OSError):
            self.sock.shutdown(socket.SHUT_RDWR)
        with suppress(OSError):
            self.sock.close()
        self.closed = True
