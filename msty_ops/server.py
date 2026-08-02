"""Four-tool diagnostic Msty operations MCP server."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from . import __version__
from .manifests import (
    build_model_manifest,
    capability_manifest,
    compatibility_manifest,
    status_manifest,
)

DIAGNOSTIC_TOOLS = (
    "get_msty_status",
    "get_capability_manifest",
    "get_model_manifest",
    "run_compatibility_check",
)

mcp = FastMCP("msty-ops")
# MCP is pinned exactly because FastMCP does not expose a public server-version setter.
mcp._mcp_server.version = __version__


def _render(value: dict) -> str:
    return json.dumps(value, indent=2, default=str)


@mcp.tool()
def get_msty_status() -> str:
    """Report installation, local-service, and readiness state without reading Msty data."""
    return _render(status_manifest())


@mcp.tool()
def get_capability_manifest() -> str:
    """Report the exact four-tool diagnostic surface and its trust boundaries."""
    return _render(capability_manifest(DIAGNOSTIC_TOOLS, "diagnostic"))


@mcp.tool()
def get_model_manifest() -> str:
    """List facts advertised by fixed, loopback-only Msty model services."""
    return _render(build_model_manifest())


@mcp.tool()
def run_compatibility_check() -> str:
    """Validate the installed Studio version and local model endpoint schemas."""
    return _render(compatibility_manifest())


def main() -> None:
    """Run the diagnostic server over process-scoped stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
