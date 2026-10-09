from datetime import datetime, timezone

from property_sweep import SweepRequest, choose_deletions


def test_sweep_deletes_only_records_past_their_business_cutoff() -> None:
    request = SweepRequest.from_dict(
        {
            "sweep_id": "sweep-2026-09-30",
            "as_of": "2026-09-30T03:00:00Z",
            "maintenance_requests": [
                {
                    "record_id": "repair-old",
                    "storage_key": "maintenance/repair-old.json",
                    "status": "resolved",
                    "updated_at": "2026-08-01T10:00:00Z",
                },
                {
                    "record_id": "repair-open",
                    "storage_key": "maintenance/repair-open.json",
                    "status": "open",
                    "updated_at": "2026-07-01T10:00:00Z",
                },
            ],
            "tenant_documents": [
                {
                    "record_id": "lease-current",
                    "storage_key": "tenants/lease-current.pdf",
                    "expires_at": "2027-01-01T00:00:00Z",
                }
            ],
            "inspection_reminders": [
                {
                    "record_id": "inspection-done",
                    "storage_key": "inspections/inspection-done.json",
                    "status": "completed",
                    "scheduled_for": "2026-09-20T09:00:00Z",
                }
            ],
        }
    )

    selected = choose_deletions(request)

    assert [item.record_id for item in selected] == ["repair-old", "inspection-done"]
    assert request.as_of == datetime(2026, 9, 30, 3, tzinfo=timezone.utc)
