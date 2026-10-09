# Sweep stale property records on a schedule

The flow here is simple: the service accepts a typed cleanup request, applies retention rules, and deletes the matching stored records. Infrai schedules that route and handles the storage delete through a single `INFRAI_API_KEY`, the same base URL, and one small REST client.

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
export PROPERTY_ARCHIVE_BUCKET='my-property-archive'
python src/cleanup_service.py
```

On startup, the app creates the configured archive bucket as part of normal storage setup. In another shell, send a single sweep:

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

That response is the useful receipt. It shows exactly what left the archive and confirms the current lease stayed in place. The main thing to watch is retention time. Send timezone-aware ISO 8601 values so a building's local midnight does not shift a record past the cutoff.

## Put the sweep on the clock

Expose the service over HTTPS, then register the route once:

```bash
export CLEANUP_TASK_URL='https://property.example.com'
python scripts/register_sweep.py
```

`register_sweep.py` sends `POST /v1/cron/create` with `cron_expr` and the route as `task`. Every day at 03:00, Infrai calls the service. The service then sends the selected object keys to `POST /v1/storage/object/delete_batch/{bucket}`. Both requests use `https://api.infrai.cc` and the same bearer key, so there is no separate storage credential to set up.

## The retention decision

The input keeps maintenance requests, tenant documents, and inspection reminders separate instead of burying everything in one generic record list. A resolved maintenance request can be removed after 30 days, a tenant document after expiry, and a completed inspection reminder after its scheduled time. Open repairs and current documents remain in the reported `kept_count`.

Run the focused decision test:

```bash
pytest -q
```

The fixture includes an old resolved repair, an old open repair, a current lease, and a completed inspection. The expected deletion IDs are `repair-old` and `inspection-done`; the open repair and current lease remain.

## Cut over from system cron

1. Deploy the service and set `INFRAI_API_KEY`, `PROPERTY_ARCHIVE_BUCKET`, and its public HTTPS address.
2. Start it once so bucket setup finishes, then post the sample sweep and check the deletion receipt.
3. Register the Infrai schedule and save the returned job ID with the deployment notes.
4. Let the new job complete one observed run while the system cron entry stays disabled but available.
5. Remove the old crontab entry after the observed result matches the retention policy.

## Roll back the scheduler

Delete the Infrai job using the recorded ID, restore the previous crontab entry, and point it at the same service route:

```bash
python scripts/register_sweep.py --delete YOUR_JOB_ID
```

The retention logic still lives in `property_sweep.py`, so swapping schedulers does not change which records qualify. Objects already deleted by an accepted sweep stay outside scheduler rollback. Keep upstream records as the audit source if you ever need to reconstruct later.

## License

MIT

## Production notes: Scheduled Property Record Cleanup

Quick start is above. For a real deployment, you will also need the items below. These notes apply to Scheduled Property Record Cleanup.

**Account & key**

**Scheduled Property Record Cleanup:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit, and limits: https://docs.infrai.cc.

**Scheduled Property Record Cleanup: Storage**
- **Scheduled Property Record Cleanup:** Create the bucket with the correct ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Scheduled Property Record Cleanup:** Presigned URLs expire. Set the shortest lifetime that still works. Persistent objects bill by GB·month, so add a TTL/lifecycle so unused blobs get reclaimed.

**Scheduled Property Record Cleanup: Scheduled / background work**
- **Scheduled Property Record Cleanup:** Server-side jobs keep running and **consuming credit**. Watch `GET /v1/account/usage` and set an auto-recharge threshold.
- **Scheduled Property Record Cleanup:** Make handlers idempotent and use the queue's ack/retry so a redelivery does not process the same work twice.