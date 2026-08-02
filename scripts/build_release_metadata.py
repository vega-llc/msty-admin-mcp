#!/usr/bin/env python3
"""Generate a CycloneDX SBOM, build statement, and checksums for release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _components(requirements: Path) -> list[dict[str, str]]:
    found: dict[str, str] = {}
    for line in requirements.read_text(encoding="utf-8").splitlines():
        match = REQUIREMENT.match(line)
        if match:
            found[match.group(1).lower().replace("_", "-")] = match.group(2)
    return [
        {
            "type": "library",
            "name": name,
            "version": version,
            "bom-ref": f"pkg:pypi/{name}@{version}",
            "purl": f"pkg:pypi/{name}@{version}",
        }
        for name, version in sorted(found.items())
    ]


def generate(dist: Path, requirements: Path, version: str) -> None:
    dist.mkdir(parents=True, exist_ok=True)
    timestamp = _now()
    package_ref = f"pkg:pypi/msty-local-ops@{version}"
    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        ":".join(
            [
                os.environ.get("GITHUB_REPOSITORY", "vega-llc/msty-local-ops"),
                os.environ.get("GITHUB_RUN_ID", "local"),
                version,
            ]
        ),
    )
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "component": {
                "type": "application",
                "name": "msty-local-ops",
                "version": version,
                "bom-ref": package_ref,
                "purl": package_ref,
            },
        },
        "components": _components(requirements),
    }
    (dist / "msty-local-ops.cdx.json").write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    provenance = {
        "schema_version": 1,
        "generated_at": timestamp,
        "subject": {"name": "msty-local-ops", "version": version},
        "source": {
            "repository": os.environ.get("GITHUB_SERVER_URL", "https://github.com")
            + "/"
            + os.environ.get("GITHUB_REPOSITORY", "vega-llc/msty-local-ops"),
            "commit": os.environ.get("GITHUB_SHA", "local-build"),
            "ref": os.environ.get("GITHUB_REF", "local-build"),
        },
        "builder": {
            "workflow": os.environ.get("GITHUB_WORKFLOW", "local-build"),
            "run_id": os.environ.get("GITHUB_RUN_ID", "local-build"),
        },
        "note": "GitHub release builds also receive a signed artifact attestation.",
    }
    (dist / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    assets = sorted(path for path in dist.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    lines = []
    for asset in assets:
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()
        lines.append(f"{digest}  {asset.name}")
    (dist / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--requirements", type=Path, default=Path("requirements-audit.txt"))
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    generate(args.dist, args.requirements, args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
