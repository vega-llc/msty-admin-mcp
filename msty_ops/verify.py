"""Run a fixed public/synthetic local-model canary with no private inputs."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .doctor import assess
from .runtime import SERVICE_PORTS, THINKING_MODES, local_generate_request, utc_now

CANARY_PROMPT = (
    "This is a public synthetic health check. Return exactly one JSON object: "
    '{"status":"LOCAL_CANARY_OK","sum":42}'
)
EXPECTED = {"status": "LOCAL_CANARY_OK", "sum": 42}


def _parse_exact_json(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content.strip())
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def verify(
    *,
    model: str | None = None,
    service: str | None = None,
    thinking_mode: str = "none",
    doctor_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if (model is None) != (service is None):
        raise ValueError("model and service must be provided together")
    if service is not None and service not in SERVICE_PORTS:
        raise ValueError("service must be local_ai, mlx, or llamacpp")
    if thinking_mode not in THINKING_MODES:
        raise ValueError("thinking_mode must be default or none")

    doctor = doctor_report if doctor_report is not None else assess()
    canary: dict[str, Any]
    if model is None:
        canary = {
            "status": "not_run",
            "reason": "provide an exact local model and service to run inference",
        }
    else:
        result = local_generate_request(
            model=model,
            service=service,
            message=CANARY_PROMPT,
            temperature=0.0,
            max_tokens=128,
            thinking_mode=thinking_mode,
        )
        parsed = _parse_exact_json(result.get("content")) if result.get("success") else None
        passed = parsed == EXPECTED
        canary = {
            "status": "pass" if passed else "fail",
            "success": passed,
            "model": model,
            "service": service,
            "thinking_mode": thinking_mode,
            "latency_ms": result.get("latency_ms"),
            "error_kind": None if passed else result.get("error_kind", "unexpected_output"),
        }

    doctor_green = doctor.get("color") == "green"
    inference_passed = canary.get("status") in {"not_run", "pass"}
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "status": "pass" if doctor_green and inference_passed else "fail",
        "doctor": {
            "color": doctor.get("color"),
            "summary": doctor.get("summary"),
            "baseline_state": (doctor.get("baseline") or {}).get("state"),
        },
        "synthetic_canary": canary,
        "privacy": {
            "fixed_public_prompt_only": True,
            "reads_chats": False,
            "reads_knowledge_stacks": False,
            "reads_provider_credentials": False,
            "reads_msty_database": False,
            "cloud_fallback": False,
            "persistence": "none",
        },
        "scope": "ordinary_local_diagnostics_only",
    }


def _render_text(report: dict[str, Any]) -> str:
    lines = [f"Msty Local Ops Verify: {report['status'].upper()}"]
    lines.append(f"  Doctor: {report['doctor']['color'].upper()}")
    lines.append(f"  Synthetic inference: {report['synthetic_canary']['status'].upper()}")
    lines.append("  Scope: ordinary local diagnostics only")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument("--service", choices=tuple(SERVICE_PORTS))
    parser.add_argument("--thinking-mode", choices=tuple(sorted(THINKING_MODES)), default="none")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = verify(
            model=args.model,
            service=args.service,
            thinking_mode=args.thinking_mode,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2) if args.json else _render_text(report))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CANARY_PROMPT", "EXPECTED", "verify"]
