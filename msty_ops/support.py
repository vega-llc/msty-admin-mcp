"""Create a deliberately privacy-redacted Msty Local Ops support bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import __version__
from .doctor import _private_json_write, assess
from .manifests import compatibility_manifest, status_manifest
from .runtime import SERVICE_PORTS, utc_now


def build_support_bundle(
    status: dict[str, Any] | None = None,
    compatibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = status if status is not None else status_manifest()
    compatibility = compatibility if compatibility is not None else compatibility_manifest()
    doctor = assess(status, compatibility, baseline_path=None)
    studio = status.get("studio") or {}
    process = status.get("process") or {}
    services = status.get("local_services") or {}
    safe_services = {}
    for name in sorted(SERVICE_PORTS):
        candidate = services.get(name)
        result: dict[str, Any] = candidate if isinstance(candidate, dict) else {}
        safe_services[name] = {
            "port": SERVICE_PORTS[name],
            "reachable": bool(result.get("reachable")),
            "schema_valid": bool(result.get("schema_valid")),
            "advertised_model_count": result.get("advertised_model_count"),
            "error_kind": result.get("error_kind"),
        }
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "adapter": {"name": "msty-local-ops", "version": __version__},
        "doctor": {
            "color": doctor["color"],
            "summary": doctor["summary"],
            "reason_codes": [
                (
                    "studio_missing"
                    if not studio.get("installed")
                    else (
                        "local_service_unavailable"
                        if not doctor["facts"]["valid_services"]
                        else (
                            "no_local_models"
                            if not doctor["facts"]["usable_services"]
                            else (
                                "studio_version_untested"
                                if studio.get("version_support") != "tested"
                                else "ready"
                            )
                        )
                    )
                )
            ],
        },
        "studio": {
            "installed": bool(studio.get("installed")),
            "version": studio.get("version"),
            "version_support": studio.get("version_support"),
        },
        "process": {"state": process.get("state"), "running": process.get("running")},
        "local_services": safe_services,
        "compatibility": {"overall_status": compatibility.get("overall_status")},
        "redaction": {
            "included": ["versions", "booleans", "counts", "fixed ports", "error categories"],
            "excluded": [
                "usernames",
                "filesystem paths",
                "hostnames and network addresses",
                "model identifiers and metadata",
                "prompts, chats, and document content",
                "provider names, credentials, and configuration",
                "process identifiers and executable paths",
            ],
        },
    }


def write_support_bundle(path: Path, payload: dict[str, Any], *, overwrite: bool = False) -> None:
    _private_json_write(path, payload, overwrite=overwrite)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.preview and args.output:
        parser.error("choose --preview or --output, not both")
    if not args.preview and not args.output:
        parser.error("choose --preview or provide --output")

    payload = build_support_bundle()
    if args.preview:
        print(json.dumps(payload, indent=2))
        return 0
    output = args.output.expanduser()
    try:
        write_support_bundle(output, payload, overwrite=args.force)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Support bundle was not written: {exc}")
        return 1
    print(f"Privacy-redacted support bundle written to: {output}")
    print("Review the JSON before sharing it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_support_bundle", "write_support_bundle"]
