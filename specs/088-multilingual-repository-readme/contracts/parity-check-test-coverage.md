# README Parity Checker Test Coverage

Status: implemented locally

The pytest suite at `scripts/tests/test_readme_parity.py` covers:

- H1/H2/H3 extraction and H4/fenced-code exclusion.
- Badge counting versus normal Markdown links.
- Language-switcher detection and missing-bar handling.
- Unclosed fenced-code rejection before pandoc execution.
- Exit code `0` for structurally identical README variants.
- Exit code `1` for heading drift inside the grace window.
- Exit code `1` for `docs-translation-exempt` drift downgrade.
- Exit code `2` for drift after the tracked grace window expires.
- Exit code `1` for byte-mismatched language switcher bars.
- Exit code `2` for pandoc validation failure.
- Exit code `2` for missing required locale README files.
- Locale typo fixes that do not change heading, badge, or link structure.
- Non-failing warnings for missing local link targets.
- Badge-count mismatch detection.

Command used for local verification:

```bash
pytest scripts/tests/test_readme_parity.py -v
```

Repository-state parity verification on 2026-04-30 used Pandoc 3.9.0.2 from `/tmp/musematic-pandoc/pandoc-3.9.0.2/bin`:

```bash
PATH=/tmp/musematic-pandoc/pandoc-3.9.0.2/bin:$PATH python scripts/check-readme-parity.py
```

Result: exit code `0`. The script emitted only the expected informational warnings for missing `./CONTRIBUTING.md` and `./LICENSE`, which are outside UPD-038.
