from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.dlp.scanner import DLPEventInput, DLPScanner, DLPScanResult
from platform.privacy_compliance.events import (
    DLPEventPayload,
    PrivacyEventPublisher,
    PrivacyEventType,
    make_correlation,
)
from platform.privacy_compliance.exceptions import SeededRuleDeletionError
from platform.privacy_compliance.models import PrivacyDLPEvent, PrivacyDLPRule
from platform.privacy_compliance.repository import PrivacyComplianceRepository
from uuid import UUID


class DLPService:
    def __init__(
        self,
        *,
        repository: PrivacyComplianceRepository,
        event_publisher: PrivacyEventPublisher,
    ) -> None:
        self.repository = repository
        self.events = event_publisher

    async def scan_and_apply(
        self,
        text: str,
        workspace_id: UUID | None,
    ) -> DLPScanResult:
        rules = await self.repository.list_dlp_rules(workspace_id)
        scanner = DLPScanner(rules)
        matches = scanner.scan(text, workspace_id)
        result = scanner.apply_actions(text, matches)
        return DLPScanResult(
            output_text=result.output_text,
            blocked=result.blocked,
            events=[
                DLPEventInput(
                    rule_id=event.rule_id,
                    rule_name=event.rule_name,
                    classification=event.classification,
                    action_taken=event.action_taken,
                    match_summary=event.match_summary,
                    workspace_id=workspace_id,
                )
                for event in result.events
            ],
        )

    async def emit_event(
        self,
        event: DLPEventInput,
        *,
        execution_id: UUID | None = None,
    ) -> PrivacyDLPEvent:
        now = datetime.now(UTC)
        persisted = await self.repository.create_dlp_event(
            PrivacyDLPEvent(
                rule_id=event.rule_id,
                workspace_id=event.workspace_id,
                execution_id=execution_id,
                match_summary=event.match_summary,
                action_taken=event.action_taken,
                created_at=now,
            )
        )
        await self.events.publish(
            PrivacyEventType.dlp_event,
            DLPEventPayload(
                rule_id=event.rule_id,
                rule_name=event.rule_name,
                classification=event.classification,
                workspace_id=event.workspace_id,
                execution_id=execution_id,
                action_taken=event.action_taken,
                match_summary=event.match_summary,
                occurred_at=now,
            ),
            key=str(event.workspace_id or event.rule_id),
            correlation_ctx=make_correlation(
                workspace_id=event.workspace_id,
                execution_id=execution_id,
            ),
        )
        return persisted

    async def emit_events(
        self,
        events: list[DLPEventInput],
        *,
        execution_id: UUID | None = None,
    ) -> list[PrivacyDLPEvent]:
        return [await self.emit_event(event, execution_id=execution_id) for event in events]

    async def create_rule(
        self,
        *,
        name: str,
        classification: str,
        pattern: str,
        action: str,
        workspace_id: UUID | None = None,
    ) -> PrivacyDLPRule:
        return await self.repository.create_dlp_rule(
            PrivacyDLPRule(
                workspace_id=workspace_id,
                name=name,
                classification=classification,
                pattern=pattern,
                action=action,
                enabled=True,
                seeded=False,
            )
        )

    async def update_rule(
        self,
        rule_id: UUID,
        *,
        enabled: bool | None = None,
        action: str | None = None,
    ) -> PrivacyDLPRule:
        rule = await self.repository.get_dlp_rule(rule_id)
        if rule is None:
            raise ValueError("DLP rule not found")
        return await self.repository.update_dlp_rule(rule, enabled=enabled, action=action)

    async def delete_rule(self, rule_id: UUID) -> None:
        rule = await self.repository.get_dlp_rule(rule_id)
        if rule is None:
            return
        if rule.seeded:
            raise SeededRuleDeletionError()
        await self.repository.delete_dlp_rule(rule)
