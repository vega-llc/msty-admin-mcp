#!/usr/bin/env python3
"""Verify an installed Msty Local Ops MCP over stdio."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

DIAGNOSTIC_TOOLS = {
    "get_msty_status",
    "get_capability_manifest",
    "get_model_manifest",
    "run_compatibility_check",
}
LOCAL_TOOLS = DIAGNOSTIC_TOOLS | {"local_generate"}


async def inspect(mode: str) -> dict:
    module = "msty_ops.server" if mode == "diagnostic" else "msty_ops.local_server"
    expected_name = "msty-ops" if mode == "diagnostic" else "msty-local-inference"
    expected_tools = DIAGNOSTIC_TOOLS if mode == "diagnostic" else LOCAL_TOOLS
    parameters = StdioServerParameters(command=sys.executable, args=["-m", module])

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            listed = await session.list_tools()
            models_result = await session.call_tool("get_model_manifest", {})
            capability_result = await session.call_tool("get_capability_manifest", {})

    if not models_result.content or not isinstance(models_result.content[0], TextContent):
        raise RuntimeError("model manifest did not return text")
    if not capability_result.content or not isinstance(capability_result.content[0], TextContent):
        raise RuntimeError("capability manifest did not return text")
    models = json.loads(models_result.content[0].text)
    capabilities = json.loads(capability_result.content[0].text)
    tools = {tool.name for tool in listed.tools}
    return {
        "ok": (
            initialized.serverInfo.name == expected_name
            and initialized.serverInfo.version == "1.2.0"
            and tools == expected_tools
            and set(capabilities.get("tools", [])) == expected_tools
            and capabilities.get("tool_count") == len(expected_tools)
            and capabilities.get("resources") == []
            and capabilities.get("prompts") == []
        ),
        "mode": mode,
        "server": initialized.serverInfo.name,
        "version": initialized.serverInfo.version,
        "tools": sorted(tools),
        "model_count": models.get("state_summary", {}).get("advertised_records", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("diagnostic", "local"), default="diagnostic")
    parser.add_argument("--allow-no-models", action="store_true")
    args = parser.parse_args()

    try:
        result = asyncio.run(inspect(args.mode))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    if not result["ok"]:
        return 1
    if result["model_count"] == 0 and not args.allow_no_models:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
