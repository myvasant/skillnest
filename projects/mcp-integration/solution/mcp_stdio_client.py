"""A tiny MCP client for the stdio transport: spawn a server, exchange newline-delimited JSON-RPC.

A real host (an IDE, a chat app) does the same thing: start the server as a subprocess, write one JSON
request per line to its stdin, read one JSON message per line from its stdout, match responses to
requests by ``id``, and close stdin to shut it down.

By default the client speaks the stateless revision 2026-07-28: every request carries ``_meta`` with the
protocol version and client capabilities. :meth:`McpStdioClient.connect` implements the backward-
compatibility probe from the stdio transport spec: try ``server/discover`` first; a recognised modern
error means "modern server, pick another version"; any other error means "legacy server", so fall back
to the ``initialize`` handshake.
"""

from __future__ import annotations

import itertools
import json
import queue
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, Any, Literal

PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
CLIENT_INFO: Mapping[str, str] = {"name": "groundwork-test-client", "version": "1.0.0"}
UNSUPPORTED_PROTOCOL_VERSION = -32022


class McpError(Exception):
    """The server answered a request with a JSON-RPC error."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class McpStdioClient:
    """Spawn ``server_path`` with the current Python interpreter and talk to it over stdio.

    ``timeout`` is a safety net so a broken server fails a test instead of hanging it; nothing relies
    on timing when the server works.
    """

    def __init__(self, server_path: str | Path, *, args: Sequence[str] = (), timeout: float = 10.0) -> None:
        self.timeout = timeout
        self.mode: Literal["modern", "legacy"] = "modern"
        self.protocol_version = PROTOCOL_VERSION
        self.stderr_lines: list[str] = []
        self._ids = itertools.count(1)
        self._inbox: queue.Queue[bytes | None] = queue.Queue()
        # The command is fixed (this interpreter + a server file we chose), never built from user input.
        self._process = subprocess.Popen(  # noqa: S603
            [sys.executable, "-u", str(server_path), *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self._process.stdout is not None and self._process.stderr is not None
        self._readers = [
            threading.Thread(target=self._pump, args=(self._process.stdout, self._inbox.put), daemon=True),
            threading.Thread(target=self._pump, args=(self._process.stderr, self._log), daemon=True),
        ]
        for reader in self._readers:
            reader.start()

    # ------------------------------------------------------------------ plumbing
    @staticmethod
    def _pump(stream: IO[bytes], deliver: Any) -> None:
        """Read lines from a pipe on a background thread (pipes block; tests must not)."""
        for line in iter(stream.readline, b""):
            deliver(line)
        deliver(None)

    def _log(self, line: bytes | None) -> None:
        if line is not None:
            self.stderr_lines.append(line.decode("utf-8", errors="replace").rstrip())

    def send(self, message: Mapping[str, Any]) -> None:
        """Write one message as one line."""
        self.send_raw_line(json.dumps(message, separators=(",", ":")))

    def send_raw_line(self, text: str) -> None:
        """Write any text plus a newline (tests use this to send malformed input)."""
        assert self._process.stdin is not None
        self._process.stdin.write(text.encode("utf-8") + b"\n")
        self._process.stdin.flush()

    def receive(self) -> dict[str, Any]:
        """The next message from the server's stdout, parsed.

        Take a line from the inbox queue (filled by the reader thread) with ``self.timeout``: raise
        ``TimeoutError`` if nothing arrives, ``ConnectionError`` if the reader saw end-of-file (``None``).
        """
        try:
            line = self._inbox.get(timeout=self.timeout)
        except queue.Empty:
            raise TimeoutError(f"no message from the server within {self.timeout} s") from None
        if line is None:
            raise ConnectionError("the server closed its output (did it crash? see stderr_lines)")
        return json.loads(line)

    # ------------------------------------------------------------------ JSON-RPC
    def meta(self) -> dict[str, Any]:
        """The per-request ``_meta`` fields of revision 2026-07-28."""
        return {
            "io.modelcontextprotocol/protocolVersion": self.protocol_version,
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": dict(CLIENT_INFO),
        }

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Send a request and wait for *its* response (skipping notifications and other ids).

        Ids come from ``self._ids`` (1, 2, 3...). In ``"modern"`` mode merge :meth:`meta` into
        ``params["_meta"]``; in ``"legacy"`` mode send the params as given. An error response raises
        :class:`McpError` (code, message, data); otherwise return the ``result`` object.
        """
        request_id = next(self._ids)
        body = dict(params or {})
        if self.mode == "modern":
            body["_meta"] = {**self.meta(), **body.get("_meta", {})}
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": body})
        while True:
            message = self.receive()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise McpError(error["code"], error["message"], error.get("data"))
            return message["result"]

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        """Send a notification (no id, no response)."""
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = dict(params)
        self.send(message)

    # ------------------------------------------------------------------ MCP operations
    def discover(self) -> dict[str, Any]:
        """``server/discover``: versions, capabilities and server info in one call."""
        return self.request("server/discover")

    def list_tools(self) -> list[dict[str, Any]]:
        """``tools/list``."""
        return self.request("tools/list")["tools"]

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """``tools/call``; the result may have ``isError: true`` (a tool execution error)."""
        return self.request("tools/call", {"name": name, "arguments": dict(arguments)})

    def initialize_legacy(self, protocol_version: str = LEGACY_PROTOCOL_VERSION) -> dict[str, Any]:
        """The 2025-11-25 handshake: ``initialize``, check the version, then ``notifications/initialized``.

        Switch to ``"legacy"`` mode first (no ``_meta``), send ``initialize`` with ``protocolVersion``,
        ``capabilities: {}`` and ``clientInfo``; if the server answers with a version this client does not
        speak, raise :class:`McpError`; otherwise send ``notifications/initialized`` and return the result.
        """
        self.mode = "legacy"
        result = self.request(
            "initialize",
            {"protocolVersion": protocol_version, "capabilities": {}, "clientInfo": dict(CLIENT_INFO)},
        )
        if result.get("protocolVersion") != LEGACY_PROTOCOL_VERSION:
            raise McpError(-32602, f"server chose unsupported protocol version {result.get('protocolVersion')!r}")
        self.protocol_version = result["protocolVersion"]
        self.notify("notifications/initialized")
        return result

    def connect(self) -> Literal["modern", "legacy"]:
        """Probe the server's era as the stdio spec recommends, and return it.

        Send ``server/discover``. Success -> ``"modern"``. A -32022 error -> the server is modern but wants
        another version: retry if ours is in ``data["supported"]``, else raise. Any other error -> the
        server is legacy: :meth:`initialize_legacy` and return ``"legacy"``.
        """
        try:
            info = self.discover()
        except McpError as error:
            if error.code != UNSUPPORTED_PROTOCOL_VERSION:
                self.initialize_legacy()
                return "legacy"
            supported = (error.data or {}).get("supported", [])
            if PROTOCOL_VERSION not in supported:
                raise McpError(error.code, f"no common protocol version (server supports {supported})") from None
            info = self.discover()
        if PROTOCOL_VERSION not in info.get("supportedVersions", []):
            raise McpError(-32602, "the server does not support this client's protocol version")
        return "modern"

    # ------------------------------------------------------------------ shutdown
    def close(self) -> int:
        """Close stdin (the spec's shutdown signal), wait for exit, kill if it hangs. Returns the exit code."""
        process = self._process
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        try:
            code = process.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            code = process.wait()
        for reader in self._readers:
            reader.join(timeout=self.timeout)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        return code

    def __enter__(self) -> McpStdioClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
