from __future__ import annotations

import json
import logging
import socket
from contextlib import suppress


logger = logging.getLogger(__name__)


class TcpJsonConnection:
    def __init__(self, sock: socket.socket):
        """Initialize a non-blocking TCP connection with internal buffers."""
        self.sock = sock
        self.sock.setblocking(False)
        self.closed = False
        self._recv_buffer = b""
        self._send_buffer = b""

    def queue_json(self, payload: dict) -> None:
        """Serialize and queue one JSON payload for transmission."""
        self._send_buffer += (json.dumps(payload,
                              separators=(",", ":")) + "\n").encode("utf-8")

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

    def poll_messages(self) -> list[str]:
        """Read bytes and return decoded newline-delimited messages."""
        messages: list[str] = []
        while not self.closed:
            try:
                chunk = self.sock.recv(4096)
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
            newline_idx = self._recv_buffer.find(b"\n")
            if newline_idx < 0:
                break
            line = self._recv_buffer[:newline_idx]
            self._recv_buffer = self._recv_buffer[newline_idx + 1:]
            if line:
                messages.append(line.decode("utf-8", errors="replace"))
        return messages

    def close(self) -> None:
        """Close the underlying socket and mark the connection as closed."""
        if self.closed and self.sock.fileno() < 0:
            return
        with suppress(OSError):
            self.sock.shutdown(socket.SHUT_RDWR)
        with suppress(OSError):
            self.sock.close()
        self.closed = True
