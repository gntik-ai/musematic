from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "check-readme-parity.py"
SPEC = importlib.util.spec_from_file_location("check_readme_parity", MODULE_PATH)
assert SPEC is not None
parity = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(parity)
REAL_VALIDATE_PANDOC = parity.validate_pandoc


LANGUAGE_BAR = (
    "> **Read this in other languages**: [English](./README.md) · "
    "[Español](./README.es.md) · [Italiano](./README.it.md) · "
    "[Deutsch](./README.de.md) · [Français](./README.fr.md) · [简体中文](./README.zh.md)"
)


def readme(title: str = "Musematic", *, extra: str = "") -> str:
    return f"""# {title}

[![Build](https://example.com/build.svg)](https://example.com/build)
[![License](https://example.com/license.svg)](./LICENSE)
[![Kubernetes](https://example.com/k8s.svg)](https://example.com/k8s)
[![Version](https://example.com/version.svg)](https://example.com/version)

{LANGUAGE_BAR}

Intro paragraph with [one link](./docs/).

## What is Musematic?

Text.

### Audience

Text.

## Core capabilities

Text.

## Quick start

```bash
make dev-up
```

{extra}
"""


def write_all_readmes(root: Path, content: str | None = None) -> None:
    (root / "docs").mkdir()
    body = content or readme()
    for locale in parity.LOCALES:
        path = parity.readme_path(root, locale)
        path.write_text(body, encoding="utf-8")


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parity, "validate_pandoc", lambda _file: True)
    monkeypatch.setattr(parity, "has_exempt_label", lambda _pr_number: False)
    monkeypatch.setattr(parity, "check_grace_window", lambda _issue_number: True)
    monkeypatch.setattr(parity, "find_open_drift_issue", lambda: None)


def test_extract_headings_h1_h2_h3_ignores_h4_and_fences() -> None:
    content = """# H1
## H2
### H3
#### H4
```markdown
## fenced
```
"""
    assert parity.extract_headings(content) == [(1, "H1"), (2, "H2"), (3, "H3")]


def test_count_badges_distinguishes_links() -> None:
    content = "[![badge](badge.svg)](https://example.com) [link](target.md) ![second](two.svg)"
    assert parity.count_badges(content) == 2
    assert parity.count_links(content) == 1


def test_extract_language_bar_returns_none_when_missing() -> None:
    assert parity.extract_language_bar("# README") is None
    assert parity.extract_language_bar(readme()) == LANGUAGE_BAR


def test_validate_pandoc_returns_false_on_unclosed_fence(tmp_path: Path) -> None:
    file = tmp_path / "README.md"
    file.write_text("# Title\n\n```bash\nmake dev-up\n", encoding="utf-8")
    assert REAL_VALIDATE_PANDOC(file) is False


def test_parity_identical_files_exit_zero(tmp_path: Path) -> None:
    write_all_readmes(tmp_path)
    assert parity.main(["--repo-root", str(tmp_path)]) == 0


def test_translated_heading_text_with_same_structure_exits_zero(tmp_path: Path) -> None:
    write_all_readmes(tmp_path)
    (tmp_path / "README.es.md").write_text(
        readme(title="Musematic", extra=""),
        encoding="utf-8",
    )
    assert parity.main(["--repo-root", str(tmp_path)]) == 0


def test_missing_heading_in_variant_exits_warning(tmp_path: Path) -> None:
    write_all_readmes(tmp_path)
    (tmp_path / "README.es.md").write_text(readme().replace("### Audience\n\nText.\n\n", ""), encoding="utf-8")
    assert parity.main(["--repo-root", str(tmp_path)]) == 1


def test_drift_with_exempt_label_remains_warning(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    write_all_readmes(tmp_path)
    (tmp_path / "README.es.md").write_text(readme().replace("### Audience\n\nText.\n\n", ""), encoding="utf-8")
    monkeypatch.setattr(parity, "has_exempt_label", lambda _pr_number: True)
    monkeypatch.setattr(parity, "check_grace_window", lambda _issue_number: False)
    assert parity.main(["--repo-root", str(tmp_path), "--pr-number", "42", "--drift-issue", "9"]) == 1


def test_drift_after_grace_window_exits_hard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    write_all_readmes(tmp_path)
    (tmp_path / "README.es.md").write_text(readme().replace("### Audience\n\nText.\n\n", ""), encoding="utf-8")
    monkeypatch.setattr(parity, "check_grace_window", lambda _issue_number: False)
    assert parity.main(["--repo-root", str(tmp_path), "--drift-issue", "9"]) == 2


def test_language_switcher_mismatch_exits_warning(tmp_path: Path) -> None:
    write_all_readmes(tmp_path)
    bad = readme().replace("English](./README.md)", "English](README.md)")
    (tmp_path / "README.fr.md").write_text(bad, encoding="utf-8")
    assert parity.main(["--repo-root", str(tmp_path)]) == 1


def test_pandoc_failure_exits_hard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    write_all_readmes(tmp_path)
    monkeypatch.setattr(parity, "validate_pandoc", lambda file: file.name != "README.it.md")
    assert parity.main(["--repo-root", str(tmp_path)]) == 2


def test_missing_locale_file_exits_hard(tmp_path: Path) -> None:
    write_all_readmes(tmp_path)
    (tmp_path / "README.zh.md").unlink()
    assert parity.main(["--repo-root", str(tmp_path)]) == 2


def test_typo_fix_without_structure_change_exits_zero(tmp_path: Path) -> None:
    write_all_readmes(tmp_path)
    fixed = readme().replace("Intro paragraph", "Intro paragraph corrected")
    (tmp_path / "README.es.md").write_text(fixed, encoding="utf-8")
    assert parity.main(["--repo-root", str(tmp_path)]) == 0


def test_find_missing_local_links_warns_without_failure(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[missing](./missing.md)", encoding="utf-8")
    warnings = parity.find_missing_local_links(tmp_path, tmp_path / "README.md", "[missing](./missing.md)")
    assert warnings == ["README.md: local link target missing: ./missing.md"]


def test_badge_count_mismatch_exits_warning(tmp_path: Path) -> None:
    write_all_readmes(tmp_path)
    (tmp_path / "README.de.md").write_text(readme().replace("[![Version]", "[Version]"), encoding="utf-8")
    assert parity.main(["--repo-root", str(tmp_path)]) == 1
