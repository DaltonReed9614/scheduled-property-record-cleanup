"""HTTP entry point called by the scheduled property cleanup job."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from infrai_client import InfraiClient, InfraiError
from property_sweep import SweepRequest, choose_deletions


BUCKET = os.environ.get("PROPERTY_ARCHIVE_BUCKET", "property-record-archive")


def run_sweep(payload: dict[str, Any], client: InfraiClient) -> dict[str, Any]:
    request = SweepRequest.from_dict(payload)
    candidates = choose_deletions(request)
    if candidates:
        client.delete_objects(
            BUCKET,
            [candidate.storage_key for candidate in candidates],
            request.sweep_id,
        )
    total = (
        len(request.maintenance_requests)
        + len(request.tenant_documents)
        + len(request.inspection_reminders)
    )
    return {
        "sweep_id": request.sweep_id,
        "deleted_record_ids": [candidate.record_id for candidate in candidates],
        "kept_count": total - len(candidates),
    }


class CleanupHandler(BaseHTTPRequestHandler):
    client: InfraiClient

    def do_POST(self) -> None:
        if self.path != "/cleanup/sweep":
            self._send(404, {"error": "route not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            self._send(200, run_sweep(payload, self.client))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
        except InfraiError as exc:
            self._send(exc.status if 400 <= exc.status < 500 else 502, {"error": exc.code})

    def _send(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    client = InfraiClient(os.environ["INFRAI_API_KEY"])
    client.ensure_bucket(BUCKET)
    CleanupHandler.client = client
    port = int(os.environ.get("PORT", "8080"))
    print(f"Property cleanup listening on http://127.0.0.1:{port}/cleanup/sweep")
    ThreadingHTTPServer(("0.0.0.0", port), CleanupHandler).serve_forever()


if __name__ == "__main__":
    main()
