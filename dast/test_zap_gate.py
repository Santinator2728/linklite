import json

import pytest

import zap_gate


def report(tmp_path, name, alerts):
    path = tmp_path / name
    path.write_text(
        json.dumps({"site": [{"@name": "http://link:8000", "alerts": alerts}]}), encoding="utf-8"
    )
    return path


def alert(pluginid, risk, name="Some alert"):
    return {"pluginid": str(pluginid), "name": name, "riskcode": str(risk), "instances": [{}]}


@pytest.fixture
def accepted_file(tmp_path, monkeypatch):
    path = tmp_path / "accepted.json"
    path.write_text(json.dumps([{"pluginid": "100", "reason": "known and documented"}]))
    monkeypatch.setattr(zap_gate, "ACCEPTED_FILE", path)
    return path


def test_passes_with_only_low_alerts(tmp_path, accepted_file):
    path = report(tmp_path, "r.json", [alert(1, 1), alert(2, 0)])
    assert zap_gate.main([str(path)]) == 0


def test_fails_on_medium_alert(tmp_path, accepted_file, capsys):
    path = report(tmp_path, "r.json", [alert(10, 2, "Bad header")])

    assert zap_gate.main([str(path)]) == 1
    assert "**blocks**" in capsys.readouterr().out


def test_accepted_alert_does_not_block_and_shows_reason(tmp_path, accepted_file, capsys):
    path = report(tmp_path, "r.json", [alert(100, 3)])

    assert zap_gate.main([str(path)]) == 0
    assert "accepted: known and documented" in capsys.readouterr().out


def test_alerts_from_all_reports_are_combined(tmp_path, accepted_file):
    first = report(tmp_path, "a.json", [alert(1, 1)])
    second = report(tmp_path, "b.json", [alert(11, 3)])
    assert zap_gate.main([str(first), str(second)]) == 1


def test_missing_report_fails_closed(tmp_path, accepted_file):
    assert zap_gate.main([str(tmp_path / "missing.json")]) == 2


def test_no_arguments_fails_closed():
    assert zap_gate.main([]) == 2


def test_accepted_alert_without_reason_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "accepted.json"
    path.write_text(json.dumps([{"pluginid": "100", "reason": " "}]))
    monkeypatch.setattr(zap_gate, "ACCEPTED_FILE", path)
    good = report(tmp_path, "r.json", [])

    assert zap_gate.main([str(good)]) == 2


def test_summary_is_written_for_github(tmp_path, accepted_file, monkeypatch):
    out = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out))
    zap_gate.main([str(report(tmp_path, "r.json", []))])

    assert "No alerts." in out.read_text()


def test_real_accepted_file_is_valid():
    assert isinstance(zap_gate.load_accepted(), dict)
