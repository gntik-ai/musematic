from __future__ import annotations

from pathlib import Path

from ci.lint_llm_calls import find_violations


def test_lint_llm_calls_allows_router_and_blocks_new_direct_call(tmp_path: Path) -> None:
    allowed = (
        tmp_path
        / "apps/control-plane/src/platform/common/clients/model_provider_http.py"
    )
    blocked = tmp_path / "apps/control-plane/src/platform/new_client.py"
    config = tmp_path / "apps/control-plane/src/platform/common/config.py"
    allowed.parent.mkdir(parents=True)
    blocked.parent.mkdir(parents=True, exist_ok=True)
    config.parent.mkdir(parents=True, exist_ok=True)
    allowed.write_text('import httpx\nURL = "/v1/chat/completions"\n', encoding="utf-8")
    blocked.write_text('import httpx\nURL = "/v1/messages"\n', encoding="utf-8")
    config.write_text('URL = "/v1/chat/completions"\n', encoding="utf-8")

    assert find_violations(tmp_path) == [
        (
            Path("apps/control-plane/src/platform/new_client.py"),
            2,
            'URL = "/v1/messages"',
        )
    ]
