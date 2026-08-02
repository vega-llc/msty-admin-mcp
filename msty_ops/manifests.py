"""Truthful status and compatibility manifests for the modern adapter."""

from __future__ import annotations

import platform
import plistlib
from pathlib import Path
from typing import Any, Iterable

import psutil

from . import __version__
from .runtime import SERVICE_PORTS, build_model_manifest, probe_services, utc_now

APP_PATHS = (Path("/Applications/MstyStudio.app"), Path("/Applications/Msty Studio.app"))
TESTED_STUDIO_VERSIONS = frozenset({"2.9.6"})


def _app_info() -> dict[str, Any]:
    app_path = next((candidate for candidate in APP_PATHS if candidate.exists()), None)
    version = None
    bundle_id = None
    if app_path:
        plist_path = app_path / "Contents/Info.plist"
        try:
            with plist_path.open("rb") as stream:
                info = plistlib.load(stream)
            version = info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")
            bundle_id = info.get("CFBundleIdentifier")
        except (OSError, plistlib.InvalidFileException, AttributeError):
            pass
    return {
        "installed": app_path is not None,
        "path": str(app_path) if app_path else None,
        "version": version,
        "bundle_id": bundle_id,
        "version_support": ("tested" if version in TESTED_STUDIO_VERSIONS else "not_tested"),
    }


def _process_info() -> dict[str, Any]:
    inspected = 0
    denied = 0
    vanished = 0
    try:
        for process in psutil.process_iter(["name", "pid"]):
            try:
                inspected += 1
                name = str(process.info.get("name") or "")
            except (psutil.AccessDenied, PermissionError):
                denied += 1
                continue
            except psutil.NoSuchProcess:
                vanished += 1
                continue

            if "msty" not in name.casefold():
                continue

            try:
                executable = process.exe()
            except (psutil.AccessDenied, PermissionError):
                return {
                    "state": "running_unverified",
                    "running": True,
                    "pid": process.info.get("pid"),
                    "executable": None,
                    "inspection_complete": False,
                    "error": "Msty executable inspection was denied",
                }
            except psutil.NoSuchProcess:
                return {
                    "state": "unknown",
                    "running": None,
                    "inspection_complete": False,
                    "error": "Msty process exited during inspection",
                }
            return {
                "state": "running",
                "running": True,
                "pid": process.info.get("pid"),
                "executable": executable,
                "inspection_complete": True,
            }
    except (psutil.Error, OSError, PermissionError) as exc:
        return {
            "state": "unknown",
            "running": None,
            "inspection_complete": False,
            "error": str(exc),
        }
    if denied:
        return {
            "state": "unknown",
            "running": None,
            "inspection_complete": False,
            "error": "One or more process names could not be inspected",
            "inspected_processes": inspected,
            "access_denied_processes": denied,
        }
    return {
        "state": "not_detected",
        "running": False,
        "inspection_complete": True,
        "access_denied_processes": denied,
        "vanished_processes": vanished,
    }


def status_manifest() -> dict[str, Any]:
    app = _app_info()
    process = _process_info()
    services = probe_services()
    usable_services = [
        name
        for name, result in services.items()
        if result["reachable"]
        and result["schema_valid"]
        and (result["advertised_model_count"] or 0) > 0
    ]
    local_ready = bool(app["installed"] and usable_services)
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "adapter": {"name": "msty-ops", "version": __version__},
        "studio": app,
        "process": process,
        "local_services": services,
        "readiness": {
            "local": {
                "status": "ready" if local_ready else "not_ready",
                "usable_services": usable_services,
            },
            "cloud": {
                "status": "not_assessed",
                "note": (
                    "This adapter never reads hosted-provider credentials or external router "
                    "policy state."
                ),
            },
            "restricted_local": {
                "status": "not_attested",
                "blocking_checks": [
                    "process-level outbound deny has not been proven",
                    "DNS and HTTPS canary capture has not been proven",
                    "telemetry and temporary-cache controls have not been proven",
                    "an MCP client can observe every tool argument and result",
                ],
            },
        },
    }


def capability_manifest(tool_names: Iterable[str], process_kind: str) -> dict[str, Any]:
    exposed_tools = sorted(set(tool_names))
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "adapter": {"name": "msty-ops", "version": __version__},
        "process_kind": process_kind,
        "tool_count": len(exposed_tools),
        "tools": exposed_tools,
        "resources": [],
        "prompts": [],
        "transport": "stdio",
        "construction": "direct_allowlist",
        "network_policy": {
            "destinations": [
                {"host": "127.0.0.1", "port": port, "service": service}
                for service, port in SERVICE_PORTS.items()
            ],
            "proxies": False,
            "redirects": False,
            "cloud_fallback": False,
        },
        "privacy_boundary": {
            "local_service_only": True,
            "caller_observes_arguments_and_results": True,
            "approved_for_sensitive_data": False,
        },
    }


def compatibility_manifest() -> dict[str, Any]:
    app = _app_info()
    services = probe_services()
    compatible_services = [
        name for name, result in services.items() if result["reachable"] and result["schema_valid"]
    ]
    if not app["installed"]:
        overall = "fail"
    elif not compatible_services:
        overall = "not_ready"
    elif app["version_support"] == "tested":
        overall = "pass"
    else:
        overall = "pass_unverified_version"
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "overall_status": overall,
        "studio": app,
        "tested_matrix": {
            "studio_versions": sorted(TESTED_STUDIO_VERSIONS),
            "mcp_sdk": "mcp==1.29.0",
            "python": ["3.10", "3.11", "3.12"],
            "platform": "macOS Apple Silicon",
        },
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "local_service_contract": {
            "required_capability": "at least one valid /v1/models endpoint",
            "compatible_services": compatible_services,
            "services": services,
        },
        "not_checked": [
            "external gateway or router policy configuration",
            "provider credentials",
            "Msty database schema",
            "restricted-local egress attestation",
        ],
    }


__all__ = [
    "status_manifest",
    "capability_manifest",
    "compatibility_manifest",
    "build_model_manifest",
]
