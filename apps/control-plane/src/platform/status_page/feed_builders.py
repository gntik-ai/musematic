"""Status page feed builders for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import format_datetime
from html import escape
from platform.status_page.schemas import (
    MaintenanceWindowSummary,
    PlatformStatusSnapshotRead,
    PublicIncident,
)
from typing import Any
from xml.etree import ElementTree

try:  # pragma: no cover - exercised when the locked dependency is installed.
    from feedgen.feed import FeedGenerator
except ImportError:  # pragma: no cover - local Python envs may not be uv-synced.
    FeedGenerator = None


DEFAULT_STATUS_BASE_URL = "https://status.musematic.ai"


def build_rss(
    snapshot: PlatformStatusSnapshotRead,
    incidents: list[PublicIncident],
    *,
    base_url: str = DEFAULT_STATUS_BASE_URL,
) -> bytes:
    base_url = base_url.rstrip("/")
    if FeedGenerator is None:
        return _build_rss_fallback(snapshot, incidents, base_url=base_url)
    fg = _base_feed(snapshot, base_url=base_url, self_path="/api/v1/public/status/feed.rss")
    fg.ttl(1)
    for entry in _entries(snapshot, incidents, base_url=base_url):
        feed_entry = fg.add_entry()
        feed_entry.id(entry["id"])
        guid = getattr(feed_entry, "guid", None)
        if callable(guid):
            guid(entry["id"], permalink=False)
        feed_entry.title(entry["title"])
        feed_entry.link(href=entry["link"])
        feed_entry.published(entry["published"])
        feed_entry.updated(entry["updated"])
        feed_entry.description(entry["summary"])
        for category in entry["categories"]:
            feed_entry.category(term=category)
    return _feed_bytes(fg.rss_str(pretty=False))


def build_atom(
    snapshot: PlatformStatusSnapshotRead,
    incidents: list[PublicIncident],
    *,
    base_url: str = DEFAULT_STATUS_BASE_URL,
) -> bytes:
    base_url = base_url.rstrip("/")
    if FeedGenerator is None:
        return _build_atom_fallback(snapshot, incidents, base_url=base_url)
    fg = _base_feed(snapshot, base_url=base_url, self_path="/api/v1/public/status/feed.atom")
    for entry in _entries(snapshot, incidents, base_url=base_url):
        feed_entry = fg.add_entry()
        feed_entry.id(entry["id"])
        feed_entry.title(entry["title"])
        feed_entry.link(href=entry["link"])
        feed_entry.published(entry["published"])
        feed_entry.updated(entry["updated"])
        feed_entry.summary(entry["summary"])
        feed_entry.content(f"<p>{escape(entry['summary'])}</p>", type="html")
        for category in entry["categories"]:
            feed_entry.category(term=category)
    return _feed_bytes(fg.atom_str(pretty=False))


def _base_feed(
    snapshot: PlatformStatusSnapshotRead,
    *,
    base_url: str,
    self_path: str,
) -> Any:
    if FeedGenerator is None:  # pragma: no cover - guarded by callers.
        raise RuntimeError("feedgen is required for feed generation")
    fg = FeedGenerator()
    fg.id(f"{base_url}{self_path}")
    fg.title("Musematic Platform Status")
    fg.link(href=f"{base_url}{self_path}", rel="self")
    fg.link(href=f"{base_url}/", rel="alternate")
    fg.description("Incident and maintenance lifecycle for the Musematic platform.")
    fg.language("en")
    fg.updated(_ensure_aware(snapshot.generated_at))
    return fg


def _entries(
    snapshot: PlatformStatusSnapshotRead,
    incidents: list[PublicIncident],
    *,
    base_url: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for incident in incidents:
        updated = _ensure_aware(incident.last_update_at)
        title_prefix = "Incident resolved" if incident.resolved_at else "Incident"
        entries.append(
            {
                "id": f"urn:musematic:incident:{incident.id}:updated:{updated.isoformat()}",
                "title": f"{title_prefix}: {incident.title} ({incident.severity.value})",
                "link": f"{base_url}/incidents/{incident.id}",
                "published": _ensure_aware(incident.started_at),
                "updated": updated,
                "summary": _incident_summary(incident),
                "categories": ["incident", f"severity:{incident.severity.value}"],
            }
        )
    for window in snapshot.scheduled_maintenance:
        entries.append(_maintenance_entry(window, event="scheduled", base_url=base_url))
    if snapshot.active_maintenance is not None:
        entries.append(
            _maintenance_entry(
                snapshot.active_maintenance,
                event="started",
                base_url=base_url,
            )
        )
    entries.sort(key=lambda item: item["updated"], reverse=True)
    return entries


def _incident_summary(incident: PublicIncident) -> str:
    components = ", ".join(incident.components_affected) or "platform"
    summary = incident.last_update_summary or incident.title
    return f"{summary} Components affected: {components}. Severity: {incident.severity.value}."


def _maintenance_entry(
    window: MaintenanceWindowSummary,
    *,
    event: str,
    base_url: str,
) -> dict[str, Any]:
    updated = _ensure_aware(window.starts_at)
    components = ", ".join(window.components_affected) or "platform"
    return {
        "id": f"urn:musematic:maintenance:{window.window_id}:{event}",
        "title": f"Maintenance {event}: {window.title}",
        "link": f"{base_url}/maintenance/{window.window_id}",
        "published": _ensure_aware(window.starts_at),
        "updated": updated,
        "summary": (
            f"Window: {window.starts_at.isoformat()} to {window.ends_at.isoformat()}. "
            f"Writes blocked: {str(window.blocks_writes).lower()}. Components: {components}."
        ),
        "categories": ["maintenance"],
    }


def _ensure_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _feed_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError(f"Unexpected feed output type: {type(value).__name__}")


def _build_rss_fallback(
    snapshot: PlatformStatusSnapshotRead,
    incidents: list[PublicIncident],
    *,
    base_url: str,
) -> bytes:
    ElementTree.register_namespace("atom", "http://www.w3.org/2005/Atom")
    rss = ElementTree.Element("rss", {"version": "2.0"})
    channel = ElementTree.SubElement(rss, "channel")
    ElementTree.SubElement(channel, "title").text = "Musematic Platform Status"
    ElementTree.SubElement(channel, "link").text = f"{base_url}/"
    ElementTree.SubElement(channel, "description").text = (
        "Incident and maintenance lifecycle for the Musematic platform."
    )
    ElementTree.SubElement(channel, "language").text = "en"
    ElementTree.SubElement(channel, "lastBuildDate").text = format_datetime(
        _ensure_aware(snapshot.generated_at)
    )
    ElementTree.SubElement(channel, "ttl").text = "1"
    for entry in _entries(snapshot, incidents, base_url=base_url):
        item = ElementTree.SubElement(channel, "item")
        ElementTree.SubElement(item, "title").text = entry["title"]
        ElementTree.SubElement(item, "link").text = entry["link"]
        guid = ElementTree.SubElement(item, "guid", {"isPermaLink": "false"})
        guid.text = entry["id"]
        ElementTree.SubElement(item, "pubDate").text = format_datetime(entry["updated"])
        ElementTree.SubElement(item, "description").text = entry["summary"]
        for category in entry["categories"]:
            ElementTree.SubElement(item, "category").text = category
    return _feed_bytes(ElementTree.tostring(rss, encoding="utf-8", xml_declaration=True))


def _build_atom_fallback(
    snapshot: PlatformStatusSnapshotRead,
    incidents: list[PublicIncident],
    *,
    base_url: str,
) -> bytes:
    ElementTree.register_namespace("", "http://www.w3.org/2005/Atom")
    feed = ElementTree.Element("{http://www.w3.org/2005/Atom}feed")
    ElementTree.SubElement(feed, "{http://www.w3.org/2005/Atom}id").text = (
        f"{base_url}/api/v1/public/status/feed.atom"
    )
    ElementTree.SubElement(feed, "{http://www.w3.org/2005/Atom}title").text = (
        "Musematic Platform Status"
    )
    ElementTree.SubElement(
        feed,
        "{http://www.w3.org/2005/Atom}link",
        {"rel": "self", "href": f"{base_url}/api/v1/public/status/feed.atom"},
    )
    ElementTree.SubElement(
        feed,
        "{http://www.w3.org/2005/Atom}link",
        {"rel": "alternate", "href": f"{base_url}/"},
    )
    ElementTree.SubElement(feed, "{http://www.w3.org/2005/Atom}updated").text = (
        _ensure_aware(snapshot.generated_at).isoformat().replace("+00:00", "Z")
    )
    for entry_data in _entries(snapshot, incidents, base_url=base_url):
        entry = ElementTree.SubElement(feed, "{http://www.w3.org/2005/Atom}entry")
        ElementTree.SubElement(entry, "{http://www.w3.org/2005/Atom}id").text = entry_data["id"]
        ElementTree.SubElement(entry, "{http://www.w3.org/2005/Atom}title").text = entry_data[
            "title"
        ]
        ElementTree.SubElement(
            entry,
            "{http://www.w3.org/2005/Atom}link",
            {"href": entry_data["link"]},
        )
        ElementTree.SubElement(entry, "{http://www.w3.org/2005/Atom}updated").text = (
            entry_data["updated"].isoformat().replace("+00:00", "Z")
        )
        ElementTree.SubElement(entry, "{http://www.w3.org/2005/Atom}published").text = (
            entry_data["published"].isoformat().replace("+00:00", "Z")
        )
        ElementTree.SubElement(entry, "{http://www.w3.org/2005/Atom}summary").text = entry_data[
            "summary"
        ]
        for category in entry_data["categories"]:
            ElementTree.SubElement(
                entry,
                "{http://www.w3.org/2005/Atom}category",
                {"term": category},
            )
    return _feed_bytes(ElementTree.tostring(feed, encoding="utf-8", xml_declaration=True))
