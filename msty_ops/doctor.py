"""Plain-language health and upgrade-drift checks for Msty Local Ops."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .manifests import compatibility_manifest, status_manifest
from .runtime import utc_now

DEFAULT_BASELINE = (
    Path.home() / "Library" / "Application Support" / "Msty Local Ops" / "state" / "baseline.json"
)
BASELINE_SCHEMA_VERSION = 1
MAX_BASELINE_BYTES = 64 * 1024
COLORS = ("green", "yellow", "red")


def _fingerprint_facts(status: dict[str, Any]) -> dict[str, Any]:
    services = status.get("local_services") or {}
    return {
        "adapter_version": __version__,
        "studio_version": (status.get("studio") or {}).get("version"),
        "services": {
            name: {
                "reachable": bool(result.get("reachable")),
                "schema_valid": bool(result.get("schema_valid")),
                "advertised_model_count": result.get("advertised_model_count"),
            }
            for name, result in sorted(services.items())
            if isinstance(result, dict)
        },
    }


def fingerprint(status: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    facts = _fingerprint_facts(status)
    canonical = json.dumps(facts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest(), facts


def load_baseline(path: Path) -> tuple[str, dict[str, Any] | None]:
    """Return a bounded baseline state without following a final-component symlink."""
    if path.is_symlink():
        return "invalid", None
    try:
        if not path.exists():
            return "not_recorded", None
        with path.open("rb") as stream:
            raw = stream.read(MAX_BASELINE_BYTES + 1)
        if len(raw) > MAX_BASELINE_BYTES:
            return "invalid", None
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "invalid", None
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != BASELINE_SCHEMA_VERSION
        or not isinstance(value.get("fingerprint"), str)
        or not isinstance(value.get("facts"), dict)
    ):
        return "invalid", None
    return "loaded", value


def _private_json_write(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    if path.is_symlink():
        raise ValueError("Refusing to write through a symlink")
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def record_baseline(path: Path, status: dict[str, Any]) -> dict[str, Any]:
    value, facts = fingerprint(status)
    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "recorded_at": utc_now(),
        "fingerprint": value,
        "facts": facts,
    }
    _private_json_write(path, payload, overwrite=True)
    return payload


def assess(
    status: dict[str, Any] | None = None,
    compatibility: dict[str, Any] | None = None,
    *,
    baseline_path: Path | None = DEFAULT_BASELINE,
) -> dict[str, Any]:
    status = status if status is not None else status_manifest()
    compatibility = compatibility if compatibility is not None else compatibility_manifest()
    studio = status.get("studio") or {}
    services = status.get("local_services") or {}
    valid_services = [
        name
        for name, result in services.items()
        if isinstance(result, dict) and result.get("reachable") and result.get("schema_valid")
    ]
    usable_services = [
        name
        for name in valid_services
        if isinstance(services[name].get("advertised_model_count"), int)
        and services[name]["advertised_model_count"] > 0
    ]
    model_count = sum(
        result.get("advertised_model_count") or 0
        for result in services.values()
        if isinstance(result, dict) and isinstance(result.get("advertised_model_count"), int)
    )

    reasons: list[str] = []
    actions: list[str] = []
    if not studio.get("installed"):
        color = "red"
        reasons.append("Msty Studio was not found in Applications.")
        actions.append("Install Msty Studio, open it once, and run the doctor again.")
    elif not valid_services:
        color = "red"
        reasons.append("No valid local model service is reachable on Msty's loopback ports.")
        actions.append("Start Msty Studio and start or load a local model, then retry.")
    elif not usable_services:
        color = "yellow"
        reasons.append("Local services respond, but none advertises an available model.")
        actions.append("Download or load a local model in Msty before using local inference.")
    elif studio.get("version_support") != "tested":
        color = "yellow"
        reasons.append("The installed Msty Studio version has not been tested by this release.")
        actions.append("Run the synthetic canary before trusting the upgraded setup.")
    else:
        color = "green"
        reasons.append("Msty Studio and at least one tested local model service are ready.")
        actions.append("Use the diagnostic MCP first; enable local inference only when needed.")

    current_fingerprint, current_facts = fingerprint(status)
    baseline_state = "disabled"
    baseline_recorded_at = None
    if baseline_path is not None:
        load_state, baseline = load_baseline(baseline_path)
        baseline_state = load_state
        if baseline:
            baseline_recorded_at = baseline.get("recorded_at")
            if baseline.get("fingerprint") == current_fingerprint:
                baseline_state = "current"
            else:
                baseline_state = "changed"
                if color == "green":
                    color = "yellow"
                reasons.append("The local setup changed since the last known-good baseline.")
                actions.append(
                    "Re-run compatibility and synthetic canary tests, then re-record it."
                )
        elif load_state == "invalid":
            if color == "green":
                color = "yellow"
            reasons.append("The saved upgrade baseline is invalid or unsafe to read.")
            actions.append("Remove it manually after review, then record a fresh green baseline.")

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "color": color,
        "summary": {"green": "ready", "yellow": "needs review", "red": "not ready"}[color],
        "reasons": reasons,
        "next_actions": actions,
        "facts": {
            "adapter_version": __version__,
            "studio_installed": bool(studio.get("installed")),
            "studio_version": studio.get("version"),
            "studio_version_support": studio.get("version_support"),
            "valid_services": sorted(valid_services),
            "usable_services": sorted(usable_services),
            "advertised_model_count": model_count,
            "compatibility_status": compatibility.get("overall_status"),
        },
        "baseline": {
            "state": baseline_state,
            "recorded_at": baseline_recorded_at,
            "current_fingerprint": current_fingerprint,
            "current_facts": current_facts,
        },
        "privacy": {
            "reads_chats": False,
            "reads_provider_credentials": False,
            "reads_msty_database": False,
            "submits_prompts": False,
        },
    }


def _render_text(report: dict[str, Any]) -> str:
    lines = [f"Msty Local Ops: {report['color'].upper()} - {report['summary']}"]
    lines.extend(f"  - {reason}" for reason in report["reasons"])
    lines.append(f"  Models advertised: {report['facts']['advertised_model_count']}")
    lines.append(f"  Upgrade baseline: {report['baseline']['state']}")
    lines.append("Next:")
    lines.extend(f"  - {action}" for action in report["next_actions"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--record-baseline", action="store_true")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--no-baseline", action="store_true")
    args = parser.parse_args()

    baseline_path = None if args.no_baseline else args.baseline.expanduser()
    status = status_manifest()
    report = assess(status, baseline_path=baseline_path)
    if args.record_baseline:
        if baseline_path is None:
            parser.error("--record-baseline cannot be combined with --no-baseline")
        if report["color"] == "red":
            print(_render_text(report))
            print("Baseline not recorded because the setup is RED.")
            return 1
        record_baseline(baseline_path, status)
        report = assess(status, baseline_path=baseline_path)

    print(json.dumps(report, indent=2) if args.json else _render_text(report))
    return {"green": 0, "yellow": 2, "red": 1}[report["color"]]


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["DEFAULT_BASELINE", "assess", "fingerprint", "load_baseline", "record_baseline"]
