"""Strict loopback-only access to Msty's documented local model endpoints."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

LOOPBACK_HOST = "127.0.0.1"
SERVICE_PORTS = {
    "local_ai": 11964,
    "mlx": 11973,
    "llamacpp": 11454,
}
SERVICE_ORDER = tuple(SERVICE_PORTS)
ALLOWED_REQUESTS = frozenset(
    {
        ("GET", "/v1/models"),
        ("POST", "/v1/chat/completions"),
    }
)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_INVENTORY_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_MODELS_PER_SERVICE = 2_048
MAX_TOTAL_MODEL_RECORDS = 4_096
MAX_MODEL_ID_CHARS = 1_000
MAX_DECLARED_FIELD_BYTES = 16 * 1024
MAX_TOTAL_DECLARED_METADATA_BYTES = 2 * 1024 * 1024
MAX_PROMPT_CHARS = 65_536
MAX_SYSTEM_PROMPT_CHARS = 32_768
MAX_OUTPUT_TOKENS = 8_192


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N803
        return None


_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _NoRedirectHandler(),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _failure(
    service: str,
    endpoint: str,
    error_kind: str,
    error: str,
    *,
    status_code: int | None = None,
    latency_ms: float | None = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "service": service,
        "host": LOOPBACK_HOST,
        "port": SERVICE_PORTS.get(service),
        "endpoint": endpoint,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "error_kind": error_kind,
        "error": error,
    }


def request_json(
    service: str,
    endpoint: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 5,
) -> dict[str, Any]:
    """Call one fixed Msty loopback service without proxies or redirects."""
    normalized_method = method.strip().upper()
    if service not in SERVICE_PORTS:
        return _failure(service, endpoint, "unknown_service", "Unknown local service")
    if (normalized_method, endpoint) not in ALLOWED_REQUESTS:
        return _failure(
            service,
            endpoint,
            "endpoint_not_allowed",
            "Only the model inventory and chat-completion endpoints are allowed",
        )
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 180:
        return _failure(service, endpoint, "invalid_timeout", "Timeout must be 1 to 180 seconds")

    url = f"http://{LOOPBACK_HOST}:{SERVICE_PORTS[service]}{endpoint}"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, method=normalized_method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")

    started = time.monotonic()
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            latency_ms = round((time.monotonic() - started) * 1000, 2)
            if len(raw) > MAX_RESPONSE_BYTES:
                return _failure(
                    service,
                    endpoint,
                    "response_too_large",
                    "Local service response exceeded the safety limit",
                    status_code=response.status,
                    latency_ms=latency_ms,
                )
            try:
                data = json.loads(raw.decode("utf-8")) if raw else None
            except (UnicodeDecodeError, json.JSONDecodeError):
                return _failure(
                    service,
                    endpoint,
                    "invalid_json",
                    "Local service did not return valid JSON",
                    status_code=response.status,
                    latency_ms=latency_ms,
                )
            return {
                "success": response.status == 200,
                "service": service,
                "host": LOOPBACK_HOST,
                "port": SERVICE_PORTS[service],
                "endpoint": endpoint,
                "status_code": response.status,
                "latency_ms": latency_ms,
                "response_bytes": len(raw),
                "data": data,
                "error_kind": None if response.status == 200 else "unexpected_http_status",
                "error": None if response.status == 200 else f"HTTP {response.status}",
            }
    except urllib.error.HTTPError as exc:
        return _failure(
            service,
            endpoint,
            "http_error",
            f"HTTP {exc.code}: {exc.reason}",
            status_code=exc.code,
            latency_ms=round((time.monotonic() - started) * 1000, 2),
        )
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        lowered = reason.lower()
        if "refused" in lowered or "errno 61" in lowered or "errno 111" in lowered:
            error_kind = "connection_refused"
        elif "timed out" in lowered or "timeout" in lowered:
            error_kind = "timeout"
        elif "not permitted" in lowered or "permission denied" in lowered:
            error_kind = "host_policy_blocked"
        else:
            error_kind = "connection_error"
        return _failure(
            service,
            endpoint,
            error_kind,
            reason,
            latency_ms=round((time.monotonic() - started) * 1000, 2),
        )
    except (OSError, TimeoutError) as exc:
        return _failure(
            service,
            endpoint,
            "connection_error",
            str(exc),
            latency_ms=round((time.monotonic() - started) * 1000, 2),
        )


def _models_from_response(
    response: dict[str, Any],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    data = response.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return None, "invalid_model_list_schema"
    if len(data["data"]) > MAX_MODELS_PER_SERVICE:
        return None, "model_record_limit_exceeded"
    return [item for item in data["data"] if isinstance(item, dict)], None


def probe_services() -> dict[str, dict[str, Any]]:
    """Probe all fixed local services and validate their model-list schema."""
    results: dict[str, dict[str, Any]] = {}
    total_response_bytes = 0
    total_records = 0
    for service in SERVICE_ORDER:
        response = request_json(service, "/v1/models")
        response_bytes = response.get("response_bytes", 0)
        if not isinstance(response_bytes, int) or isinstance(response_bytes, bool):
            response_bytes = 0
        total_response_bytes += response_bytes
        models, schema_error = (
            _models_from_response(response)
            if response.get("success")
            else (None, response.get("error_kind"))
        )
        if models is not None and (
            total_response_bytes > MAX_INVENTORY_RESPONSE_BYTES
            or total_records + len(models) > MAX_TOTAL_MODEL_RECORDS
        ):
            models = None
            schema_error = "aggregate_inventory_limit_exceeded"
        if models is not None:
            total_records += len(models)
        results[service] = {
            "host": LOOPBACK_HOST,
            "port": SERVICE_PORTS[service],
            "reachable": response.get("success", False),
            "status_code": response.get("status_code"),
            "latency_ms": response.get("latency_ms"),
            "schema_valid": models is not None,
            "advertised_model_count": len(models) if models is not None else None,
            "response_bytes": response_bytes,
            "error_kind": schema_error or response.get("error_kind"),
            "error": response.get("error"),
        }
    return results


def build_model_manifest() -> dict[str, Any]:
    """Return model facts exactly as advertised by reachable local services."""
    records: list[dict[str, Any]] = []
    services: dict[str, dict[str, Any]] = {}
    seen: dict[str, list[str]] = {}
    total_response_bytes = 0
    total_records = 0
    total_declared_metadata_bytes = 0
    skipped_model_ids = 0
    omitted_declared_fields = 0

    for service in SERVICE_ORDER:
        response = request_json(service, "/v1/models")
        response_bytes = response.get("response_bytes", 0)
        if not isinstance(response_bytes, int) or isinstance(response_bytes, bool):
            response_bytes = 0
        total_response_bytes += response_bytes
        raw_models, schema_error = (
            _models_from_response(response)
            if response.get("success")
            else (None, response.get("error_kind"))
        )
        if raw_models is not None and (
            total_response_bytes > MAX_INVENTORY_RESPONSE_BYTES
            or total_records + len(raw_models) > MAX_TOTAL_MODEL_RECORDS
        ):
            raw_models = None
            schema_error = "aggregate_inventory_limit_exceeded"
        if raw_models is not None:
            total_records += len(raw_models)
        services[service] = {
            "host": LOOPBACK_HOST,
            "port": SERVICE_PORTS[service],
            "reachable": response.get("success", False),
            "schema_valid": raw_models is not None,
            "advertised_model_count": len(raw_models) if raw_models is not None else None,
            "response_bytes": response_bytes,
            "error_kind": schema_error or response.get("error_kind"),
            "error": response.get("error"),
        }
        for raw in raw_models or []:
            raw_model_id = raw.get("id")
            if not isinstance(raw_model_id, str):
                skipped_model_ids += 1
                continue
            model_id = raw_model_id.strip()
            if not model_id or len(model_id) > MAX_MODEL_ID_CHARS:
                skipped_model_ids += 1
                continue
            raw_loaded = raw.get("loaded")
            loaded = raw_loaded if isinstance(raw_loaded, bool) else None
            declared = {}
            declared_omissions = []
            for key in (
                "name",
                "type",
                "task",
                "pipeline_tag",
                "capabilities",
                "tags",
                "context_length",
                "quantization",
            ):
                if key not in raw:
                    continue
                encoded = json.dumps(raw[key], ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
                if (
                    len(encoded) > MAX_DECLARED_FIELD_BYTES
                    or total_declared_metadata_bytes + len(encoded)
                    > MAX_TOTAL_DECLARED_METADATA_BYTES
                ):
                    omitted_declared_fields += 1
                    declared_omissions.append(key)
                    continue
                declared[key] = raw[key]
                total_declared_metadata_bytes += len(encoded)
            record = {
                "id": model_id,
                "service": service,
                "port": SERVICE_PORTS[service],
                "declared_metadata": declared,
                "declared_metadata_omissions": declared_omissions,
                "state": {
                    "installed_on_disk": None,
                    "registered_with_service": True,
                    "advertised_by_service": True,
                    "service_reachable": True,
                    "loaded": loaded,
                    "inference_verified": None,
                },
                "evidence": {
                    "source": f"{service}:/v1/models",
                    "observed_at": utc_now(),
                    "installed_on_disk": "not_checked",
                    "loaded": "service_field" if isinstance(raw_loaded, bool) else "not_reported",
                    "inference_verified": "not_tested",
                },
            }
            records.append(record)
            seen.setdefault(model_id, []).append(service)

    duplicate_registrations = [
        {"model_id": model_id, "services": service_names}
        for model_id, service_names in sorted(seen.items())
        if len(service_names) > 1
    ]
    loaded_values = [record["state"]["loaded"] for record in records]
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "trust_class": "local_loopback_inventory",
        "services": services,
        "models": records,
        "state_summary": {
            "advertised_records": len(records),
            "unique_model_ids": len(seen),
            "loaded": {
                "true": sum(value is True for value in loaded_values),
                "false": sum(value is False for value in loaded_values),
                "unknown": sum(value is None for value in loaded_values),
            },
            "inference_verified": {
                "true": 0,
                "false": 0,
                "unknown": len(records),
            },
        },
        "conflicts": {"duplicate_registrations": duplicate_registrations},
        "limits": {
            "response_bytes_per_service": MAX_RESPONSE_BYTES,
            "inventory_response_bytes_total": MAX_INVENTORY_RESPONSE_BYTES,
            "model_records_per_service": MAX_MODELS_PER_SERVICE,
            "model_records_total": MAX_TOTAL_MODEL_RECORDS,
            "model_id_characters": MAX_MODEL_ID_CHARS,
            "declared_field_bytes": MAX_DECLARED_FIELD_BYTES,
            "declared_metadata_bytes_total": MAX_TOTAL_DECLARED_METADATA_BYTES,
        },
        "inventory_budget": {
            "response_bytes_observed": total_response_bytes,
            "model_records_accepted": len(records),
            "declared_metadata_bytes_accepted": total_declared_metadata_bytes,
            "skipped_model_ids": skipped_model_ids,
            "omitted_declared_fields": omitted_declared_fields,
        },
        "evaluation": {
            "status": "not_evaluated",
            "champions": {},
            "note": "No recommendation is emitted without a versioned evaluation suite.",
        },
    }


def _validate_generation_inputs(
    model: str,
    message: str,
    system_prompt: str | None,
    temperature: float,
    max_tokens: int,
    service: str | None,
) -> str | None:
    if not isinstance(model, str) or not model.strip() or len(model) > 1_000:
        return "model must be a non-empty string of at most 1,000 characters"
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_PROMPT_CHARS:
        return f"message must be non-empty and at most {MAX_PROMPT_CHARS:,} characters"
    if system_prompt is not None and (
        not isinstance(system_prompt, str) or len(system_prompt) > MAX_SYSTEM_PROMPT_CHARS
    ):
        return f"system_prompt must be at most {MAX_SYSTEM_PROMPT_CHARS:,} characters"
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        return "temperature must be a number"
    if not 0 <= float(temperature) <= 2:
        return "temperature must be between 0 and 2"
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        return "max_tokens must be an integer"
    if not 1 <= max_tokens <= MAX_OUTPUT_TOKENS:
        return f"max_tokens must be between 1 and {MAX_OUTPUT_TOKENS}"
    if service is not None and service not in SERVICE_PORTS:
        return "service must be local_ai, mlx, or llamacpp"
    return None


def _extract_content(data: Any) -> tuple[str | None, int | None, str | None]:
    if not isinstance(data, dict):
        return None, None, None
    choices = data.get("choices")
    content: Any = None
    finish_reason = None
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        raw_finish_reason = choices[0].get("finish_reason")
        if raw_finish_reason is not None:
            finish_reason = str(raw_finish_reason)
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = message.get("content")
        if content is None:
            content = choices[0].get("text")
    if content is None:
        for key in ("response", "content", "text", "output"):
            if data.get(key) is not None:
                content = data[key]
                break
    usage = data.get("usage")
    completion_tokens = None
    if isinstance(usage, dict):
        raw_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
        if isinstance(raw_tokens, int) and not isinstance(raw_tokens, bool):
            completion_tokens = raw_tokens
    return (str(content) if content is not None else None), completion_tokens, finish_reason


def local_generate_request(
    *,
    model: str,
    message: str,
    service: str | None = None,
    system_prompt: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1_024,
) -> dict[str, Any]:
    """Generate through one explicitly selected, advertised local model."""
    validation_error = _validate_generation_inputs(
        model,
        message,
        system_prompt,
        temperature,
        max_tokens,
        service,
    )
    if validation_error:
        return {"success": False, "error_kind": "invalid_parameter", "error": validation_error}

    matches: list[str] = []
    inventory_errors: dict[str, str] = {}
    for candidate_service in ([service] if service else SERVICE_ORDER):
        if candidate_service is None:
            continue
        inventory = request_json(candidate_service, "/v1/models")
        models, inventory_error = (
            _models_from_response(inventory)
            if inventory.get("success")
            else (None, str(inventory.get("error_kind") or "inventory_unavailable"))
        )
        if models is None:
            inventory_errors[candidate_service] = str(
                inventory_error or "invalid_model_list_schema"
            )
            continue
        for raw in models:
            if str(raw.get("id") or "") == model:
                matches.append(candidate_service)
                break

    if not matches:
        if inventory_errors:
            return {
                "success": False,
                "error_kind": "inventory_unavailable",
                "error": "The selected local model inventory could not be validated",
                "services": inventory_errors,
            }
        return {
            "success": False,
            "error_kind": "model_not_advertised",
            "error": "The requested model is not advertised by the selected local service(s)",
        }
    if len(matches) > 1 and service is None:
        return {
            "success": False,
            "error_kind": "ambiguous_model",
            "error": "The model is advertised by multiple services; specify service explicitly",
            "services": matches,
        }

    selected_service = matches[0]
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": max_tokens,
        "stream": False,
    }
    response = request_json(
        selected_service,
        "/v1/chat/completions",
        method="POST",
        payload=payload,
        timeout=180,
    )
    if not response.get("success"):
        return {
            "success": False,
            "simulated": False,
            "model": model,
            "service": selected_service,
            "error_kind": response.get("error_kind"),
            "error": response.get("error"),
            "latency_ms": response.get("latency_ms"),
        }

    content, completion_tokens, finish_reason = _extract_content(response.get("data"))
    if finish_reason in {"length", "max_tokens"}:
        return {
            "success": False,
            "simulated": False,
            "model": model,
            "service": selected_service,
            "error_kind": "output_truncated",
            "error": "The local model exhausted max_tokens before a complete answer",
            "completion_tokens": completion_tokens,
            "latency_ms": response.get("latency_ms"),
        }
    if content is None or not content.strip() or completion_tokens == 0:
        return {
            "success": False,
            "simulated": False,
            "model": model,
            "service": selected_service,
            "error_kind": "empty_completion",
            "error": "The local model returned no usable completion",
            "latency_ms": response.get("latency_ms"),
        }
    return {
        "success": True,
        "simulated": False,
        "trust_class": "local_loopback_inference",
        "model": model,
        "service": selected_service,
        "content": content,
        "completion_tokens": completion_tokens,
        "finish_reason": finish_reason,
        "latency_ms": response.get("latency_ms"),
        "observed_at": utc_now(),
        "cloud_fallback": False,
        "persistence": "not_performed_by_msty_ops",
    }


__all__ = [
    "LOOPBACK_HOST",
    "SERVICE_PORTS",
    "SERVICE_ORDER",
    "request_json",
    "probe_services",
    "build_model_manifest",
    "local_generate_request",
    "utc_now",
]
