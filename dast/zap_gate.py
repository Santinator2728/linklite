"""DAST quality gate: decide pass/fail from OWASP ZAP JSON reports (XP-39).

ZAP attacks the running services and writes one JSON report per service. This script
reads them and fails the pipeline when an alert at or above the failing risk level is
found, unless that alert is listed in accepted-alerts.json with a written reason.

Usage: python dast/zap_gate.py REPORT.json [REPORT.json ...]
Exit codes: 0 pass, 1 fail, 2 could not run (missing or unreadable report: fail closed).
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# ZAP risk codes: 0 informational, 1 low, 2 medium, 3 high.
RISK_NAMES = {0: "Informational", 1: "Low", 2: "Medium", 3: "High"}
FAIL_AT_RISK = 2  # Medium and High alerts block the pipeline.
ACCEPTED_FILE = Path(__file__).with_name("accepted-alerts.json")


@dataclass(frozen=True)
class Alert:
    site: str
    plugin_id: str
    name: str
    risk: int
    instances: int


def load_alerts(report_path: Path) -> list[Alert]:
    report = json.loads(report_path.read_text())
    alerts = []
    for site in report.get("site", []):
        for item in site.get("alerts", []):
            alerts.append(
                Alert(
                    site=site.get("@name", "?"),
                    plugin_id=str(item["pluginid"]),
                    name=item["name"],
                    risk=int(item["riskcode"]),
                    instances=len(item.get("instances", [])),
                )
            )
    return alerts


def load_accepted(path: Path | None = None) -> dict[str, str]:
    """Return {plugin_id: reason}. Every accepted alert must say why it is accepted."""
    entries = json.loads((path or ACCEPTED_FILE).read_text())
    accepted = {}
    for entry in entries:
        reason = entry.get("reason", "").strip()
        if not reason:
            raise ValueError(f"accepted alert {entry.get('pluginid')} has no reason")
        accepted[str(entry["pluginid"])] = reason
    return accepted


def blocking(alerts: list[Alert], accepted: dict[str, str]) -> list[Alert]:
    return [a for a in alerts if a.risk >= FAIL_AT_RISK and a.plugin_id not in accepted]


def summary(alerts: list[Alert], accepted: dict[str, str], failed: list[Alert]) -> str:
    lines = [
        "## DAST (OWASP ZAP)",
        "",
        f"**Decision: {'FAIL' if failed else 'PASS'}** "
        f"(fails on {RISK_NAMES[FAIL_AT_RISK]} or higher, unless accepted)",
        "",
    ]
    if not alerts:
        return "\n".join([*lines, "No alerts."])
    lines += ["| Risk | Alert | Plugin | Site | Instances | Status |", "|---|---|---|---|---|---|"]
    for a in sorted(alerts, key=lambda a: (-a.risk, a.site, a.name)):
        if a in failed:
            status = "**blocks**"
        elif a.plugin_id in accepted:
            status = f"accepted: {accepted[a.plugin_id]}"
        else:
            status = "below threshold"
        lines.append(
            f"| {RISK_NAMES.get(a.risk, a.risk)} | {a.name} | {a.plugin_id} | {a.site} "
            f"| {a.instances} | {status} |"
        )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: zap_gate.py REPORT.json [REPORT.json ...]")
        return 2
    try:
        alerts = [alert for path in argv for alert in load_alerts(Path(path))]
        accepted = load_accepted()
    except (OSError, ValueError, KeyError) as exc:
        print(f"DAST gate could not run: {exc}")
        return 2
    failed = blocking(alerts, accepted)
    text = summary(alerts, accepted, failed)
    print(text)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as out:
            out.write(text + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
