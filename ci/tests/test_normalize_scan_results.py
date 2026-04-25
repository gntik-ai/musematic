from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ci import normalize_scan_results


def test_sarif_result_blocks_at_scanner_threshold(tmp_path) -> None:
    path = tmp_path / "gosec.sarif"
    path.write_text(
        """
        {
          "runs": [{
            "tool": {"driver": {"rules": [{"id": "G401", "name": "Weak crypto"}]}},
            "results": [{
              "ruleId": "G401",
              "level": "error",
              "message": {"text": "MD5 used"},
              "locations": [{
                "physicalLocation": {"artifactLocation": {"uri": "services/a/main.go"}}
              }]
            }]
          }]
        }
        """,
        encoding="utf-8",
    )

    [payload] = normalize_scan_results.normalize_inputs([path], release_version="1.0.0")

    assert payload["scanner"] == "gosec"
    assert payload["gating_result"] == "blocked"
    assert payload["findings"][0]["vulnerability_id"] == "G401"
    assert payload["findings"][0]["severity"] == "high"


def test_dev_only_metadata_makes_finding_non_blocking(tmp_path) -> None:
    path = tmp_path / "npm-audit.json"
    path.write_text(
        """
        {
          "vulnerabilities": {
            "vite": {"name": "vite", "source": 123, "severity": "high", "title": "CVE"}
          }
        }
        """,
        encoding="utf-8",
    )

    [payload] = normalize_scan_results.normalize_inputs(
        [path],
        release_version="1.0.0",
        metadata={"dev_only_components": ["vite"]},
    )

    assert payload["gating_result"] == "passed"
    assert payload["findings"][0]["dev_only"] is True


def test_active_exception_makes_finding_non_blocking(tmp_path) -> None:
    path = tmp_path / "pip-audit.json"
    path.write_text(
        """
        {
          "dependencies": [{
            "name": "fastapi",
            "vulns": [{"id": "PYSEC-1", "severity": "critical", "fix_versions": ["1.2.3"]}]
          }]
        }
        """,
        encoding="utf-8",
    )
    expires_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    [payload] = normalize_scan_results.normalize_inputs(
        [path],
        release_version="1.0.0",
        exceptions=[
            {
                "scanner": "pip_audit",
                "vulnerability_id": "PYSEC-1",
                "component_pattern": "fastapi",
                "expires_at": expires_at,
            }
        ],
    )

    assert payload["gating_result"] == "passed"
    assert payload["findings"][0]["excepted"] is True


def test_generic_json_shape_is_normalized(tmp_path) -> None:
    path = tmp_path / "bandit.json"
    path.write_text(
        """
        {
          "results": [{
            "test_id": "B101",
            "filename": "apps/control-plane/src/a.py",
            "issue_severity": "HIGH",
            "issue_text": "assert used"
          }]
        }
        """,
        encoding="utf-8",
    )

    [payload] = normalize_scan_results.normalize_inputs([path], release_version="1.0.0")

    assert payload["max_severity"] == "high"
    assert payload["gating_result"] == "blocked"
    assert payload["findings"][0]["component"] == "apps/control-plane/src/a.py"
