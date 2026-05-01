from __future__ import annotations

from datetime import UTC, datetime
from platform.status_page.feed_builders import build_atom, build_rss
from platform.status_page.schemas import (
    OverallState,
    PlatformStatusSnapshotRead,
    PublicIncident,
    SourceKind,
)
from xml.etree import ElementTree


def _snapshot(now: datetime) -> PlatformStatusSnapshotRead:
    return PlatformStatusSnapshotRead(
        generated_at=now,
        source_kind=SourceKind.poll,
        overall_state=OverallState.degraded,
        components=[],
        active_incidents=[],
        scheduled_maintenance=[],
        active_maintenance=None,
        recently_resolved_incidents=[],
        uptime_30d={},
    )


def _incident(now: datetime) -> PublicIncident:
    return PublicIncident(
        id="incident-123",
        title="Elevated control-plane errors",
        severity="warning",
        started_at=now,
        last_update_at=now,
        last_update_summary="Investigating elevated 5xx rate.",
        components_affected=["control-plane-api"],
    )


def test_rss_feed_has_valid_channel_stable_ids_and_no_subscriber_identifiers() -> None:
    now = datetime(2026, 4, 28, 13, 45, tzinfo=UTC)
    xml = build_rss(_snapshot(now), [_incident(now)], base_url="https://status.example.test")

    root = ElementTree.fromstring(xml)
    assert root.tag.endswith("rss")
    channel = root.find("channel")
    assert channel is not None
    assert channel.findtext("title") == "Musematic Platform Status"
    item = channel.find("item")
    assert item is not None
    guid = item.findtext("guid") or ""
    assert "incident-123" in guid
    assert "updated" in guid
    assert b"subscriber" not in xml.lower()
    assert b"dev@example.com" not in xml


def test_atom_feed_has_valid_namespace_stable_ids_and_no_subscriber_identifiers() -> None:
    now = datetime(2026, 4, 28, 13, 45, tzinfo=UTC)
    xml = build_atom(_snapshot(now), [_incident(now)], base_url="https://status.example.test")

    root = ElementTree.fromstring(xml)
    assert root.tag == "{http://www.w3.org/2005/Atom}feed"
    entry = root.find("{http://www.w3.org/2005/Atom}entry")
    assert entry is not None
    entry_id = entry.findtext("{http://www.w3.org/2005/Atom}id") or ""
    assert entry_id.startswith("urn:musematic:incident:incident-123:updated:")
    assert b"subscriber" not in xml.lower()
    assert b"dev@example.com" not in xml
