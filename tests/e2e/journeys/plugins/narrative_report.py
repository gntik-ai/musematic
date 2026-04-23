from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

import pytest

from journeys.helpers.narrative import JourneyStepRecord, collect_journey_step_records, reset_journey_step_records


@dataclass(slots=True)
class JourneyCaseReport:
    nodeid: str
    outcome: str = "passed"
    duration_s: float = 0.0
    records: list[JourneyStepRecord] = field(default_factory=list)


def pytest_configure(config) -> None:
    reports_dir = Path(str(config.rootpath)) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    config._journey_case_reports = {}


def pytest_runtest_setup(item) -> None:
    del item
    reset_journey_step_records()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if call.when != "call":
        return

    case_reports: dict[str, JourneyCaseReport] = getattr(item.config, "_journey_case_reports", {})
    case_reports[report.nodeid] = JourneyCaseReport(
        nodeid=report.nodeid,
        outcome=report.outcome,
        duration_s=report.duration,
        records=collect_journey_step_records(),
    )


def pytest_sessionfinish(session, exitstatus: int) -> None:
    reports_dir = Path(str(session.config.rootpath)) / "reports"
    case_reports: dict[str, JourneyCaseReport] = getattr(session.config, "_journey_case_reports", {})
    _write_junit_report(reports_dir / "journeys-junit.xml", case_reports)
    _write_html_report(reports_dir / "journeys-report.html", case_reports, exitstatus)


def _write_junit_report(path: Path, case_reports: dict[str, JourneyCaseReport]) -> None:
    suites = Element("testsuites")
    by_journey: dict[str, list[JourneyCaseReport]] = defaultdict(list)
    for case in case_reports.values():
        journey_id = case.records[0].journey_id if case.records else "unknown"
        by_journey[journey_id].append(case)

    for journey_id in sorted(by_journey):
        cases = by_journey[journey_id]
        suite = SubElement(
            suites,
            "testsuite",
            name=journey_id,
            tests=str(sum(max(1, len(case.records)) for case in cases)),
            failures=str(
                sum(
                    1
                    for case in cases
                    for record in (case.records or [None])
                    if (record is None and case.outcome != "passed")
                    or (record is not None and record.status != "passed")
                )
            ),
        )
        for case in cases:
            records = case.records or [
                JourneyStepRecord(
                    journey_id=journey_id,
                    test_nodeid=case.nodeid,
                    step_index=1,
                    description=case.nodeid,
                    started_at="",
                    duration_ms=int(case.duration_s * 1000),
                    status=case.outcome,
                    error=None,
                )
            ]
            for record in records:
                testcase = SubElement(
                    suite,
                    "testcase",
                    classname=record.journey_id,
                    name=f"{record.test_nodeid} :: step {record.step_index} :: {record.description}",
                    time=f"{record.duration_ms / 1000:.3f}",
                )
                if record.status != "passed":
                    failure = SubElement(testcase, "failure", message=record.error or record.status)
                    failure.text = record.error or "journey step failed"
    ElementTree(suites).write(path, encoding="utf-8", xml_declaration=True)


def _write_html_report(path: Path, case_reports: dict[str, JourneyCaseReport], exitstatus: int) -> None:
    rows: list[str] = []
    for case in sorted(case_reports.values(), key=lambda item: item.nodeid):
        records = case.records
        if not records:
            rows.append(
                "<section class='journey'>"
                f"<h2>{escape(case.nodeid)}</h2>"
                "<p class='empty'>No journey steps were captured.</p>"
                "</section>"
            )
            continue

        list_items: list[str] = []
        for record in records:
            css_class = "failed" if record.status != "passed" else "passed"
            suffix = f" ({record.duration_ms} ms)"
            details = f" - {escape(record.error)}" if record.error else ""
            list_items.append(
                f"<li class='{css_class}'>"
                f"<span class='step-index'>{record.step_index}.</span> "
                f"<span class='step-text'>{escape(record.description)}</span>"
                f"<span class='step-duration'>{suffix}</span>"
                f"{details}</li>"
            )
            if record.status != "passed":
                break
        rows.append(
            "<section class='journey'>"
            f"<h2>{escape(records[0].journey_id.upper())} - {escape(case.nodeid)}</h2>"
            f"<p class='summary'>Outcome: {escape(case.outcome)}; steps captured: {len(records)}</p>"
            f"<ol>{''.join(list_items)}</ol>"
            "</section>"
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Journey Narrative Report</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem auto; max-width: 1100px; line-height: 1.5; }}
    h1 {{ margin-bottom: 0.25rem; }}
    .summary {{ color: #555; }}
    .journey {{ border: 1px solid #d7d7d7; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0; }}
    ol {{ padding-left: 1.5rem; }}
    li {{ margin: 0.35rem 0; }}
    li.failed {{ color: #9f1239; font-weight: 600; }}
    li.passed {{ color: #166534; }}
    .step-index {{ display: inline-block; min-width: 2rem; }}
    .step-duration {{ color: #666; margin-left: 0.4rem; font-size: 0.95em; }}
    .empty {{ color: #666; font-style: italic; }}
  </style>
</head>
<body>
  <h1>Journey Narrative Report</h1>
  <p class="summary">pytest exit status: {exitstatus}; journeys captured: {len(case_reports)}</p>
  {''.join(rows) if rows else "<p class='empty'>No journey cases executed.</p>"}
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
