"""Five-tool Msty operations server with explicit local inference."""

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
from .runtime import local_generate_request

LOCAL_INFERENCE_TOOLS = (
    "get_msty_status",
    "get_capability_manifest",
    "get_model_manifest",
    "run_compatibility_check",
    "local_generate",
)

mcp = FastMCP("msty-local-inference")
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
    """Report the exact five-tool local-inference surface and its trust boundaries."""
    return _render(capability_manifest(LOCAL_INFERENCE_TOOLS, "local-inference"))


@mcp.tool()
def get_model_manifest() -> str:
    """List facts advertised by fixed, loopback-only Msty model services."""
    return _render(build_model_manifest())


@mcp.tool()
def run_compatibility_check() -> str:
    """Validate the installed Studio version and local model endpoint schemas."""
    return _render(compatibility_manifest())


@mcp.tool()
def local_generate(
    model: str,
    message: str,
    service: str | None = None,
    system_prompt: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1_024,
) -> str:
    """Generate with one explicit Msty local model; never simulate or fall back to cloud."""
    return _render(
        local_generate_request(
            model=model,
            message=message,
            service=service,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    )


def main() -> None:
    """Run the explicit local-inference server over process-scoped stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
