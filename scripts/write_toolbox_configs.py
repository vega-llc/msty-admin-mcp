#!/usr/bin/env python3
"""Write ready-to-paste Msty Toolbox configurations for an installed environment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def write_config(output: Path, python: Path, module: str) -> None:
    payload = {
        "command": str(python),
        "args": ["-m", module],
        "env": {"PYTHONUNBUFFERED": "1"},
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    python = args.python.expanduser().resolve()
    if not python.is_file() or not os.access(python, os.X_OK):
        parser.error("--python must point to an executable Python interpreter")

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    diagnostic = output / "msty-toolbox-diagnostic.json"
    local = output / "msty-toolbox-local-inference.json"
    write_config(diagnostic, python, "msty_ops.server")
    write_config(local, python, "msty_ops.local_server")

    print(json.dumps({"diagnostic": str(diagnostic), "local_inference": str(local)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
