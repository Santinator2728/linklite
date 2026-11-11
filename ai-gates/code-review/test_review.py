import json
from types import SimpleNamespace

import pytest

import review

CONFIG = {
    "model": "claude-opus-5-5",
    "effort": "high",
    "max_tokens": 1000,
    "fail_on": "high",
    "max_diff_chars": 1000,
    "exclude": ["*.lock"],
}

DIFF = """diff --git a/services/link/app.py b/services/link/app.py
+print("changed")
diff --git a/services/link/requirements.lock b/services/link/requirements.lock
+fastapi==1.0 --hash=sha256:abc
"""


class FakeClient:
    """Stands in for anthropic.Anthropic(): returns a canned response, records the request."""

    def __init__(self, findings, stop_reason="end_turn"):
        self.request = None
        body = json.dumps({"summary": "Looks fine.", "findings": findings})
        self.response = SimpleNamespace(
            stop_reason=stop_reason,
            model="claude-opus-5-5",
            content=[SimpleNamespace(type="text", text=body)],
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.request = kwargs
        return self.response


def finding(severity):
    return {
        "severity": severity,
        "file": "services/link/app.py",
        "line": 1,
        "title": "Problem",
        "explanation": "Why it matters.",
        "suggestion": "How to fix it.",
    }


def test_filter_diff_drops_excluded_files():
    filtered = review.filter_diff(DIFF, ["*.lock"])
    assert "app.py" in filtered
    assert "requirements.lock" not in filtered


@pytest.mark.parametrize(
    ("severities", "expected"),
    [([], "pass"), (["low", "medium"], "pass"), (["low", "high"], "fail"), (["critical"], "fail")],
)
def test_decide_uses_the_threshold(severities, expected):
    assert review.decide([finding(s) for s in severities], "high") == expected


def test_run_sends_pinned_settings_and_passes_without_findings():
    client = FakeClient(findings=[])
    result = review.run(client, CONFIG, "prompt", DIFF)

    assert result["decision"] == "pass"
    assert client.request["model"] == "claude-opus-5-5"
    assert client.request["output_config"]["effort"] == "high"
    assert client.request["output_config"]["format"]["schema"] == review.FINDINGS_SCHEMA
    assert "<diff>" in client.request["messages"][0]["content"]


def test_run_fails_on_a_high_finding():
    result = review.run(FakeClient(findings=[finding("high")]), CONFIG, "prompt", DIFF)
    assert result["decision"] == "fail"


def test_run_skips_the_api_for_an_empty_diff():
    client = FakeClient(findings=[])
    result = review.run(client, CONFIG, "prompt", "")
    assert result["decision"] == "pass"
    assert client.request is None


def test_run_refuses_a_diff_that_is_too_large():
    with pytest.raises(review.GateError, match="max_diff_chars"):
        review.run(FakeClient(findings=[]), CONFIG, "prompt", "x" * 2000)


def test_run_rejects_an_incomplete_answer():
    with pytest.raises(review.GateError, match="max_tokens"):
        review.run(FakeClient(findings=[], stop_reason="max_tokens"), CONFIG, "prompt", DIFF)


def test_load_config_checks_required_keys(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("model: claude-opus-5-5\n")
    with pytest.raises(review.GateError, match="missing"):
        review.load_config(path)

    path.write_text("model: m\neffort: high\nmax_tokens: 1\nfail_on: urgent\nmax_diff_chars: 1\n")
    with pytest.raises(review.GateError, match="fail_on"):
        review.load_config(path)


def test_repo_config_is_valid():
    config = review.load_config(review.HERE / "config.yaml")
    assert config["model"] == "claude-opus-5-5"


def fake_git(*args):
    return DIFF if args[0] == "diff" else "0123456789abcdef\n"


def test_main_writes_result_and_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "git", fake_git)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.chdir(tmp_path)

    code = review.main([], client=FakeClient(findings=[finding("high")]))

    assert code == 1
    result = json.loads((tmp_path / review.OUTPUT_FILE).read_text())
    assert result["decision"] == "fail"
    assert result["commit"] == "0123456789abcdef"
    assert len(result["config_fingerprint"]) == 12
    assert "AI code review: FAIL" in summary.read_text()


def test_main_returns_2_when_the_gate_cannot_run(monkeypatch, capsys):
    monkeypatch.setattr(review, "git", fake_git)
    client = FakeClient(findings=[], stop_reason="refusal")

    assert review.main([], client=client) == 2
    assert "could not run" in capsys.readouterr().out


@pytest.mark.parametrize("base", ["--output=/tmp/x", "origin/main;rm -rf /", "a..b", "-p"])
def test_main_rejects_a_base_that_is_not_a_branch_name(base, monkeypatch, capsys):
    monkeypatch.setattr(review, "git", fake_git)

    assert review.main([f"--base={base}"], client=FakeClient(findings=[])) == 2
    assert "invalid base branch" in capsys.readouterr().out


def test_git_runs_in_this_repository():
    assert len(review.git("rev-parse", "HEAD").strip()) == 40
