"""Contract tests for the allowlist-by-construction modern servers."""

import importlib
import json
import os
import subprocess
import sys
from io import BytesIO
from urllib.error import HTTPError

import pytest

from msty_ops import manifests, runtime

EXPECTED_DIAGNOSTIC_TOOLS = {
    "get_msty_status",
    "get_capability_manifest",
    "get_model_manifest",
    "run_compatibility_check",
}
EXPECTED_LOCAL_TOOLS = EXPECTED_DIAGNOSTIC_TOOLS | {"local_generate"}


def test_diagnostic_server_is_a_four_tool_direct_allowlist(monkeypatch):
    monkeypatch.setenv("MSTY_MCP_PROFILE", "full")
    server = importlib.import_module("msty_ops.server")

    assert set(server.mcp._tool_manager._tools) == EXPECTED_DIAGNOSTIC_TOOLS
    assert server.mcp._resource_manager._resources == {}
    assert server.mcp._prompt_manager._prompts == {}

    report = json.loads(server.get_capability_manifest())
    assert report["tool_count"] == 4
    assert report["construction"] == "direct_allowlist"
    assert "legacy" not in report
    assert "legacy_modules_loaded" not in report
    assert report["network_policy"]["cloud_fallback"] is False


def test_local_server_adds_only_explicit_local_generation(monkeypatch):
    monkeypatch.setenv("MSTY_MCP_PROFILE", "full")
    server = importlib.import_module("msty_ops.local_server")

    assert set(server.mcp._tool_manager._tools) == EXPECTED_LOCAL_TOOLS
    assert server.mcp._resource_manager._resources == {}
    assert server.mcp._prompt_manager._prompts == {}


def test_modern_imports_do_not_load_legacy_server():
    code = """
import json
import sys
import msty_ops.server
import msty_ops.local_server
print(json.dumps(sorted(name for name in sys.modules if name.startswith('src'))))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=dict(os.environ, MSTY_MCP_PROFILE="full"),
    )

    assert json.loads(completed.stdout) == []


def test_modern_runtime_has_fixed_loopback_destinations(monkeypatch):
    monkeypatch.setenv("MSTY_HOST", "example.com")
    monkeypatch.setenv("MSTY_MLX_PORT", "443")

    assert runtime.LOOPBACK_HOST == "127.0.0.1"
    assert runtime.SERVICE_PORTS == {
        "local_ai": 11964,
        "mlx": 11973,
        "llamacpp": 11454,
    }


def test_runtime_rejects_unknown_endpoints_before_network(monkeypatch):
    monkeypatch.setattr(
        runtime._OPENER,
        "open",
        lambda *args, **kwargs: pytest.fail("network should not be called"),
    )

    result = runtime.request_json("mlx", "/admin/secrets")

    assert result["success"] is False
    assert result["error_kind"] == "endpoint_not_allowed"


class _Response:
    def __init__(self, payload: dict, status: int = 200):
        self.status = status
        self._stream = BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self, amount: int = -1) -> bytes:
        return self._stream.read(amount)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_model_manifest_preserves_unknown_state(monkeypatch):
    def fake_request(service, endpoint, **kwargs):
        assert endpoint == "/v1/models"
        return {
            "success": True,
            "data": {"data": [{"id": f"{service}-model"}]},
            "error_kind": None,
            "error": None,
        }

    monkeypatch.setattr(runtime, "request_json", fake_request)

    manifest = runtime.build_model_manifest()

    assert manifest["state_summary"]["advertised_records"] == 3
    assert manifest["state_summary"]["loaded"]["unknown"] == 3
    assert all(model["state"]["installed_on_disk"] is None for model in manifest["models"])
    assert manifest["evaluation"]["status"] == "not_evaluated"
    assert manifest["evaluation"]["champions"] == {}


def test_model_manifest_bounds_declared_metadata(monkeypatch):
    oversized = "x" * (runtime.MAX_DECLARED_FIELD_BYTES + 1)

    def fake_request(service, endpoint, **kwargs):
        models = [{"id": "bounded-model", "tags": oversized}] if service == "mlx" else []
        return {
            "success": True,
            "response_bytes": 100,
            "data": {"data": models},
            "error_kind": None,
            "error": None,
        }

    monkeypatch.setattr(runtime, "request_json", fake_request)

    manifest = runtime.build_model_manifest()

    model = manifest["models"][0]
    assert model["declared_metadata"] == {}
    assert model["declared_metadata_omissions"] == ["tags"]
    assert manifest["inventory_budget"]["omitted_declared_fields"] == 1


def test_model_manifest_rejects_aggregate_inventory_over_budget(monkeypatch):
    def fake_request(service, endpoint, **kwargs):
        return {
            "success": True,
            "response_bytes": runtime.MAX_RESPONSE_BYTES,
            "data": {"data": []},
            "error_kind": None,
            "error": None,
        }

    monkeypatch.setattr(runtime, "request_json", fake_request)

    manifest = runtime.build_model_manifest()

    assert manifest["services"]["local_ai"]["schema_valid"] is True
    assert manifest["services"]["mlx"]["schema_valid"] is True
    assert manifest["services"]["llamacpp"]["schema_valid"] is False
    assert manifest["services"]["llamacpp"]["error_kind"] == "aggregate_inventory_limit_exceeded"


def test_local_generate_requires_an_advertised_explicit_model(monkeypatch):
    calls = []

    def fake_request(service, endpoint, **kwargs):
        calls.append((service, endpoint, kwargs.get("method", "GET")))
        return {"success": True, "data": {"data": []}}

    monkeypatch.setattr(runtime, "request_json", fake_request)

    result = runtime.local_generate_request(model="missing", message="synthetic test")

    assert result["success"] is False
    assert result["error_kind"] == "model_not_advertised"
    assert all(endpoint == "/v1/models" for _, endpoint, _ in calls)


def test_local_generate_never_simulates_empty_output(monkeypatch):
    def fake_request(service, endpoint, **kwargs):
        if endpoint == "/v1/models":
            return {"success": True, "data": {"data": [{"id": "test-model"}]}}
        return {
            "success": True,
            "latency_ms": 2.0,
            "data": {"choices": [{"message": {"content": ""}}]},
        }

    monkeypatch.setattr(runtime, "request_json", fake_request)

    result = runtime.local_generate_request(
        model="test-model",
        message="synthetic test",
        service="mlx",
    )

    assert result["success"] is False
    assert result["simulated"] is False
    assert result["error_kind"] == "empty_completion"


def test_local_generate_rejects_truncated_reasoning_as_an_answer(monkeypatch):
    def fake_request(service, endpoint, **kwargs):
        if endpoint == "/v1/models":
            return {"success": True, "data": {"data": [{"id": "test-model"}]}}
        return {
            "success": True,
            "latency_ms": 2.0,
            "data": {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "unfinished reasoning"},
                    }
                ],
                "usage": {"completion_tokens": 256},
            },
        }

    monkeypatch.setattr(runtime, "request_json", fake_request)

    result = runtime.local_generate_request(
        model="test-model",
        message="synthetic test",
        service="mlx",
        max_tokens=256,
    )

    assert result["success"] is False
    assert result["simulated"] is False
    assert result["error_kind"] == "output_truncated"
    assert "unfinished reasoning" not in json.dumps(result)


def test_local_generate_rejects_budget_exhaustion_even_when_service_reports_stop(monkeypatch):
    def fake_request(service, endpoint, **kwargs):
        if endpoint == "/v1/models":
            return {"success": True, "data": {"data": [{"id": "test-model"}]}}
        return {
            "success": True,
            "latency_ms": 2.0,
            "data": {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "unfinished reasoning at the token ceiling"},
                    }
                ],
                "usage": {"completion_tokens": 256},
            },
        }

    monkeypatch.setattr(runtime, "request_json", fake_request)

    result = runtime.local_generate_request(
        model="test-model",
        message="synthetic test",
        service="mlx",
        max_tokens=256,
    )

    assert result["success"] is False
    assert result["error_kind"] == "output_truncated"
    assert "unfinished reasoning" not in json.dumps(result)


def test_local_generate_can_disable_thinking_without_arbitrary_parameters(monkeypatch):
    chat_payload = None

    def fake_request(service, endpoint, **kwargs):
        nonlocal chat_payload
        if endpoint == "/v1/models":
            return {"success": True, "data": {"data": [{"id": "test-model"}]}}
        chat_payload = kwargs["payload"]
        return {
            "success": True,
            "latency_ms": 2.0,
            "data": {
                "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
                "usage": {"completion_tokens": 1},
            },
        }

    monkeypatch.setattr(runtime, "request_json", fake_request)

    result = runtime.local_generate_request(
        model="test-model",
        message="synthetic test",
        service="mlx",
        thinking_mode="none",
    )

    assert result["success"] is True
    assert result["thinking_mode"] == "none"
    assert chat_payload is not None
    assert chat_payload["chat_template_kwargs"] == {"enable_thinking": False}


def test_local_generate_default_omits_thinking_override(monkeypatch):
    chat_payload = None

    def fake_request(service, endpoint, **kwargs):
        nonlocal chat_payload
        if endpoint == "/v1/models":
            return {"success": True, "data": {"data": [{"id": "test-model"}]}}
        chat_payload = kwargs["payload"]
        return {
            "success": True,
            "latency_ms": 2.0,
            "data": {
                "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
                "usage": {"completion_tokens": 1},
            },
        }

    monkeypatch.setattr(runtime, "request_json", fake_request)

    result = runtime.local_generate_request(
        model="test-model",
        message="synthetic test",
        service="mlx",
    )

    assert result["success"] is True
    assert result["thinking_mode"] == "default"
    assert chat_payload is not None
    assert "chat_template_kwargs" not in chat_payload


def test_local_generate_rejects_unknown_thinking_mode(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "request_json",
        lambda *args, **kwargs: pytest.fail("invalid input must not reach a service"),
    )

    result = runtime.local_generate_request(
        model="test-model",
        message="synthetic test",
        service="mlx",
        thinking_mode="unbounded",
    )

    assert result["success"] is False
    assert result["error_kind"] == "invalid_parameter"


def test_http_errors_do_not_read_or_return_response_body(monkeypatch):
    error = HTTPError(
        url="http://127.0.0.1:11973/v1/models",
        code=500,
        msg="failure",
        hdrs=None,
        fp=BytesIO(b"private prompt echo"),
    )
    monkeypatch.setattr(
        runtime._OPENER, "open", lambda *args, **kwargs: (_ for _ in ()).throw(error)
    )

    result = runtime.request_json("mlx", "/v1/models")

    assert result["error_kind"] == "http_error"
    assert "private prompt" not in json.dumps(result)


def test_process_inspection_denial_is_unknown_not_not_detected(monkeypatch):
    class DeniedProcess:
        @property
        def info(self):
            raise manifests.psutil.AccessDenied(pid=42)

    monkeypatch.setattr(
        manifests.psutil,
        "process_iter",
        lambda attrs: [DeniedProcess()],
    )

    result = manifests._process_info()

    assert result["state"] == "unknown"
    assert result["running"] is None
    assert result["inspection_complete"] is False


def test_msty_process_with_hidden_executable_is_running_unverified(monkeypatch):
    class MstyProcess:
        info = {"name": "Msty Studio", "pid": 43}

        def exe(self):
            raise manifests.psutil.AccessDenied(pid=43)

    monkeypatch.setattr(
        manifests.psutil,
        "process_iter",
        lambda attrs: [MstyProcess()],
    )

    result = manifests._process_info()

    assert result["state"] == "running_unverified"
    assert result["running"] is True
    assert result["executable"] is None
    assert result["inspection_complete"] is False
