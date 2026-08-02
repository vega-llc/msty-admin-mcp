#!/usr/bin/env python3
"""Require a final, exact vMAJOR.MINOR.PATCH tag matching pyproject.toml."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import tomli

FINAL_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def validate(tag: str, pyproject: Path) -> str:
    match = FINAL_TAG.fullmatch(tag)
    if not match:
        raise ValueError("release tag must be final and exactly vMAJOR.MINOR.PATCH")
    with pyproject.open("rb") as stream:
        version = tomli.load(stream)["project"]["version"]
    if tag != f"v{version}":
        raise ValueError(f"tag {tag!r} does not match project version {version!r}")
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args()
    try:
        version = validate(args.tag, args.pyproject)
    except (OSError, KeyError, ValueError) as exc:
        print(f"Release validation failed: {exc}")
        return 1
    print(f"Release tag validated for version {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
