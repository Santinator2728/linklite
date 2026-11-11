"""AI code review gate (Jira XP-36).

Sends the diff of a pull request to Claude with the versioned prompt and settings in this folder,
gets back a structured list of findings, and fails when a finding reaches the configured severity.
The pass/fail decision is computed here from the findings, not taken from free text, so it only
depends on the findings and the threshold.

Usage: python review.py --base origin/main (the result is written to ai-review.json)
Exit codes: 0 pass, 1 fail, 2 the gate could not run (counts as a failed check).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess  # noqa: S404 - runs git with fixed arguments, no shell
import sys
from pathlib import Path
from typing import Any

import anthropic
import yaml

HERE = Path(__file__).resolve().parent
SEVERITIES = ["low", "medium", "high", "critical"]
REQUIRED_CONFIG = ("model", "effort", "max_tokens", "fail_on", "max_diff_chars")
OUTPUT_FILE = "ai-review.json"
# A branch name such as origin/main; never something git could read as an option.
BASE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")

FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": SEVERITIES},
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "title": {"type": "string"},
                    "explanation": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["severity", "file", "line", "title", "explanation", "suggestion"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "findings"],
    "additionalProperties": False,
}


class GateError(Exception):
    """The review could not produce a trustworthy result."""


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text())
    missing = [key for key in REQUIRED_CONFIG if key not in config]
    if missing:
        raise GateError(f"config.yaml is missing: {', '.join(missing)}")
    if config["fail_on"] not in SEVERITIES:
        raise GateError(f"fail_on must be one of {SEVERITIES}")
    config.setdefault("exclude", [])
    return config


def fingerprint(*texts: str) -> str:
    """Short hash of the gate's configuration, to prove two runs used the same settings."""
    return hashlib.sha256("\n".join(texts).encode()).hexdigest()[:12]


def checked_base(base: str) -> str:
    if not BASE_REF.fullmatch(base) or ".." in base:
        raise GateError(f"invalid base branch: {base!r}")
    return base


def git(*args: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed git arguments
        ["git", *args],  # noqa: S607 - git from PATH, as in any CI runner
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def filter_diff(diff: str, exclude: list[str]) -> str:
    """Drop the sections of a unified diff whose file matches an exclude pattern."""
    kept: list[str] = []
    keep = True
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[-1].strip()
            keep = not any(fnmatch.fnmatch(path, pattern) for pattern in exclude)
        if keep:
            kept.append(line)
    return "".join(kept)


def decide(findings: list[dict[str, Any]], fail_on: str) -> str:
    threshold = SEVERITIES.index(fail_on)
    blocking = [f for f in findings if SEVERITIES.index(f["severity"]) >= threshold]
    return "fail" if blocking else "pass"


def ask_claude(client: Any, config: dict[str, Any], prompt: str, diff: str) -> dict[str, Any]:
    response = client.messages.create(
        model=config["model"],
        max_tokens=config["max_tokens"],
        system=prompt,
        output_config={
            "effort": config["effort"],
            "format": {"type": "json_schema", "schema": FINDINGS_SCHEMA},
        },
        messages=[
            {
                "role": "user",
                "content": f"Review this pull request diff.\n\n<diff>\n{diff}\n</diff>",
            }
        ],
    )
    if response.stop_reason != "end_turn":
        raise GateError(f"the model stopped early (stop_reason={response.stop_reason})")
    text = next(block.text for block in response.content if block.type == "text")
    review = json.loads(text)
    review["model"] = response.model
    review["request_id"] = getattr(response, "_request_id", None)
    review["usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return review


def run(client: Any, config: dict[str, Any], prompt: str, diff: str) -> dict[str, Any]:
    if not diff.strip():
        review: dict[str, Any] = {"summary": "No reviewable changes.", "findings": []}
    elif len(diff) > config["max_diff_chars"]:
        raise GateError(
            f"diff has {len(diff)} characters, above max_diff_chars={config['max_diff_chars']}; "
            "split the pull request"
        )
    else:
        review = ask_claude(client, config, prompt, diff)
    review["decision"] = decide(review["findings"], config["fail_on"])
    return review


def to_markdown(result: dict[str, Any]) -> str:
    icon = "✅" if result["decision"] == "pass" else "❌"
    lines = [
        f"## {icon} AI code review: {result['decision'].upper()}",
        "",
        result["summary"],
        "",
        f"Model `{result.get('model', '-')}` · fails on `{result['fail_on']}` or higher · "
        f"config `{result['config_fingerprint']}` · commit `{result['commit'][:7]}`",
        "",
    ]
    if result["findings"]:
        lines += ["| Severity | Where | Finding |", "|---|---|---|"]
        for f in result["findings"]:
            detail = f"**{f['title']}**: {f['explanation']} _Fix:_ {f['suggestion']}"
            lines.append(f"| {f['severity']} | `{f['file']}:{f['line']}` | {detail} |")
    else:
        lines.append("No findings.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None, client: Any = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="branch the PR will merge into")
    args = parser.parse_args(argv)

    config_text = (HERE / "config.yaml").read_text()
    prompt = (HERE / "prompt.md").read_text()
    try:
        config = load_config(HERE / "config.yaml")
        base = checked_base(args.base)
        diff = filter_diff(git("diff", "--end-of-options", f"{base}...HEAD"), config["exclude"])
        result = run(client or anthropic.Anthropic(), config, prompt, diff)
    except (GateError, anthropic.AnthropicError, subprocess.CalledProcessError) as error:
        print(f"::error::AI code review could not run: {error}")
        return 2

    result["fail_on"] = config["fail_on"]
    result["config_fingerprint"] = fingerprint(config_text, prompt)
    result["commit"] = git("rev-parse", "HEAD").strip()
    Path(OUTPUT_FILE).write_text(json.dumps(result, indent=2) + "\n")

    report = to_markdown(result)
    print(report)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as summary:
            summary.write(report)
    return 0 if result["decision"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
