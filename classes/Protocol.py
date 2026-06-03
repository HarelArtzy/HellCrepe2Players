from __future__ import annotations

import logging
import pickle
import select
import socket
from contextlib import suppress


logger = logging.getLogger(__name__)


MAX_HEADER_BYTES = 12
MAX_FRAME_BYTES = 2_000_000


class Protocol:
    def __init__(self, sock: socket.socket):
        """Initialize a blocking TCP connection for framed messages."""
        self.sock = sock
        self.sock.setblocking(True)
        self.closed = False

    def send_message(self, payload: dict) -> None:
        """Serialize and send one pickled payload with len# framing."""
        body = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        header = f"{len(body)}#".encode("ascii")
        packet = header + body
        try:
            self.sock.sendall(packet)
        except OSError as e:
            self.closed = True
            logger.warning("Socket send failed: %s", e)
            raise ConnectionError(str(e)) from e

    def _recv_exactly(self, size: int) -> bytes:
        chunks: list[bytes] = []
        received = 0
        while received < size:
            try:
                chunk = self.sock.recv(size - received)
            except OSError as e:
                self.closed = True
                logger.warning("Socket receive failed: %s", e)
                raise ConnectionError(str(e)) from e
            if not chunk:
                self.closed = True
                raise ConnectionError("Socket closed while receiving data")
            chunks.append(chunk)
            received += len(chunk)
        return b"".join(chunks)

    def _recv_header(self) -> int:
        header = ""
        while True:
            try:
                ch = self.sock.recv(1).decode("ascii")
            except OSError as e:
                self.closed = True
                logger.warning("Socket receive failed: %s", e)
                raise ConnectionError(str(e)) from e
            if not ch:
                self.closed = True
                raise ConnectionError("Socket closed while reading header")
            if ch == "#":
                break
            header += ch
            if len(header) > MAX_HEADER_BYTES:
                self.closed = True
                raise ConnectionError("Invalid frame header length")

        if not header or not header.isdigit():
            self.closed = True
            raise ConnectionError("Invalid frame header digits")

        body_len = int(header)
        if body_len > MAX_FRAME_BYTES:
            self.closed = True
            raise ConnectionError("Frame too large")
        return body_len

    def read_message(self) -> dict:
        """Read one framed pickled dict message."""
        body_len = self._recv_header()
        body = self._recv_exactly(body_len)
        try:
            msg = pickle.loads(body)
        except Exception as e:
            raise ConnectionError(f"Invalid pickled payload: {e}") from e
        if not isinstance(msg, dict):
            raise ConnectionError("Unsupported payload type")
        return msg

    def get_messages(self) -> list[dict]:
        """Read all immediately available framed messages."""
        messages: list[dict] = []
        while not self.closed:
            readable, _, _ = select.select([self.sock], [], [], 0.0)
            if not readable:
                break
            messages.append(self.read_message())
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
