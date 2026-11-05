"""OPTIONAL: the same two tools served with the official MCP Python SDK.

VERSION-DEPENDENT. Written for the ``mcp`` package 2.x (checked with mcp 2.3.0, October 2026), where
the high-level server class is ``MCPServer`` — it was called ``FastMCP`` in mcp 1.x, and the import
below falls back to that name. The SDK takes care of everything you wrote by hand in
``mcp_stdio_server.py``: framing, JSON-RPC envelopes and error codes, protocol-version handling for
both eras, ``tools/list`` schemas generated from type hints, and argument validation.

Run it over stdio (from the kit folder)::

    python -m pip install -r optional/requirements.txt
    python optional/mcp_sdk_server.py

Compare what you had to write with what the SDK generates: ``python -m pytest tests/test_mcp_sdk_optional.py``.
"""

from typing import Any, Literal, TypedDict

try:  # mcp >= 2.0
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x: the same classes under their old names
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]
from mcp.types import ToolAnnotations

Unit = Literal["celsius", "fahrenheit", "kelvin"]
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


class Temperature(TypedDict):
    """Structured output of convert_temperature (the SDK turns this into an outputSchema)."""

    value: float
    unit: str


class WordStats(TypedDict):
    """Structured output of word_stats."""

    characters: int
    words: int
    lines: int


def temperature(value: float, from_unit: Unit, to_unit: Unit) -> Temperature:
    """Plain function: convert via kelvin, refusing temperatures below absolute zero."""
    to_kelvin = {"celsius": value + 273.15, "fahrenheit": (value - 32) * 5 / 9 + 273.15, "kelvin": float(value)}
    kelvin = to_kelvin[from_unit]
    if kelvin < 0:
        raise ValueError(f"{value} {from_unit} is below absolute zero")
    result = {"celsius": kelvin - 273.15, "fahrenheit": (kelvin - 273.15) * 9 / 5 + 32, "kelvin": kelvin}[to_unit]
    return {"value": round(result, 2), "unit": to_unit}


def stats(text: str) -> WordStats:
    """Plain function: count characters, words and lines."""
    return {"characters": len(text), "words": len(text.split()), "lines": len(text.splitlines())}


def build_server() -> Any:
    """Create the SDK server and register both tools with decorators."""
    server = MCPServer("groundwork-tools-sdk", instructions="Two read-only utilities.")

    @server.tool(
        name="convert_temperature",
        title="Temperature converter",
        description="Convert a temperature between celsius, fahrenheit and kelvin.",
        annotations=READ_ONLY,
    )
    def convert_temperature(value: float, from_unit: Unit, to_unit: Unit) -> Temperature:
        # The SDK hides the text of unexpected exceptions from the client (like your -32603 handling)
        # and passes ToolError messages through as isError results (like your ToolExecutionError).
        try:
            return temperature(value, from_unit, to_unit)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(
        name="word_stats",
        title="Word statistics",
        description="Count the characters, words and lines in a text.",
        annotations=READ_ONLY,
    )
    def word_stats(text: str) -> WordStats:
        return stats(text)

    return server


if __name__ == "__main__":
    build_server().run(transport="stdio")
