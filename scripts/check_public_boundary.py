#!/usr/bin/env python3
"""Fail when a public tree contains common secret or machine-specific artifacts."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
}
EXCLUDED_FILES = {Path("scripts/check_public_boundary.py")}
FORBIDDEN_SUFFIXES = {".db", ".key", ".pem", ".p12", ".pfx", ".sqlite", ".sqlite3"}
FORBIDDEN_NAMES = {".DS_Store", ".env", "id_rsa", "id_ed25519"}
MAX_TEXT_BYTES = 2 * 1024 * 1024

PATTERNS = {
    "absolute macOS home path": re.compile(r"/Users/(?!<)[A-Za-z0-9._-]+/"),
    "absolute Windows home path": re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\\]+\\\\"),
    "email address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "private IPv4 address": re.compile(
        r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    ),
    "credential-like prefix": re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
        r"xox[abprs]-[A-Za-z0-9-]{16,})\b"
    ),
    "private key material": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "operational pull-request reference": re.compile(r"\bPR\s*#\d+\b", re.I),
    "private working branch": re.compile(r"\bcodex/[A-Za-z0-9._/-]+\b"),
}


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.is_symlink():
            yield path, "symlink"
        elif path.is_file():
            yield path, "file"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    findings: list[str] = []

    for path, kind in iter_files(root):
        relative = path.relative_to(root)
        if kind == "symlink":
            findings.append(f"{relative}: symlinks require explicit review")
            continue
        if path.name in FORBIDDEN_NAMES or path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            findings.append(f"{relative}: forbidden artifact type")
            continue
        if relative in EXCLUDED_FILES:
            continue
        raw = path.read_bytes()
        if len(raw) > MAX_TEXT_BYTES:
            findings.append(f"{relative}: file exceeds the public review size limit")
            continue
        if b"\0" in raw:
            findings.append(f"{relative}: binary file requires explicit review")
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"{relative}: non-UTF-8 file requires explicit review")
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{relative}:{line}: {label}")

    if findings:
        print("Public-boundary check failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Public-boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
