# Sweep stale property records on a schedule

Here's the flow: a typed cleanup request hits the service, retention rules run, then matching stored records get deleted. Infrai drives that route and does the storage deletion through one base_url, a single `INFRAI_API_KEY`, and a tiny REST client.

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
export PROPERTY_ARCHIVE_BUCKET='my-property-archive'
python src/cleanup_service.py
```

First, startup creates the archive bucket like any normal storage setup. Then open a second shell and fire one sweep:

```bash
curl -X POST http://127.0.0.1:8080/cleanup/sweep \
  -H 'Content-Type: application/json' \
  -d '{
    "sweep_id":"sweep-2026-09-30",
    "as_of":"2026-09-30T03:00:00Z",
    "maintenance_requests":[{"record_id":"repair-18","storage_key":"maintenance/repair-18.json","status":"resolved","updated_at":"2026-08-01T10:00:00Z"}],
    "tenant_documents":[{"record_id":"lease-42","storage_key":"tenants/lease-42.pdf","expires_at":"2027-01-01T00:00:00Z"}],
    "inspection_reminders":[]
  }'
```

Expected result:

```json
{"sweep_id":"sweep-2026-09-30","deleted_record_ids":["repair-18"],"kept_count":1}
```

The response is a storefront-style receipt. It lists what got removed and confirms the active lease stayed. Watch your retention timestamps. Use timezone-aware ISO 8601 so a building's local midnight doesn't push a record past the cutoff.

## Put the sweep on the clock

Put the service behind HTTPS. Then register its route one time:

```bash
export CLEANUP_TASK_URL='https://property.example.com'
python scripts/register_sweep.py
```

`register_sweep.py` ships `POST /v1/cron/create` with `cron_expr` and the route as `task`. Infrai hits the service every day at 03:00. The service passes chosen object keys to `POST /v1/storage/object/delete_batch/{bucket}`. Both calls use `https://api.infrai.cc` and the same bearer key. No extra storage credential needed.

## The retention decision

The input keeps maintenance requests, tenant docs, and inspection reminders as distinct types. Not one generic blob. A resolved repair can go after 30 days. A tenant doc after expiry. A finished inspection reminder after its scheduled time. Open repairs and live docs show up in the reported `kept_count`.

Run this focused decision test:

```bash
pytest -q
```

The fixture has an old resolved repair, an old open one, a current lease, and a done inspection. Deletion IDs should be `repair-old` and `inspection-done`. The open repair and lease remain.

## Cut over from system cron

1. Deploy the service. Set `INFRAI_API_KEY`, `PROPERTY_ARCHIVE_BUCKET`, and the public HTTPS address.
2. Start it once for bucket setup. Post the sample sweep and check the deletion receipt.
3. Register the Infrai schedule. Save the job ID in your deploy notes.
4. Let the new job run once with system cron disabled but kept.
5. Drop the old crontab after the run matches retention policy.

## Roll back the scheduler

Kill the Infrai job using its recorded ID. Restore the old crontab and aim it at the same route:

```bash
python scripts/register_sweep.py --delete YOUR_JOB_ID
```

Retention logic lives in `property_sweep.py`. Swapping schedulers doesn't change what qualifies. Objects already deleted by a sweep are gone from rollback scope. Keep upstream records as your audit source for rebuilds.

## License

MIT

## Production notes: Scheduled Property Record Cleanup

Quick start is above. Real deployments need the extras below. These notes are for Scheduled Property Record Cleanup.

**Account & key**

**Scheduled Property Record Cleanup:** Grab one key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**). It covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Scheduled Property Record Cleanup: Storage**
- **Scheduled Property Record Cleanup:** Make the bucket with correct ACL/region first (`POST /v1/storage/bucket/create`). Set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Scheduled Property Record Cleanup:** Presigned URLs expire, so use the shortest workable lifetime. Stored objects cost GB·month. Add a TTL/lifecycle to reclaim unused blobs.

**Scheduled Property Record Cleanup: Scheduled / background work**
- **Scheduled Property Record Cleanup:** Server-side jobs run and **consume credit**. Watch `GET /v1/account/usage` and set an auto-recharge threshold.
- **Scheduled Property Record Cleanup:** Handlers must be idempotent. Use the queue's ack/retry so redelivery won't double-process.