from msty_ops import verify


def _doctor(color="green"):
    return {
        "color": color,
        "summary": "ready" if color == "green" else "not ready",
        "baseline": {"state": "current"},
    }


def test_diagnostic_verify_does_not_submit_a_prompt(monkeypatch):
    monkeypatch.setattr(
        verify,
        "local_generate_request",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not generate")),
    )

    report = verify.verify(doctor_report=_doctor())

    assert report["status"] == "pass"
    assert report["synthetic_canary"]["status"] == "not_run"
    assert report["privacy"]["fixed_public_prompt_only"] is True
    assert report["privacy"]["cloud_fallback"] is False


def test_explicit_local_canary_requires_exact_json(monkeypatch):
    monkeypatch.setattr(
        verify,
        "local_generate_request",
        lambda **kwargs: {
            "success": True,
            "content": '{"status":"LOCAL_CANARY_OK","sum":42}',
            "latency_ms": 12.5,
            "service": kwargs["service"],
        },
    )

    report = verify.verify(
        model="synthetic-model",
        service="mlx",
        doctor_report=_doctor(),
    )

    assert report["status"] == "pass"
    assert report["synthetic_canary"]["status"] == "pass"
    assert report["synthetic_canary"]["service"] == "mlx"


def test_unexpected_model_output_fails(monkeypatch):
    monkeypatch.setattr(
        verify,
        "local_generate_request",
        lambda **_kwargs: {"success": True, "content": "LOCAL_CANARY_OK"},
    )

    report = verify.verify(
        model="synthetic-model",
        service="local_ai",
        doctor_report=_doctor(),
    )

    assert report["status"] == "fail"
    assert report["synthetic_canary"]["status"] == "fail"


def test_model_and_service_are_required_together():
    try:
        verify.verify(model="synthetic-model", doctor_report=_doctor())
    except ValueError as exc:
        assert "together" in str(exc)
    else:
        raise AssertionError("missing service should fail closed")
