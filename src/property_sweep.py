"""Business rules for deciding which property records leave storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class MaintenanceRequest:
    record_id: str
    storage_key: str
    status: str
    updated_at: datetime


@dataclass(frozen=True)
class TenantDocument:
    record_id: str
    storage_key: str
    expires_at: datetime


@dataclass(frozen=True)
class InspectionReminder:
    record_id: str
    storage_key: str
    status: str
    scheduled_for: datetime


@dataclass(frozen=True)
class SweepRequest:
    sweep_id: str
    as_of: datetime
    maintenance_requests: tuple[MaintenanceRequest, ...]
    tenant_documents: tuple[TenantDocument, ...]
    inspection_reminders: tuple[InspectionReminder, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SweepRequest":
        return cls(
            sweep_id=str(value["sweep_id"]),
            as_of=parse_time(str(value["as_of"])),
            maintenance_requests=tuple(
                MaintenanceRequest(
                    record_id=str(item["record_id"]),
                    storage_key=str(item["storage_key"]),
                    status=str(item["status"]),
                    updated_at=parse_time(str(item["updated_at"])),
                )
                for item in value.get("maintenance_requests", [])
            ),
            tenant_documents=tuple(
                TenantDocument(
                    record_id=str(item["record_id"]),
                    storage_key=str(item["storage_key"]),
                    expires_at=parse_time(str(item["expires_at"])),
                )
                for item in value.get("tenant_documents", [])
            ),
            inspection_reminders=tuple(
                InspectionReminder(
                    record_id=str(item["record_id"]),
                    storage_key=str(item["storage_key"]),
                    status=str(item["status"]),
                    scheduled_for=parse_time(str(item["scheduled_for"])),
                )
                for item in value.get("inspection_reminders", [])
            ),
        )


@dataclass(frozen=True)
class DeletionCandidate:
    record_id: str
    storage_key: str
    reason: str


def choose_deletions(request: SweepRequest) -> list[DeletionCandidate]:
    maintenance_cutoff = request.as_of - timedelta(days=30)
    selected = [
        DeletionCandidate(item.record_id, item.storage_key, "resolved-maintenance-retention")
        for item in request.maintenance_requests
        if item.status == "resolved" and item.updated_at <= maintenance_cutoff
    ]
    selected.extend(
        DeletionCandidate(item.record_id, item.storage_key, "expired-tenant-document")
        for item in request.tenant_documents
        if item.expires_at <= request.as_of
    )
    selected.extend(
        DeletionCandidate(item.record_id, item.storage_key, "completed-inspection-reminder")
        for item in request.inspection_reminders
        if item.status == "completed" and item.scheduled_for <= request.as_of
    )
    return selected
