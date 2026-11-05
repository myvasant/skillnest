"""OPTIONAL tests with the official MCP Python SDK — skipped unless ``mcp`` is installed.

1. The SDK version of the server (``optional/mcp_sdk_server.py``) exposes the same tools.
2. Interoperability: the SDK's own client talks to YOUR hand-written server over stdio — the strongest
   evidence that your server follows the specification. With ``--legacy-only`` the SDK client falls
   back to the 2025-11-25 ``initialize`` handshake, exercising the dual-era path.

Version-dependent: written for mcp 2.x (checked with 2.3.0), whose client is ``mcp.Client``.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

mcp = pytest.importorskip("mcp")
anyio = pytest.importorskip("anyio")

OPTIONAL_FILE = Path(__file__).resolve().parent.parent / "optional" / "mcp_sdk_server.py"
SPEC = importlib.util.find_spec("mcp_stdio_server")
assert SPEC is not None and SPEC.origin is not None
HAND_WRITTEN_SERVER = SPEC.origin


@pytest.fixture(scope="module")
def sdk_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mcp_sdk_server", OPTIONAL_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plain_functions(sdk_module: ModuleType) -> None:
    assert sdk_module.temperature(100, "celsius", "fahrenheit") == {"value": 212.0, "unit": "fahrenheit"}
    assert sdk_module.stats("a b\nc") == {"characters": 5, "words": 3, "lines": 2}
    with pytest.raises(ValueError):
        sdk_module.temperature(-500, "celsius", "kelvin")


def test_sdk_server_lists_the_same_tools(sdk_module: ModuleType) -> None:
    server = sdk_module.build_server()
    tools = anyio.run(server.list_tools)
    assert sorted(tool.name for tool in tools) == ["convert_temperature", "word_stats"]
    tool = next(tool for tool in tools if tool.name == "convert_temperature")
    schema = getattr(tool, "input_schema", None) or tool.inputSchema  # snake_case in mcp 2.x, camelCase in 1.x
    assert schema["required"] == ["value", "from_unit", "to_unit"]


@pytest.mark.skipif(not hasattr(mcp, "Client"), reason="needs the mcp 2.x Client class")
@pytest.mark.parametrize(
    ("args", "expected_version"),
    [
        ([HAND_WRITTEN_SERVER], "2026-07-28"),
        ([HAND_WRITTEN_SERVER, "--legacy-only"], "2025-11-25"),
        ([str(OPTIONAL_FILE)], "2026-07-28"),
    ],
    ids=["your-server-modern", "your-server-legacy-only", "sdk-server"],
)
def test_official_client_over_stdio(args: list[str], expected_version: str) -> None:
    async def scenario() -> tuple[str, list[str], object, object]:
        params = mcp.StdioServerParameters(command=sys.executable, args=args)
        async with mcp.Client(params) as client:
            listed = await client.list_tools()
            good = await client.call_tool("word_stats", {"text": "a b"})
            bad = await client.call_tool("convert_temperature", {"value": -500, "from_unit": "celsius", "to_unit": "kelvin"})
            return client.protocol_version, [tool.name for tool in listed.tools], good, bad

    version, names, good, bad = anyio.run(scenario)
    assert version == expected_version
    assert names == ["convert_temperature", "word_stats"]
    assert good.structured_content == {"characters": 3, "words": 2, "lines": 1} and not good.is_error
    assert bad.is_error and "absolute zero" in bad.content[0].text
