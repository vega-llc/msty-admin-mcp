import json
import stat

import pytest

from msty_ops import doctor, support


def _status(*, installed=True, support="tested", count=2, reachable=True, valid=True):
    return {
        "studio": {
            "installed": installed,
            "version": "2.9.6" if installed else None,
            "version_support": support,
        },
        "process": {"state": "running", "running": True},
        "local_services": {
            "mlx": {
                "reachable": reachable,
                "schema_valid": valid,
                "advertised_model_count": count,
                "error_kind": None,
            },
            "local_ai": {
                "reachable": False,
                "schema_valid": False,
                "advertised_model_count": None,
                "error_kind": "connection_refused",
            },
            "llamacpp": {
                "reachable": False,
                "schema_valid": False,
                "advertised_model_count": None,
                "error_kind": "connection_refused",
            },
        },
    }


def _compatibility(status="pass"):
    return {"overall_status": status}


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (_status(), "green"),
        (_status(support="not_tested"), "yellow"),
        (_status(count=0), "yellow"),
        (_status(reachable=False, valid=False), "red"),
        (_status(installed=False), "red"),
    ],
)
def test_doctor_traffic_light_states(status, expected):
    report = doctor.assess(status, _compatibility(), baseline_path=None)

    assert report["color"] == expected
    assert report["privacy"] == {
        "reads_chats": False,
        "reads_provider_credentials": False,
        "reads_msty_database": False,
        "submits_prompts": False,
    }


def test_baseline_detects_operational_drift(tmp_path):
    path = tmp_path / "state" / "baseline.json"
    good = _status()
    doctor.record_baseline(path, good)

    current = doctor.assess(good, _compatibility(), baseline_path=path)
    changed = doctor.assess(_status(count=3), _compatibility(), baseline_path=path)

    assert current["color"] == "green"
    assert current["baseline"]["state"] == "current"
    assert changed["color"] == "yellow"
    assert changed["baseline"]["state"] == "changed"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_baseline_refuses_symlink(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "baseline.json"
    link.symlink_to(target)

    assert doctor.load_baseline(link) == ("invalid", None)
    with pytest.raises(ValueError, match="symlink"):
        doctor.record_baseline(link, _status())


def test_support_bundle_excludes_sensitive_and_machine_specific_values(tmp_path):
    status = _status()
    mac_home = "/" + "Users/example/"
    status["studio"]["path"] = mac_home + "Applications/MstyStudio.app"
    status["process"]["pid"] = 1234
    status["process"]["executable"] = mac_home + "private/MstyStudio"
    status["local_services"]["mlx"]["error"] = "token sk-example-secret"
    status["local_services"]["mlx"]["model_id"] = "private-model-name"

    payload = support.build_support_bundle(status, _compatibility())
    encoded = json.dumps(payload)

    assert mac_home not in encoded
    assert "sk-example-secret" not in encoded
    assert "private-model-name" not in encoded
    assert '"pid"' not in encoded
    assert '"path"' not in encoded

    output = tmp_path / "support.json"
    support.write_support_bundle(output, payload)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_support_bundle_refuses_overwrite_and_symlink(tmp_path):
    payload = support.build_support_bundle(_status(), _compatibility())
    output = tmp_path / "support.json"
    support.write_support_bundle(output, payload)

    with pytest.raises(FileExistsError):
        support.write_support_bundle(output, payload)

    link = tmp_path / "linked.json"
    link.symlink_to(output)
    with pytest.raises(ValueError, match="symlink"):
        support.write_support_bundle(link, payload, overwrite=True)
