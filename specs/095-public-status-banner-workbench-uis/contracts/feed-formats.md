# Feed Format Reference — UPD-045

This document specifies the RSS 2.0 and Atom 1.0 feed payloads served by `/api/v1/public/status/feed.rss` and `/api/v1/public/status/feed.atom`. Both feeds share the same content; they differ only in serialization.

## Refresh cadence

Feeds reflect any incident lifecycle change within ≤ 60 seconds (FR-695-22 / SC-003). The CDN cache TTL is set to 30 seconds with `must-revalidate` so pull-style consumers do not over-poll.

## RSS 2.0 example

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Musematic Platform Status</title>
    <link>https://status.musematic.ai/</link>
    <atom:link href="https://status.musematic.ai/api/v1/public/status/feed.rss"
               rel="self" type="application/rss+xml" />
    <description>Incident and maintenance lifecycle for the Musematic platform.</description>
    <language>en</language>
    <lastBuildDate>Tue, 28 Apr 2026 13:45:02 +0000</lastBuildDate>
    <ttl>1</ttl>

    <item>
      <title>Incident: Elevated error rate on control-plane reads (warning)</title>
      <link>https://status.musematic.ai/incidents/incident-uuid</link>
      <guid isPermaLink="false">incident-uuid#updated-2026-04-28T13:42:11Z</guid>
      <pubDate>Tue, 28 Apr 2026 13:42:11 +0000</pubDate>
      <description><![CDATA[
        Investigating elevated 5xx error rate on the control-plane API.
        Affected components: control-plane-api.
        Severity: warning.
        Last update: 2026-04-28 13:42:11 UTC — Investigating root cause.
      ]]></description>
      <category>incident</category>
      <category>severity:warning</category>
    </item>

    <item>
      <title>Maintenance scheduled: Q2 platform upgrade</title>
      <link>https://status.musematic.ai/maintenance/window-uuid</link>
      <guid isPermaLink="false">window-uuid#scheduled</guid>
      <pubDate>Mon, 28 Apr 2026 09:00:00 +0000</pubDate>
      <description><![CDATA[
        Scheduled window: 2026-05-02 22:00 UTC → 2026-05-02 23:30 UTC.
        Writes will be paused on: control-plane-api, reasoning-engine.
      ]]></description>
      <category>maintenance</category>
    </item>
  </channel>
</rss>
```

## Atom 1.0 example

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>https://status.musematic.ai/api/v1/public/status/feed.atom</id>
  <title>Musematic Platform Status</title>
  <link rel="self" href="https://status.musematic.ai/api/v1/public/status/feed.atom" />
  <link rel="alternate" href="https://status.musematic.ai/" />
  <updated>2026-04-28T13:45:02Z</updated>

  <entry>
    <id>urn:musematic:incident:incident-uuid:updated:2026-04-28T13:42:11Z</id>
    <title>Incident: Elevated error rate on control-plane reads (warning)</title>
    <link href="https://status.musematic.ai/incidents/incident-uuid" />
    <updated>2026-04-28T13:42:11Z</updated>
    <published>2026-04-28T13:30:00Z</published>
    <category term="incident" />
    <category term="severity:warning" />
    <summary type="text">Investigating elevated 5xx error rate on control-plane API. Components affected: control-plane-api.</summary>
    <content type="html"><![CDATA[
      <p>Severity: <strong>warning</strong></p>
      <p>Last update: 2026-04-28 13:42:11 UTC — Investigating root cause.</p>
    ]]></content>
  </entry>

  <entry>
    <id>urn:musematic:maintenance:window-uuid:scheduled</id>
    <title>Maintenance scheduled: Q2 platform upgrade</title>
    <link href="https://status.musematic.ai/maintenance/window-uuid" />
    <updated>2026-04-28T09:00:00Z</updated>
    <published>2026-04-28T09:00:00Z</published>
    <category term="maintenance" />
    <summary type="text">Window: 2026-05-02 22:00 UTC → 2026-05-02 23:30 UTC.</summary>
  </entry>
</feed>
```

## Stable IDs

- Incident updates: `urn:musematic:incident:{incident_id}:updated:{iso8601_update_at}` — every update is its own item so RSS readers re-display the latest status.
- Incident resolution: `urn:musematic:incident:{incident_id}:resolved`.
- Maintenance scheduled: `urn:musematic:maintenance:{window_id}:scheduled`.
- Maintenance started: `urn:musematic:maintenance:{window_id}:started`.
- Maintenance ended: `urn:musematic:maintenance:{window_id}:ended`.
- Component degraded/recovered: `urn:musematic:component:{component_id}:state:{state}:at:{iso8601}`.

Stable IDs guarantee RSS clients can deduplicate and order correctly.

## Categories

- `incident`, `maintenance`, `component`
- `severity:info`, `severity:warning`, `severity:high`, `severity:critical`

## Subscriber identifiers

The feeds **do not** include subscriber identifiers (per spec security note). Anyone with the URL can read; tracking happens out-of-band via webhook subscriptions.
