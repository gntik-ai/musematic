# Channel Adapters Contract

**Feature**: 077-multi-channel-notifications
**Modules**: `apps/control-plane/src/platform/notifications/deliverers/*.py`

This contract documents each per-channel adapter that the channel router can call.

## Common adapter protocol

```python
class ChannelDeliverer(Protocol):
    async def send(
        self,
        *,
        alert: UserAlert,
        target: str,
        config: ChannelConfig,
        canonical_payload: bytes,
        signing_secret: bytes | None = None,
    ) -> ChannelDeliveryResult: ...

@dataclass(slots=True, frozen=True)
class ChannelDeliveryResult:
    outcome: DeliveryOutcome           # success / failed / timed_out / fallback
    failure_reason: str | None = None  # short stable reason key
    last_response_status: int | None = None
    error_detail: str | None = None    # operator-readable; never contains secrets
```

The adapter NEVER logs the signing secret, NEVER logs the SMS API token, NEVER logs the user's phone number, and NEVER logs the email body (rule 23). Targets (email, phone) MAY be logged at debug only when the platform's PII redaction is configured for the test deployment.

---

## Email adapter (`deliverers/email_deliverer.py` — modified)

Extends the existing `EmailDeliverer`. Changes:
- Accepts a `ChannelConfig` instead of an SMTP-settings dict.
- Subject and body templates accept the alert + a deep link constructed from `settings.platform_public_url + alert.deep_link_path`.
- Honours `config.extra.email_format = "html" | "text"` (default `"text"`).
- DLP-redacted payload is passed through unchanged from the router.

## Webhook adapter (`deliverers/webhook_deliverer.py` — modified)

Extends the existing `WebhookDeliverer`. Changes:
- Builds HMAC signature headers via `canonical.build_signature_headers`.
- Uses the canonical JSON payload (JCS) as the HTTP body.
- HTTP timeout default 10s, configurable per webhook.
- 3xx with `Location` followed up to 3 hops; loop → dead-letter `redirect_loop`.

## Slack adapter (`deliverers/slack_deliverer.py` — new)

Slack incoming webhook payload format (Block Kit-lite):

```json
{
  "blocks": [
    {"type": "header", "text": {"type": "plain_text", "text": "<alert.title>"}},
    {"type": "section", "fields": [
      {"type": "mrkdwn", "text": "*Severity:* <alert.severity>"},
      {"type": "mrkdwn", "text": "*Workspace:* <workspace.name>"}
    ]},
    {"type": "section", "text": {"type": "mrkdwn", "text": "<alert.body>"}},
    {"type": "actions", "elements": [
      {"type": "button", "text": {"type": "plain_text", "text": "Open in Musematic"}, "url": "<deep_link>"}
    ]}
  ]
}
```

- HTTP timeout 10s.
- 2xx → success; 4xx other than 429 → dead-letter; 5xx and 429 → retry.
- `429` honours `Retry-After`; absence falls back to schedule.

## Microsoft Teams adapter (`deliverers/teams_deliverer.py` — new)

Teams Adaptive Card payload (Office 365 connector format):

```json
{
  "type": "message",
  "attachments": [{
    "contentType": "application/vnd.microsoft.card.adaptive",
    "content": {
      "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
      "type": "AdaptiveCard",
      "version": "1.4",
      "body": [
        {"type": "TextBlock", "text": "<alert.title>", "weight": "Bolder", "size": "Medium"},
        {"type": "FactSet", "facts": [
          {"title": "Severity", "value": "<alert.severity>"},
          {"title": "Workspace", "value": "<workspace.name>"}
        ]},
        {"type": "TextBlock", "text": "<alert.body>", "wrap": true}
      ],
      "actions": [
        {"type": "Action.OpenUrl", "title": "Open in Musematic", "url": "<deep_link>"}
      ]
    }
  }]
}
```

Same retry semantics as Slack.

## SMS adapter (`deliverers/sms_deliverer.py` — new)

Provider abstraction:

```python
class SmsProvider(Protocol):
    async def send_sms(
        self, *, to: str, body: str, sender: str | None
    ) -> SmsDeliveryResult: ...

class TwilioSmsProvider(SmsProvider):
    def __init__(self, account_sid: str, auth_token: str, default_sender: str): ...
    async def send_sms(self, *, to, body, sender=None) -> SmsDeliveryResult: ...
```

Provider credentials resolve via `SecretProvider` from `secret/data/notifications/sms-providers/{deployment}` (rule 39). The adapter:

1. Checks the workspace SMS cost cap before sending; if exceeded → outcome `fallback`, reason `cost_cap_exceeded`, the channel router falls back to other configured channels (typically email/in-app).
2. Body is constructed as `"<title>\n<short context>\n<short_link>"` truncated to 160 chars (single SMS); longer messages are clipped with an ellipsis and a "see app" deep link.
3. After successful send, increments the workspace's `notifications:sms_cost:{workspace_id}:{yyyy-mm}` counter.

## Verification dispatch

Verification is dispatched by the same adapter set:
- Email adapter: sends a tokenized link.
- SMS adapter: sends a 6-digit code.
- Slack/Teams adapter: sends a one-time test card; the user clicks "Confirm receipt" which hits `/api/v1/me/notifications/channels/{id}/verify` with the verification code shown in the test message body.

## Unit-test contract

- **CA1** — Email: HTML-format flag flips body content type; quiet-hours bypass logic in router still applies before adapter is called.
- **CA2** — Slack: Block Kit payload structurally valid; deep link URL present; 429 with Retry-After honoured; 4xx non-429 → dead-letter.
- **CA3** — Teams: Adaptive Card payload structurally valid; same retry semantics.
- **CA4** — SMS: cost-cap exceeded → outcome `fallback`; counter not incremented; payload not sent.
- **CA5** — SMS: body truncation produces ≤160 chars and an ellipsis or deep-link suffix.
- **CA6** — All adapters: signing/auth secrets never appear in `error_detail` or in structured-log fields (asserted by capture).
- **CA7** — Webhook: HMAC verifiable by the docs-shipped receiver snippet.
- **CA8** — Verification dispatch: each adapter type produces a verification-flavoured payload distinguishable from the standard alert payload.
