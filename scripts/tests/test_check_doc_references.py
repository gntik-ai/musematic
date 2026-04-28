from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "check-doc-references.py"
    spec = importlib.util.spec_from_file_location("check_doc_references", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check_doc_references = _load_module()


def test_load_fr_numbers_from_headings(tmp_path: Path) -> None:
    fr_doc = tmp_path / "fr.md"
    fr_doc.write_text("### FR-001 First\n\n### FR-002 Second\n", encoding="utf-8")

    assert check_doc_references.load_fr_numbers(fr_doc) == {"FR-001", "FR-002"}


def test_valid_reference_exits_zero(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    fr_doc = docs / "functional-requirements-revised-v6.md"
    fr_doc.write_text("### FR-001 First\n", encoding="utf-8")
    (docs / "page.md").write_text("See FR-001.\n", encoding="utf-8")

    status, output = check_doc_references.check_references(docs, fr_doc)

    assert status == 0
    assert "No broken FR references" in output


def test_broken_reference_exits_one(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    fr_doc = docs / "functional-requirements-revised-v6.md"
    fr_doc.write_text("### FR-001 First\n", encoding="utf-8")
    (docs / "page.md").write_text("See FR-999.\n", encoding="utf-8")

    status, output = check_doc_references.check_references(docs, fr_doc)

    assert status == 1
    assert "FR-999" in output


def test_multiple_fr_documents_are_combined(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    base_doc = docs / "functional-requirements-revised-v6.md"
    saas_doc = docs / "functional-requirements-saas-pass.md"
    base_doc.write_text("### FR-001 First\n", encoding="utf-8")
    saas_doc.write_text("### FR-685 SaaS pass\n", encoding="utf-8")
    (docs / "page.md").write_text("See FR-001 and FR-685.\n", encoding="utf-8")

    status, output = check_doc_references.check_references(docs, (base_doc, saas_doc))

    assert status == 0
    assert "No broken FR references" in output


def test_uncovered_frs_are_informational(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    fr_doc = docs / "functional-requirements-revised-v6.md"
    fr_doc.write_text("### FR-001 First\n\n### FR-002 Second\n", encoding="utf-8")
    (docs / "page.md").write_text("See FR-001.\n", encoding="utf-8")

    status, output = check_doc_references.check_references(docs, fr_doc)

    assert status == 0
    assert "FR-002" in output


def test_unparseable_fr_doc_exits_two(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    fr_doc = docs / "functional-requirements-revised-v6.md"
    fr_doc.write_text("# No FR headings\n", encoding="utf-8")

    status, output = check_doc_references.check_references(docs, fr_doc)

    assert status == 2
    assert "unparseable" in output


def test_scan_ignores_canonical_fr_doc(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    fr_doc = docs / "functional-requirements-revised-v6.md"
    fr_doc.write_text("### FR-001 First\nMentions FR-999 as an example.\n", encoding="utf-8")

    refs = check_doc_references.scan_doc_references(docs, fr_doc)

    assert refs == {}
