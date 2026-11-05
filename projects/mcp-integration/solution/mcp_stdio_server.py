"""A minimal Model Context Protocol (MCP) server over stdio, written by hand — no SDK.

MCP lets an AI application (the *host*, through a *client*) discover and call tools offered by a
*server*. On the wire it is JSON-RPC 2.0. With the **stdio transport** the client starts the server as
a subprocess and they exchange one JSON message per line: requests on the server's stdin, responses on
its stdout; anything else the server wants to say goes to stderr.

This server follows the MCP specification revision **2026-07-28**
(https://modelcontextprotocol.io/specification/2026-07-28), which made the protocol **stateless**:
there is no handshake. Every request carries its protocol version and the client's capabilities in
``params._meta``::

    {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {}}}}

and every result says what kind of result it is (``"resultType": "complete"``). ``server/discover``
reports the supported versions and capabilities. Earlier revisions (2025-11-25 and before) used an
``initialize`` request plus a ``notifications/initialized`` notification to open a session; this
server also accepts that *legacy* handshake, which makes it "dual-era" (milestone 5).

Two safe, read-only, deterministic tools are exposed: ``convert_temperature`` and ``word_stats``.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, BinaryIO

# ==================================================================================================
# Protocol constants (from the specification)
# ==================================================================================================

JSONRPC_VERSION = "2.0"
MODERN_VERSIONS: tuple[str, ...] = ("2026-07-28",)  # per-request _meta, no handshake
LEGACY_VERSIONS: tuple[str, ...] = ("2025-11-25",)  # initialize handshake (dual-era support)

META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

# JSON-RPC 2.0 standard error codes, and the MCP-defined code for an unsupported protocol version.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
UNSUPPORTED_PROTOCOL_VERSION = -32022

SERVER_INFO: Mapping[str, str] = {"name": "groundwork-tools", "version": "1.0.0"}
INSTRUCTIONS = "Two read-only utilities: convert_temperature and word_stats. Both are deterministic."
LIST_TTL_MS = 300_000
MAX_LINE_BYTES = 1_000_000


class JsonRpcError(Exception):
    """A protocol-level error, sent back as a JSON-RPC ``error`` object."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class ToolExecutionError(Exception):
    """An error *inside* a tool (bad value, business rule). Reported as a result with ``isError: true``."""


# ==================================================================================================
# Milestone 1: JSON-RPC messages
# ==================================================================================================


def error_response(request_id: str | int | None, code: int, message: str, data: Any = None) -> dict[str, Any]:
    """A JSON-RPC error response. ``id`` is ``None`` when the request's id could not be read."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


def result_response(request_id: str | int, result: Mapping[str, Any]) -> dict[str, Any]:
    """A JSON-RPC success response."""
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": dict(result)}


def is_valid_id(value: Any) -> bool:
    """MCP request ids are strings or integers — never ``null``, booleans or fractions."""
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def encode_message(message: Mapping[str, Any]) -> str:
    """One line of JSON. ``json.dumps`` escapes newlines inside strings, so the line has none."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


# ==================================================================================================
# Milestone 3: tools and argument validation
# ==================================================================================================

TEMPERATURE_UNITS = ("celsius", "fahrenheit", "kelvin")
MAX_TEXT_LENGTH = 10_000


def validate_against_schema(schema: Mapping[str, Any], value: Any, path: str = "arguments") -> list[str]:
    """Check ``value`` against a JSON Schema subset; return readable problems (empty list = valid).

    Supported keywords: ``type`` (object, string, number, integer, boolean), ``properties``,
    ``required``, ``additionalProperties: false``, ``enum``, ``minLength``/``maxLength``,
    ``minimum``/``maximum``. JSON types, not Python types: ``true`` is not a number.

    Message formats (``path`` grows like ``arguments.value``): ``"{path}: expected integer, got number"``
    (stop checking that value after a type mismatch; see :func:`json_type`), ``"{path}: must be one of
    a, b"``, ``"{path}: shorter than N characters"``, ``"{path}: longer than N characters"``,
    ``"{path}: less than N"``, ``"{path}: greater than N"``, ``"{path}: missing required property 'x'"``,
    ``"{path}: unexpected property 'x'"``.
    """
    expected = schema.get("type")
    checks: Mapping[str, Callable[[Any], bool]] = {
        "object": lambda v: isinstance(v, dict),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    }
    if expected in checks and not checks[expected](value):
        return [f"{path}: expected {expected}, got {json_type(value)}"]
    problems: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: must be one of {', '.join(map(str, schema['enum']))}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            problems.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append(f"{path}: longer than {schema['maxLength']} characters")
    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path}: less than {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path}: greater than {schema['maximum']}")
    if isinstance(value, dict):
        properties: Mapping[str, Any] = schema.get("properties", {})
        problems += [f"{path}: missing required property {n!r}" for n in schema.get("required", []) if n not in value]
        for name, item in value.items():
            if name in properties:
                problems += validate_against_schema(properties[name], item, f"{path}.{name}")
            elif schema.get("additionalProperties") is False:
                problems.append(f"{path}: unexpected property {name!r}")
    return problems


def json_type(value: Any) -> str:
    """The JSON name of a Python value's type."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "array" if isinstance(value, list) else "object"


def convert_temperature(value: float, from_unit: str, to_unit: str) -> dict[str, Any]:
    """Convert via kelvin; refuse temperatures below absolute zero. Rounded to 2 decimals."""
    to_kelvin = {"celsius": lambda v: v + 273.15, "fahrenheit": lambda v: (v - 32) * 5 / 9 + 273.15, "kelvin": float}
    from_kelvin = {"celsius": lambda k: k - 273.15, "fahrenheit": lambda k: (k - 273.15) * 9 / 5 + 32, "kelvin": float}
    kelvin = to_kelvin[from_unit](value)
    if kelvin < 0:
        raise ToolExecutionError(f"{value} {from_unit} is below absolute zero; use a value of at least 0 kelvin")
    return {"value": round(from_kelvin[to_unit](kelvin), 2), "unit": to_unit}


def word_stats(text: str) -> dict[str, Any]:
    """Count characters, words (whitespace-separated) and lines."""
    return {"characters": len(text), "words": len(text.split()), "lines": len(text.splitlines())}


@dataclass(frozen=True)
class ToolDefinition:
    """A tool as MCP describes it, plus the Python function that implements it."""

    name: str
    title: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    handler: Callable[..., Mapping[str, Any]]
    annotations: Mapping[str, Any] = field(default_factory=lambda: {"readOnlyHint": True, "openWorldHint": False})

    def describe(self) -> dict[str, Any]:
        """The ``Tool`` object returned by ``tools/list``."""
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
            "outputSchema": dict(self.output_schema),
            "annotations": dict(self.annotations),
        }


def default_tools() -> tuple[ToolDefinition, ...]:
    """The two safe tools this server exposes."""
    unit = {"type": "string", "enum": list(TEMPERATURE_UNITS)}
    return (
        ToolDefinition(
            name="convert_temperature",
            title="Temperature converter",
            description="Convert a temperature between celsius, fahrenheit and kelvin.",
            input_schema={
                "type": "object",
                "properties": {
                    "value": {"type": "number", "description": "The temperature to convert."},
                    "from_unit": {**unit, "description": "Unit of the value."},
                    "to_unit": {**unit, "description": "Unit to convert to."},
                },
                "required": ["value", "from_unit", "to_unit"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {"value": {"type": "number"}, "unit": {"type": "string"}},
                "required": ["value", "unit"],
            },
            handler=convert_temperature,
        ),
        ToolDefinition(
            name="word_stats",
            title="Word statistics",
            description="Count the characters, words and lines in a text.",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string", "maxLength": MAX_TEXT_LENGTH}},
                "required": ["text"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {k: {"type": "integer"} for k in ("characters", "words", "lines")},
                "required": ["characters", "words", "lines"],
            },
            handler=word_stats,
        ),
    )


# ==================================================================================================
# Milestones 1-3 and 5: the server
# ==================================================================================================


def check_request_meta(meta: Any) -> str:
    """Validate the per-request ``_meta`` of revision 2026-07-28 and return the protocol version.

    Both ``protocolVersion`` and ``clientCapabilities`` are required (else -32602 Invalid params);
    ``clientInfo`` is optional but must be ``{name, version}`` if present. A version this server does
    not implement gives -32022 with ``data: {supported, requested}`` so the client can retry.
    """
    if not isinstance(meta, dict):
        raise JsonRpcError(INVALID_PARAMS, "params._meta must be an object")
    version = meta.get(META_PROTOCOL_VERSION)
    if not isinstance(version, str):
        raise JsonRpcError(INVALID_PARAMS, f"params._meta is missing {META_PROTOCOL_VERSION!r} (a string)")
    if not isinstance(meta.get(META_CLIENT_CAPABILITIES), dict):
        raise JsonRpcError(INVALID_PARAMS, f"params._meta is missing {META_CLIENT_CAPABILITIES!r} (an object)")
    info = meta.get(META_CLIENT_INFO)
    if info is not None and not (
        isinstance(info, dict) and isinstance(info.get("name"), str) and isinstance(info.get("version"), str)
    ):
        raise JsonRpcError(INVALID_PARAMS, f"{META_CLIENT_INFO!r} must have string 'name' and 'version'")
    if version not in MODERN_VERSIONS:
        raise JsonRpcError(
            UNSUPPORTED_PROTOCOL_VERSION,
            "Unsupported protocol version",
            {"supported": list(MODERN_VERSIONS), "requested": version},
        )
    return version


def is_modern_request(params: Mapping[str, Any]) -> bool:
    """A request is "modern" when its ``_meta`` carries the per-request protocol fields."""
    meta = params.get("_meta")
    return isinstance(meta, dict) and (META_PROTOCOL_VERSION in meta or META_CLIENT_CAPABILITIES in meta)


class McpServer:
    """Turns incoming JSON-RPC messages into responses. Transport-agnostic: see :func:`serve` for stdio.

    The only state is the optional legacy session (milestone 5); modern requests are handled
    statelessly, as revision 2026-07-28 requires.
    """

    def __init__(
        self,
        tools: Sequence[ToolDefinition] | None = None,
        *,
        modern: bool = True,
        legacy: bool = True,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.tools = {tool.name: tool for tool in (tools if tools is not None else default_tools())}
        self.modern = modern
        self.legacy = legacy
        self.log = log or (lambda message: None)
        self.legacy_version: str | None = None
        self.legacy_initialized = False

    # ------------------------------------------------------------------ framing and envelope
    def handle_line(self, line: str) -> str | None:
        """Handle one line from the transport; return the response line, or ``None`` for notifications."""
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            return encode_message(error_response(None, PARSE_ERROR, f"Parse error: {exc.msg}"))
        response = self.handle_message(message)
        return None if response is None else encode_message(response)

    def handle_message(self, message: Any) -> dict[str, Any] | None:
        """Validate the JSON-RPC envelope, then dispatch a request or a notification.

        * a list (batch) or a non-object -> -32600 with id ``None`` (MCP does not support batches);
        * an ``id`` that is present but not a string/integer -> -32600 with id ``None``;
        * ``jsonrpc`` not ``"2.0"`` or ``method`` not a non-empty string -> -32600 (with the id if valid);
        * no ``id`` -> a notification: handle it and return ``None`` (never a response);
        * ``params`` not an object -> -32602; :class:`JsonRpcError` -> its code/message/data;
        * any other exception -> -32603 ``"Internal error"`` (details only to ``self.log``).
        """
        if isinstance(message, list):
            return error_response(None, INVALID_REQUEST, "Invalid Request: batches are not supported")
        if not isinstance(message, dict):
            return error_response(None, INVALID_REQUEST, "Invalid Request: a message must be a JSON object")
        has_id = "id" in message
        request_id = message.get("id") if has_id and is_valid_id(message.get("id")) else None
        if has_id and request_id is None:
            return error_response(None, INVALID_REQUEST, "Invalid Request: id must be a string or an integer")
        if message.get("jsonrpc") != JSONRPC_VERSION:
            return error_response(request_id, INVALID_REQUEST, 'Invalid Request: "jsonrpc" must be "2.0"')
        method = message.get("method")
        if not isinstance(method, str) or not method:
            return error_response(request_id, INVALID_REQUEST, 'Invalid Request: "method" must be a string')
        params = message.get("params", {})
        if not has_id:
            self._handle_notification(method, params)
            return None
        assert request_id is not None
        try:
            if not isinstance(params, dict):
                raise JsonRpcError(INVALID_PARAMS, "params must be an object")
            return result_response(request_id, self._handle_request(method, params))
        except JsonRpcError as exc:
            return error_response(request_id, exc.code, exc.message, exc.data)
        except Exception as exc:  # a bug: never leak a traceback to the client
            self.log(f"internal error in {method}: {type(exc).__name__}: {exc}")
            return error_response(request_id, INTERNAL_ERROR, "Internal error")

    def _handle_notification(self, method: str, params: Any) -> None:
        """Notifications never get a response. Unknown ones are ignored."""
        if method == "notifications/initialized" and self.legacy_version is not None:
            self.legacy_initialized = True
        self.log(f"notification {method}")

    # ------------------------------------------------------------------ routing
    def _handle_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route by era: ``initialize`` -> legacy handshake; per-request ``_meta`` -> modern; else legacy session.

        * ``initialize``: :meth:`_initialize` (or -32601 if legacy support is off);
        * modern request (:func:`is_modern_request`, modern support on): :func:`check_request_meta`, then
          ``{"resultType": "complete", **result, "_meta": {META_SERVER_INFO: SERVER_INFO}}``;
        * after a legacy ``initialize``: the plain legacy result;
        * legacy-only server without a session: ``server/discover`` -> -32601, anything else -> -32600;
        * otherwise -> -32602 with a message that mentions ``_meta`` (and ``initialize`` when legacy is on).
        """
        if method == "initialize":
            if not self.legacy:
                raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: initialize (supported: {', '.join(MODERN_VERSIONS)})")
            return self._initialize(params)
        if self.modern and is_modern_request(params):
            check_request_meta(params["_meta"])
            return {"resultType": "complete", **self._dispatch(method, params, modern=True),
                    "_meta": {META_SERVER_INFO: dict(SERVER_INFO)}}  # fmt: skip
        if self.legacy and self.legacy_version is not None:
            return self._dispatch(method, params, modern=False)
        if not self.modern:
            if method == "server/discover":
                raise JsonRpcError(METHOD_NOT_FOUND, "Method not found: server/discover")
            raise JsonRpcError(INVALID_REQUEST, "Server not initialized: send initialize first")
        raise JsonRpcError(
            INVALID_PARAMS,
            f"Missing params._meta: send {META_PROTOCOL_VERSION!r} and {META_CLIENT_CAPABILITIES!r} "
            f"(protocol {MODERN_VERSIONS[0]})" + (f", or call initialize first ({LEGACY_VERSIONS[0]})" if self.legacy else ""),
        )

    def _dispatch(self, method: str, params: dict[str, Any], *, modern: bool) -> dict[str, Any]:
        """The methods themselves — the same for both eras apart from the result envelope.

        ``server/discover`` (modern only): ``supportedVersions``, ``capabilities: {"tools": {}}``,
        ``instructions``, ``ttlMs``, ``cacheScope: "public"``. ``tools/list``, ``tools/call``. Anything else:
        -32601 ``"Method not found: <method>"``.
        """
        if method == "server/discover" and modern:
            return {
                "supportedVersions": list(MODERN_VERSIONS),
                "capabilities": {"tools": {}},
                "instructions": INSTRUCTIONS,
                "ttlMs": LIST_TTL_MS,
                "cacheScope": "public",
            }
        if method == "tools/list":
            return self._list_tools(params, modern=modern)
        if method == "tools/call":
            return self._call_tool(params)
        raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {method}")

    # ------------------------------------------------------------------ tools
    def _list_tools(self, params: Mapping[str, Any], *, modern: bool) -> dict[str, Any]:
        """``tools/list``: every tool, in a stable order. We never issue cursors, so any cursor is invalid."""
        if "cursor" in params:
            if not isinstance(params["cursor"], str):
                raise JsonRpcError(INVALID_PARAMS, "cursor must be a string")
            raise JsonRpcError(INVALID_PARAMS, "Invalid cursor")
        result: dict[str, Any] = {"tools": [tool.describe() for tool in self.tools.values()]}
        if modern:  # ListToolsResult is cacheable in 2026-07-28: ttlMs and cacheScope are required
            result.update(ttlMs=LIST_TTL_MS, cacheScope="public")
        return result

    def _call_tool(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """``tools/call``. Protocol errors (malformed request, unknown tool) are JSON-RPC errors; problems
        the model can fix (invalid arguments, a value out of range) are results with ``isError: true``.

        -32602 for a non-string ``name``, non-object ``arguments`` or ``"Unknown tool: <name>"``; schema
        problems -> :func:`tool_error_result` ``("Invalid arguments: " + "; ".join(problems))``;
        :class:`ToolExecutionError` -> ``tool_error_result(str(exc))``; success -> ``content`` with the
        output as JSON text, ``structuredContent`` with the output dict, ``isError: false``.
        """
        name, arguments = params.get("name"), params.get("arguments", {})
        if not isinstance(name, str):
            raise JsonRpcError(INVALID_PARAMS, "tools/call needs a string 'name'")
        if not isinstance(arguments, dict):
            raise JsonRpcError(INVALID_PARAMS, "tools/call 'arguments' must be an object")
        tool = self.tools.get(name)
        if tool is None:
            raise JsonRpcError(INVALID_PARAMS, f"Unknown tool: {name}")
        problems = validate_against_schema(tool.input_schema, arguments)
        if problems:
            return tool_error_result("Invalid arguments: " + "; ".join(problems))
        try:
            output = dict(tool.handler(**arguments))
        except ToolExecutionError as exc:
            return tool_error_result(str(exc))
        self.log(f"called {name}")
        return {"content": [{"type": "text", "text": json.dumps(output)}], "structuredContent": output, "isError": False}

    # ------------------------------------------------------------------ legacy handshake (milestone 5)
    def _initialize(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """The 2025-11-25 ``initialize`` request: negotiate a version and open a session for this process.

        Only once (-32600 ``"initialize may only be sent once"``); needs ``protocolVersion`` (string),
        ``capabilities`` (object) and ``clientInfo`` ``{name, version}`` (else -32602). Echo the requested
        version if supported, otherwise offer ``LEGACY_VERSIONS[0]``. Result: ``protocolVersion``,
        ``capabilities: {"tools": {"listChanged": false}}``, ``serverInfo``, ``instructions``.
        """
        if self.legacy_version is not None:
            raise JsonRpcError(INVALID_REQUEST, "initialize may only be sent once")
        info = params.get("clientInfo")
        if (
            not isinstance(params.get("protocolVersion"), str)
            or not isinstance(params.get("capabilities"), dict)
            or not (isinstance(info, dict) and isinstance(info.get("name"), str) and isinstance(info.get("version"), str))
        ):
            raise JsonRpcError(INVALID_PARAMS, "initialize needs protocolVersion, capabilities and clientInfo {name, version}")
        requested = params["protocolVersion"]
        self.legacy_version = requested if requested in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
        return {
            "protocolVersion": self.legacy_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": dict(SERVER_INFO),
            "instructions": INSTRUCTIONS,
        }


def tool_error_result(message: str) -> dict[str, Any]:
    """A tool execution error: a normal result the model can read and act on."""
    return {"content": [{"type": "text", "text": message}], "isError": True}


# ==================================================================================================
# Milestone 4: the stdio transport
# ==================================================================================================


def serve(stdin: BinaryIO, stdout: BinaryIO, server: McpServer) -> None:
    """Read newline-delimited JSON-RPC from ``stdin`` and write responses to ``stdout`` until EOF.

    Bytes, not text: this avoids Windows newline translation, and UTF-8 is decoded explicitly.
    Over-long lines are rejected (a cheap guard against memory exhaustion). ``stdout`` carries only
    protocol messages — logging goes elsewhere (stderr).

    Per line: read at most ``MAX_LINE_BYTES + 1`` bytes; a longer line is skipped to its end and answered
    with -32600 ``"Invalid Request: message too large"``; undecodable bytes give a parse error; blank
    lines are ignored; strip whitespace (including ``\\r``) before :meth:`McpServer.handle_line`. Write each
    reply as UTF-8 plus ``b"\\n"`` and flush.
    """
    while True:
        raw = stdin.readline(MAX_LINE_BYTES + 1)
        if not raw:
            return
        if len(raw) > MAX_LINE_BYTES and not raw.endswith(b"\n"):
            while (rest := stdin.readline(MAX_LINE_BYTES)) and not rest.endswith(b"\n"):
                pass
            reply: str | None = encode_message(error_response(None, INVALID_REQUEST, "Invalid Request: message too large"))
        else:
            try:
                text = raw.decode("utf-8").strip()
            except UnicodeDecodeError:
                text = "\x00"  # not JSON: produces a parse error
            reply = server.handle_line(text) if text else None
        if reply is not None:
            stdout.write(reply.encode("utf-8") + b"\n")
            stdout.flush()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the server on stdio. ``--legacy-only`` disables the modern (2026-07-28) path for testing clients."""
    args = list(sys.argv[1:] if argv is None else argv)

    def log(message: str) -> None:
        print(f"[groundwork-tools] {message}", file=sys.stderr, flush=True)

    server = McpServer(modern="--legacy-only" not in args, log=log)
    eras = [f"modern {', '.join(MODERN_VERSIONS)}"] if server.modern else []
    log(f"ready ({'; '.join([*eras, f'legacy {LEGACY_VERSIONS[0]}'])})")
    serve(sys.stdin.buffer, sys.stdout.buffer, server)
    log("stdin closed; exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
