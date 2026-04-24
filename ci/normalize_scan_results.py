from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
SCANNER_GATE_SEVERITY: dict[str, str] = {
    "trivy": "critical",
    "gitleaks": "low",
    "pip_audit": "critical",
    "npm_audit": "high",
    "govulncheck": "high",
    "bandit": "high",
    "gosec": "high",
    "grype": "critical",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize security scanner outputs.")
    parser.add_argument("paths", nargs="+", type=Path, help="Scanner output files or directories")
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--metadata", type=Path, default=Path("scan-metadata.json"))
    parser.add_argument("--exceptions-file", type=Path, default=None)
    parser.add_argument("--platform-url", default=os.environ.get("PLATFORM_API_URL"))
    parser.add_argument("--token-env", default="PLATFORM_JWT")
    parser.add_argument("--oidc-exchange-url", default=os.environ.get("PLATFORM_OIDC_EXCHANGE_URL"))
    parser.add_argument(
        "--oidc-audience", default=os.environ.get("PLATFORM_OIDC_AUDIENCE", "musematic")
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-post", action="store_true")
    return parser


def normalize_inputs(
    paths: list[Path],
    *,
    release_version: str,
    metadata: dict[str, Any] | None = None,
    exceptions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    metadata = metadata or {}
    exceptions = exceptions or []
    payloads: list[dict[str, Any]] = []
    for path in _expand_paths(paths):
        scanner = _scanner_from_path(path)
        findings = [
            _apply_context(scanner, item, metadata, exceptions)
            for item in _extract_findings(scanner, _load_json(path))
        ]
        payloads.append(
            {
                "scanner": scanner,
                "release_version": release_version,
                "findings": findings,
                "max_severity": _max_severity(findings),
                "scanned_at": datetime.now(UTC).isoformat(),
                "gating_result": _gating_result(scanner, findings),
            }
        )
    return payloads


def post_scan_result(platform_url: str, token: str, payload: dict[str, Any]) -> None:
    base = platform_url.rstrip("/")
    release_version = urllib.parse.quote(str(payload["release_version"]), safe="")
    url = f"{base}/api/v1/security/scans/{release_version}/results"
    body = json.dumps(
        {
            "scanner": payload["scanner"],
            "findings": payload["findings"],
            "max_severity": payload["max_severity"],
            "gating_result": payload["gating_result"],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status >= 400:
            raise RuntimeError(f"scan upload failed: HTTP {response.status}")


def fetch_active_exceptions(platform_url: str, token: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"{platform_url.rstrip('/')}/api/v1/security/vulnerability-exceptions",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return list(json.loads(response.read().decode("utf-8")))


def resolve_platform_token(args: argparse.Namespace) -> str | None:
    token = os.environ.get(args.token_env) or os.environ.get("PLATFORM_API_TOKEN")
    if token:
        return token
    if not args.oidc_exchange_url:
        return None
    oidc = _github_oidc_token(args.oidc_audience)
    body = json.dumps({"token": oidc}).encode("utf-8")
    request = urllib.request.Request(
        args.oidc_exchange_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload.get("access_token") or payload.get("token") or "")


def _github_oidc_token(audience: str) -> str:
    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    separator = "&" if "?" in request_url else "?"
    request = urllib.request.Request(
        f"{request_url}{separator}audience={urllib.parse.quote(audience)}",
        headers={"Authorization": f"Bearer {request_token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload["value"])


def _expand_paths(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                sorted(item for item in path.iterdir() if item.suffix in {".json", ".sarif"})
            )
        else:
            files.append(path)
    return files


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    return _load_json(path)


def _scanner_from_path(path: Path) -> str:
    name = path.stem.lower().replace("-", "_")
    for suffix in ("_results", "_report", "_sarif"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    for scanner in SCANNER_GATE_SEVERITY:
        if name == scanner or name.startswith(f"{scanner}_"):
            return scanner
    aliases = {"pip_audit": "pip_audit", "npm": "npm_audit", "npm_audit": "npm_audit"}
    return aliases.get(name, name)


def _extract_findings(scanner: str, document: Any) -> list[dict[str, Any]]:
    if isinstance(document, dict) and "runs" in document:
        return _extract_sarif(document)
    if scanner == "pip_audit":
        return _extract_pip_audit(document)
    if scanner == "npm_audit":
        return _extract_npm_audit(document)
    if scanner == "bandit" and isinstance(document, dict):
        return [_normalize_raw(scanner, item) for item in document.get("results", [])]
    if scanner == "gosec" and isinstance(document, dict):
        return [_normalize_raw(scanner, item) for item in document.get("Issues", [])]
    if isinstance(document, dict) and "findings" in document:
        return [_normalize_raw(scanner, item) for item in document["findings"]]
    if isinstance(document, list):
        return [_normalize_raw(scanner, item) for item in document]
    if isinstance(document, dict) and "Results" in document:
        return _extract_trivy(document)
    if isinstance(document, dict) and "vulns" in document:
        return [_normalize_raw(scanner, item) for item in document["vulns"]]
    return []


def _extract_sarif(document: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for run in document.get("runs", []):
        rules = {
            rule.get("id"): rule
            for rule in run.get("tool", {}).get("driver", {}).get("rules", [])
            if isinstance(rule, dict)
        }
        for result in run.get("results", []):
            rule_id = str(result.get("ruleId") or result.get("rule_id") or "unknown")
            rule = rules.get(rule_id, {})
            component = _sarif_component(result)
            findings.append(
                {
                    "vulnerability_id": rule_id,
                    "component": component,
                    "severity": _severity(
                        result.get("level")
                        or result.get("properties", {}).get("security-severity")
                        or rule.get("properties", {}).get("security-severity")
                    ),
                    "title": _message(result) or str(rule.get("name") or rule_id),
                    "fixed_version": None,
                    "dev_only": False,
                    "excepted": False,
                }
            )
    return findings


def _extract_pip_audit(document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    findings: list[dict[str, Any]] = []
    for dep in document.get("dependencies", []):
        component = str(dep.get("name") or dep.get("package") or "")
        for vuln in dep.get("vulns", []):
            findings.append(
                {
                    "vulnerability_id": str(vuln.get("id") or vuln.get("aliases", ["unknown"])[0]),
                    "component": component,
                    "severity": _severity(vuln.get("severity") or "critical"),
                    "title": str(vuln.get("description") or vuln.get("id") or ""),
                    "fixed_version": _first(vuln.get("fix_versions")),
                    "dev_only": False,
                    "excepted": False,
                }
            )
    return findings


def _extract_npm_audit(document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    findings: list[dict[str, Any]] = []
    for package_name, vuln in document.get("vulnerabilities", {}).items():
        findings.append(
            {
                "vulnerability_id": str(vuln.get("source") or package_name),
                "component": str(vuln.get("name") or package_name),
                "severity": _severity(vuln.get("severity")),
                "title": str(vuln.get("title") or vuln.get("name") or package_name),
                "fixed_version": None,
                "dev_only": bool(vuln.get("dev")),
                "excepted": False,
            }
        )
    return findings


def _extract_trivy(document: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for result in document.get("Results", []):
        component_target = str(result.get("Target") or "")
        for item in result.get("Vulnerabilities", []):
            raw = dict(item)
            raw.setdefault("component", raw.get("PkgName") or component_target)
            findings.append(_normalize_raw("trivy", raw))
    return findings


def _normalize_raw(scanner: str, item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {"title": str(item)}
    vulnerability_id = (
        item.get("vulnerability_id")
        or item.get("VulnerabilityID")
        or item.get("id")
        or item.get("rule_id")
        or item.get("RuleID")
        or item.get("test_id")
        or item.get("cve")
        or "unknown"
    )
    component = (
        item.get("component")
        or item.get("package")
        or item.get("PkgName")
        or item.get("filename")
        or item.get("File")
        or item.get("file")
        or ""
    )
    title = (
        item.get("title")
        or item.get("Title")
        or item.get("Description")
        or item.get("issue_text")
        or item.get("details")
        or vulnerability_id
    )
    severity_value = (
        item.get("severity")
        or item.get("Severity")
        or item.get("issue_severity")
        or item.get("level")
        or ("low" if scanner == "gitleaks" else "info")
    )
    return {
        "vulnerability_id": str(vulnerability_id),
        "component": str(component),
        "severity": _severity(severity_value),
        "title": str(title),
        "fixed_version": _first(item.get("fixed_version") or item.get("FixedVersion")),
        "dev_only": bool(item.get("dev_only") or item.get("dev")),
        "excepted": bool(item.get("excepted")),
    }


def _apply_context(
    scanner: str,
    finding: dict[str, Any],
    metadata: dict[str, Any],
    exceptions: list[dict[str, Any]],
) -> dict[str, Any]:
    component = str(finding.get("component") or "")
    finding["dev_only"] = bool(finding.get("dev_only")) or _matches_dev_only(component, metadata)
    finding["excepted"] = bool(finding.get("excepted")) or _matches_exception(
        scanner, finding, exceptions
    )
    return finding


def _matches_dev_only(component: str, metadata: dict[str, Any]) -> bool:
    patterns = (
        metadata.get("dev_only_components")
        or metadata.get("devOnlyComponents")
        or metadata.get("dev_only")
        or []
    )
    return any(fnmatch(component, str(pattern)) for pattern in patterns)


def _matches_exception(
    scanner: str,
    finding: dict[str, Any],
    exceptions: list[dict[str, Any]],
) -> bool:
    now = datetime.now(UTC)
    vulnerability_id = str(finding.get("vulnerability_id") or "")
    component = str(finding.get("component") or "")
    for exception in exceptions:
        if exception.get("scanner") not in {scanner, "*"}:
            continue
        if str(exception.get("vulnerability_id")) != vulnerability_id:
            continue
        expires_at = str(exception.get("expires_at") or "")
        if expires_at:
            parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            if parsed < now:
                continue
        pattern = str(exception.get("component_pattern") or "*")
        if fnmatch(component, pattern):
            return True
    return False


def _gating_result(scanner: str, findings: list[dict[str, Any]]) -> str:
    threshold = SCANNER_GATE_SEVERITY.get(scanner, "high")
    for finding in findings:
        if finding.get("dev_only") or finding.get("excepted"):
            continue
        if SEVERITY_RANK[finding["severity"]] >= SEVERITY_RANK[threshold]:
            return "blocked"
    return "passed"


def _max_severity(findings: list[dict[str, Any]]) -> str | None:
    severities = [finding["severity"] for finding in findings]
    return max(severities, key=lambda value: SEVERITY_RANK[value]) if severities else None


def _severity(value: Any) -> str:
    text = str(value or "info").lower()
    if text in SEVERITY_RANK:
        return text
    if text in {"error", "fail"}:
        return "high"
    if text in {"warning", "warn"}:
        return "medium"
    if text in {"note", "notice"}:
        return "low"
    try:
        score = float(text)
    except ValueError:
        return "info"
    if score >= 9:
        return "critical"
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    if score > 0:
        return "low"
    return "info"


def _sarif_component(result: dict[str, Any]) -> str:
    locations = result.get("locations") or []
    if not locations:
        return ""
    location = locations[0].get("physicalLocation", {})
    return str(location.get("artifactLocation", {}).get("uri") or "")


def _message(result: dict[str, Any]) -> str:
    message = result.get("message") or {}
    return str(message.get("text") or message.get("markdown") or "")


def _first(value: Any) -> str | None:
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = resolve_platform_token(args)
    exceptions = list(_load_optional_json(args.exceptions_file) or [])
    if args.platform_url and token and not exceptions:
        try:
            exceptions = fetch_active_exceptions(args.platform_url, token)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            print(
                f"warning: could not fetch vulnerability exceptions: {exc}",
                file=sys.stderr,
            )
    payloads = normalize_inputs(
        args.paths,
        release_version=args.release_version,
        metadata=_load_optional_json(args.metadata) or {},
        exceptions=exceptions,
    )
    if args.output is not None:
        args.output.write_text(json.dumps(payloads, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payloads, sort_keys=True, separators=(",", ":")))
    if args.platform_url and token and not args.no_post:
        for payload in payloads:
            post_scan_result(args.platform_url, token, payload)
    if any(payload["gating_result"] == "blocked" for payload in payloads):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
