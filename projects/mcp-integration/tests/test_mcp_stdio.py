"""Behaviour tests for the hand-written MCP server and client, one class per milestone.

Run everything with ``python -m pytest`` or one milestone with ``-k Milestone3``. Milestones 1-3 call
the server in-process; milestones 4-5 also start it as a real subprocess with ``sys.executable`` and
talk to it over stdio, exactly like an MCP host would. No network is used.
"""

import importlib.util
import io
import json
from pathlib import Path

import pytest
from mcp_stdio_client import McpError, McpStdioClient
from mcp_stdio_server import (
    INSTRUCTIONS,
    MAX_LINE_BYTES,
    McpServer,
    ToolDefinition,
    check_request_meta,
    encode_message,
    error_response,
    result_response,
    serve,
    validate_against_schema,
)

SPEC = importlib.util.find_spec("mcp_stdio_server")
assert SPEC is not None and SPEC.origin is not None
SERVER_PATH = Path(SPEC.origin)
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}
SERVER_META = {"io.modelcontextprotocol/serverInfo": {"name": "groundwork-tools", "version": "1.0.0"}}


def request(method: str, params: dict | None = None, *, request_id: int | str = 1, meta: bool = True) -> dict:
    """A JSON-RPC request; by default with the 2026-07-28 per-request _meta."""
    body = dict(params or {})
    if meta:
        body["_meta"] = dict(META)
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": body}


def call(server: McpServer, name: str, arguments: object, **kwargs) -> dict:
    """tools/call through handle_message; returns the whole response."""
    return server.handle_message(request("tools/call", {"name": name, "arguments": arguments}, **kwargs))


def error_of(response: dict) -> tuple[int, str]:
    assert "error" in response, f"expected an error response, got {response}"
    return response["error"]["code"], response["error"]["message"]


@pytest.fixture
def server() -> McpServer:
    return McpServer()


@pytest.fixture
def client():
    with McpStdioClient(SERVER_PATH) as running:
        yield running


class TestMilestone1JsonRpc:
    """Milestone 1: the JSON-RPC 2.0 envelope — requests, notifications and error codes."""

    def test_response_builders(self) -> None:
        assert result_response(7, {"a": 1}) == {"jsonrpc": "2.0", "id": 7, "result": {"a": 1}}
        assert error_response(None, -32700, "Parse error") == {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error"},
        }
        assert error_response("x", -32022, "Unsupported", {"supported": []})["error"]["data"] == {"supported": []}

    def test_encoded_messages_are_single_lines(self) -> None:
        line = encode_message({"text": "line one\nline two", "emoji": "café"})
        assert "\n" not in line and json.loads(line) == {"text": "line one\nline two", "emoji": "café"}

    def test_parse_error(self, server: McpServer) -> None:
        response = json.loads(server.handle_line('{"jsonrpc": "2.0", "id": 1, "method": '))
        assert response["id"] is None and response["error"]["code"] == -32700

    @pytest.mark.parametrize(
        ("message", "expected_id"),
        [
            ([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}], None),
            ("tools/list", None),
            (42, None),
            ({"jsonrpc": "1.0", "id": 3, "method": "tools/list"}, 3),
            ({"id": 3, "method": "tools/list"}, 3),
            ({"jsonrpc": "2.0", "id": 4}, 4),
            ({"jsonrpc": "2.0", "id": "abc", "method": 5}, "abc"),
            ({"jsonrpc": "2.0", "id": None, "method": "tools/list"}, None),
            ({"jsonrpc": "2.0", "id": True, "method": "tools/list"}, None),
            ({"jsonrpc": "2.0", "id": 1.5, "method": "tools/list"}, None),
            ({"jsonrpc": "2.0"}, None),
        ],
    )
    def test_invalid_requests(self, server: McpServer, message: object, expected_id: object) -> None:
        response = server.handle_message(message)
        assert response["jsonrpc"] == "2.0" and response["id"] == expected_id
        assert response["error"]["code"] == -32600

    def test_notifications_get_no_response(self, server: McpServer) -> None:
        assert server.handle_message({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}}) is None
        assert server.handle_line('{"jsonrpc": "2.0", "method": "anything/at-all"}') is None

    def test_params_must_be_an_object(self, server: McpServer) -> None:
        response = server.handle_message({"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": [1, 2]})
        assert response["id"] == 9 and response["error"]["code"] == -32602

    def test_handle_line_returns_one_json_line(self, server: McpServer) -> None:
        line = server.handle_line(json.dumps(request("server/discover", request_id="d-1")))
        assert "\n" not in line and json.loads(line)["id"] == "d-1"


class TestMilestone2StatelessProtocol:
    """Milestone 2: per-request _meta (revision 2026-07-28), server/discover and version errors."""

    def test_discover(self, server: McpServer) -> None:
        response = server.handle_message(request("server/discover", request_id="discover-1"))
        assert response == {
            "jsonrpc": "2.0",
            "id": "discover-1",
            "result": {
                "resultType": "complete",
                "supportedVersions": ["2026-07-28"],
                "capabilities": {"tools": {}},
                "instructions": INSTRUCTIONS,
                "ttlMs": 300000,
                "cacheScope": "public",
                "_meta": SERVER_META,
            },
        }

    def test_check_request_meta(self) -> None:
        assert check_request_meta(dict(META)) == "2026-07-28"
        info = {**META, "io.modelcontextprotocol/clientInfo": {"name": "x", "version": "1"}}
        assert check_request_meta(info) == "2026-07-28"

    @pytest.mark.parametrize(
        ("meta", "fragment"),
        [
            (None, "_meta"),
            ("not an object", "_meta"),
            ({"io.modelcontextprotocol/clientCapabilities": {}}, "protocolVersion"),
            ({"io.modelcontextprotocol/protocolVersion": "2026-07-28"}, "clientCapabilities"),
            ({**META, "io.modelcontextprotocol/clientCapabilities": []}, "clientCapabilities"),
            ({**META, "io.modelcontextprotocol/clientInfo": {"name": "x"}}, "clientInfo"),
            ({**META, "io.modelcontextprotocol/protocolVersion": 2026}, "protocolVersion"),
        ],
    )
    def test_malformed_meta_is_invalid_params(self, server: McpServer, meta: object, fragment: str) -> None:
        params = {} if meta is None else {"_meta": meta}
        code, message = error_of(server.handle_message(request("tools/list", params, meta=False)))
        assert code == -32602 and fragment in message

    def test_unsupported_version(self, server: McpServer) -> None:
        meta = {**META, "io.modelcontextprotocol/protocolVersion": "1900-01-01"}
        response = server.handle_message(request("tools/list", {"_meta": meta}, meta=False))
        assert response["error"] == {
            "code": -32022,
            "message": "Unsupported protocol version",
            "data": {"supported": ["2026-07-28"], "requested": "1900-01-01"},
        }

    def test_unknown_method(self, server: McpServer) -> None:
        assert error_of(server.handle_message(request("resources/list"))) == (-32601, "Method not found: resources/list")

    def test_every_request_stands_alone(self) -> None:
        first, second = McpServer(), McpServer()
        assert "tools" in first.handle_message(request("tools/list"))["result"], "no discover or handshake needed"
        assert second.handle_message(request("tools/call", {"name": "word_stats", "arguments": {"text": "a b"}}))[
            "result"
        ]["structuredContent"] == {"characters": 3, "words": 2, "lines": 1}


class TestMilestone3Tools:
    """Milestone 3: tools/list and tools/call, input validation, and the two kinds of errors."""

    def test_list_tools(self, server: McpServer) -> None:
        result = server.handle_message(request("tools/list"))["result"]
        assert (result["resultType"], result["ttlMs"], result["cacheScope"], result["_meta"]) == (
            "complete", 300000, "public", SERVER_META,
        )  # fmt: skip
        tools = {tool["name"]: tool for tool in result["tools"]}
        assert list(tools) == ["convert_temperature", "word_stats"]
        for tool in tools.values():
            assert set(tool) == {"name", "title", "description", "inputSchema", "outputSchema", "annotations"}
            assert tool["inputSchema"]["type"] == "object" and tool["inputSchema"]["additionalProperties"] is False
            assert tool["annotations"] == {"readOnlyHint": True, "openWorldHint": False}
        assert tools["convert_temperature"]["inputSchema"]["required"] == ["value", "from_unit", "to_unit"]

    def test_cursors_are_rejected(self, server: McpServer) -> None:
        assert error_of(server.handle_message(request("tools/list", {"cursor": "page-2"}))) == (-32602, "Invalid cursor")
        assert error_of(server.handle_message(request("tools/list", {"cursor": 2})))[0] == -32602

    @pytest.mark.parametrize(
        ("arguments", "expected"),
        [
            ({"value": 100, "from_unit": "celsius", "to_unit": "fahrenheit"}, {"value": 212.0, "unit": "fahrenheit"}),
            ({"value": 32, "from_unit": "fahrenheit", "to_unit": "celsius"}, {"value": 0.0, "unit": "celsius"}),
            ({"value": 0, "from_unit": "kelvin", "to_unit": "celsius"}, {"value": -273.15, "unit": "celsius"}),
            ({"value": 21.5, "from_unit": "celsius", "to_unit": "kelvin"}, {"value": 294.65, "unit": "kelvin"}),
        ],
    )
    def test_convert_temperature(self, server: McpServer, arguments: dict, expected: dict) -> None:
        result = call(server, "convert_temperature", arguments)["result"]
        assert result["resultType"] == "complete" and result["isError"] is False
        assert result["structuredContent"] == expected
        assert result["content"][0]["type"] == "text" and json.loads(result["content"][0]["text"]) == expected

    def test_word_stats(self, server: McpServer) -> None:
        result = call(server, "word_stats", {"text": "Hello world\nbye"})["result"]
        assert result["structuredContent"] == {"characters": 15, "words": 3, "lines": 2}
        assert call(server, "word_stats", {"text": ""})["result"]["structuredContent"] == {
            "characters": 0, "words": 0, "lines": 0,
        }  # fmt: skip

    @pytest.mark.parametrize(
        ("name", "arguments", "fragment"),
        [
            ("convert_temperature", {"value": 1, "from_unit": "celsius"}, "missing required property 'to_unit'"),
            ("convert_temperature", {"value": "hot", "from_unit": "celsius", "to_unit": "kelvin"}, "expected number, got string"),
            ("convert_temperature", {"value": True, "from_unit": "celsius", "to_unit": "kelvin"}, "expected number, got boolean"),
            ("convert_temperature", {"value": 1, "from_unit": "rankine", "to_unit": "kelvin"}, "must be one of"),
            ("convert_temperature", {"value": 1, "from_unit": "celsius", "to_unit": "kelvin", "x": 1}, "unexpected property 'x'"),
            ("convert_temperature", {"value": -500, "from_unit": "celsius", "to_unit": "kelvin"}, "below absolute zero"),
            ("word_stats", {"text": "x" * 10_001}, "longer than 10000 characters"),
            ("word_stats", {}, "missing required property 'text'"),
        ],
    )  # fmt: skip
    def test_tool_errors_are_results_the_model_can_read(
        self, server: McpServer, name: str, arguments: dict, fragment: str
    ) -> None:
        result = call(server, name, arguments)["result"]
        assert result["isError"] is True and result["resultType"] == "complete"
        assert fragment in result["content"][0]["text"] and "structuredContent" not in result

    def test_protocol_errors(self, server: McpServer) -> None:
        assert error_of(call(server, "launch_rockets", {})) == (-32602, "Unknown tool: launch_rockets")
        assert error_of(server.handle_message(request("tools/call", {"arguments": {}})))[0] == -32602
        assert error_of(call(server, "word_stats", ["not", "an", "object"]))[0] == -32602

    def test_bugs_become_internal_errors_without_details(self) -> None:
        def broken(text: str) -> dict:
            raise RuntimeError("secret database password in this message")

        logs: list[str] = []
        tool = ToolDefinition("broken", "Broken", "Always fails.", {"type": "object"}, {"type": "object"}, broken)
        response = call(McpServer([tool], log=logs.append), "broken", {"text": "x"})
        assert error_of(response) == (-32603, "Internal error")
        assert "secret" not in json.dumps(response) and any("secret" in line for line in logs)

    def test_schema_validator(self) -> None:
        schema = {"type": "object", "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 3}}, "required": ["n"]}
        assert validate_against_schema(schema, {"n": 2}) == []
        assert validate_against_schema(schema, {"n": 0}) == ["arguments.n: less than 1"]
        assert validate_against_schema(schema, {"n": 4}) == ["arguments.n: greater than 3"]
        assert validate_against_schema(schema, {"n": 2.5}) == ["arguments.n: expected integer, got number"]
        assert validate_against_schema(schema, []) == ["arguments: expected object, got array"]
        assert validate_against_schema(schema, {}) == ["arguments: missing required property 'n'"]
        assert validate_against_schema({"type": "object"}, {"anything": None}) == []


class TestMilestone4StdioTransport:
    """Milestone 4: newline-delimited JSON-RPC over stdio, in-process and as a real subprocess."""

    def run_serve(self, data: bytes) -> list[dict]:
        stdout = io.BytesIO()
        serve(io.BytesIO(data), stdout, McpServer())
        raw = stdout.getvalue()
        assert raw == b"" or raw.endswith(b"\n")
        return [json.loads(line) for line in raw.splitlines()]

    def test_serve_answers_requests_only(self) -> None:
        lines = [
            json.dumps(request("server/discover", request_id=1)),
            "",
            json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled"}),
            "this is not json",
            json.dumps(request("tools/call", {"name": "word_stats", "arguments": {"text": "héllo wörld"}}, request_id=2)),
        ]
        responses = self.run_serve(("\r\n".join(lines) + "\n").encode("utf-8"))
        assert [r["id"] for r in responses] == [1, None, 2]
        assert responses[1]["error"]["code"] == -32700
        assert responses[2]["result"]["structuredContent"] == {"characters": 11, "words": 2, "lines": 1}

    def test_serve_rejects_bad_bytes_and_huge_lines(self) -> None:
        huge = b'{"padding": "' + b"x" * (MAX_LINE_BYTES + 10) + b'"}\n'
        follow_up = json.dumps(request("tools/list", request_id=5)).encode() + b"\n"
        responses = self.run_serve(b"\xff\xfe not utf-8\n" + huge + follow_up)
        assert [r.get("error", {}).get("code") for r in responses] == [-32700, -32600, None]
        assert responses[1]["error"]["message"] == "Invalid Request: message too large" and responses[2]["id"] == 5

    def test_end_to_end_over_stdio(self, client: McpStdioClient) -> None:
        info = client.discover()
        assert info["supportedVersions"] == ["2026-07-28"] and info["_meta"] == SERVER_META
        assert [tool["name"] for tool in client.list_tools()] == ["convert_temperature", "word_stats"]
        result = client.call_tool("convert_temperature", {"value": 100, "from_unit": "celsius", "to_unit": "kelvin"})
        assert result["structuredContent"] == {"value": 373.15, "unit": "kelvin"} and result["isError"] is False
        assert client.call_tool("word_stats", {"text": 5})["isError"] is True

    def test_errors_and_raw_lines_over_stdio(self, client: McpStdioClient) -> None:
        with pytest.raises(McpError) as caught:
            client.call_tool("nope", {})
        assert caught.value.code == -32602 and caught.value.message == "Unknown tool: nope"
        client.send_raw_line("{oops")
        assert client.receive()["error"]["code"] == -32700
        client.notify("notifications/cancelled", {"requestId": 99})
        client.send(request("tools/list", request_id="after-notification"))
        assert client.receive()["id"] == "after-notification", "the notification produced no response"

    def test_clean_shutdown(self) -> None:
        running = McpStdioClient(SERVER_PATH)
        running.discover()
        assert running.close() == 0
        assert any("ready" in line for line in running.stderr_lines), "logs go to stderr, not stdout"


class TestMilestone5LegacyDualEra:
    """Milestone 5 (dual-era extra): the 2025-11-25 initialize handshake and the client's era probe."""

    INIT = {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "old-host", "version": "0.9"}}

    def test_initialize_handshake(self, server: McpServer) -> None:
        response = server.handle_message(request("initialize", self.INIT, meta=False))
        assert response["result"] == {
            "protocolVersion": "2025-11-25",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "groundwork-tools", "version": "1.0.0"},
            "instructions": INSTRUCTIONS,
        }
        assert server.legacy_version == "2025-11-25" and server.legacy_initialized is False
        assert server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
        assert server.legacy_initialized is True

    def test_legacy_results_have_legacy_shapes(self, server: McpServer) -> None:
        server.handle_message(request("initialize", self.INIT, meta=False))
        listed = server.handle_message(request("tools/list", request_id=2, meta=False))["result"]
        assert set(listed) == {"tools"} and len(listed["tools"]) == 2
        called = call(server, "word_stats", {"text": "a b c"}, meta=False)["result"]
        assert set(called) == {"content", "structuredContent", "isError"}
        assert "resultType" in server.handle_message(request("tools/list", request_id=3))["result"], (
            "a request with modern _meta is still served statelessly (dual-era)"
        )

    def test_version_negotiation_and_errors(self) -> None:
        old = McpServer()
        answer = old.handle_message(request("initialize", {**self.INIT, "protocolVersion": "2024-11-05"}, meta=False))
        assert answer["result"]["protocolVersion"] == "2025-11-25", "the server offers the version it supports"
        assert error_of(old.handle_message(request("initialize", self.INIT, meta=False)))[0] == -32600
        assert error_of(McpServer().handle_message(request("initialize", {"protocolVersion": "2025-11-25"}, meta=False)))[0] == -32602
        code, message = error_of(McpServer().handle_message(request("tools/list", meta=False)))
        assert code == -32602 and "initialize" in message

    def test_legacy_only_server(self) -> None:
        legacy = McpServer(modern=False)
        assert error_of(legacy.handle_message(request("server/discover")))[0] == -32601
        assert error_of(legacy.handle_message(request("tools/list")))[0] == -32600
        assert error_of(McpServer(legacy=False).handle_message(request("initialize", self.INIT, meta=False)))[0] == -32601

    def test_client_handshake_over_stdio(self, client: McpStdioClient) -> None:
        result = client.initialize_legacy()
        assert result["protocolVersion"] == "2025-11-25" and client.mode == "legacy"
        assert [tool["name"] for tool in client.list_tools()] == ["convert_temperature", "word_stats"]

    def test_client_probe_picks_the_right_era(self) -> None:
        with McpStdioClient(SERVER_PATH) as modern:
            assert modern.connect() == "modern" and modern.mode == "modern"
        with McpStdioClient(SERVER_PATH, args=["--legacy-only"]) as legacy:
            assert legacy.connect() == "legacy" and legacy.mode == "legacy"
            assert legacy.call_tool("word_stats", {"text": "one two"})["structuredContent"]["words"] == 2
