from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_grafana_embed_uses_auth_proxy_and_csp() -> None:
    component = (
        ROOT / "apps/web/components/features/admin/EmbeddedGrafanaPanel.tsx"
    ).read_text()
    route = (ROOT / "apps/web/app/api/admin/grafana-proxy/[...path]/route.ts").read_text()

    assert "/api/admin/grafana-proxy" in component
    assert "Grafana panel unavailable" in component
    assert "frame-ancestors 'self'" in route
    assert "Authorization" in route
