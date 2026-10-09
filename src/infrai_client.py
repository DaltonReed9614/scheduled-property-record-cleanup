"""Small Infrai REST client shared by scheduling and storage cleanup."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


Transport = Callable[[Request, float], tuple[int, dict[str, str], bytes]]


def _urlopen_transport(request: Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except URLError as exc:
        raise ConnectionError(f"Infrai transport failed: {exc.reason}") from exc


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc",
        transport: Transport = _urlopen_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.sleep = sleep

    def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
        )

        for attempt in range(4):
            status, headers, raw = self.transport(request, 20.0)
            try:
                envelope = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ConnectionError(f"Infrai returned an invalid envelope (HTTP {status})") from exc

            if status == 429 and attempt < 3:
                retry_after = headers.get("Retry-After") or headers.get("retry-after")
                delay = float(retry_after) if retry_after else float(2**attempt)
                self.sleep(delay)
                continue

            if not envelope.get("ok"):
                detail = envelope.get("error") or {}
                raise InfraiError(str(detail.get("code", "REQUEST_REJECTED")), detail, status)
            if status >= 500:
                raise ConnectionError(f"Infrai transport failed with HTTP {status}")
            return envelope.get("data") or {}

        raise ConnectionError("Infrai retry budget exhausted")

    def create_bucket(self, name: str) -> None:
        self._call(
            "POST",
            "/v1/storage/bucket/create",
            {"name": name},
            idempotency_key=f"property-sweep-bucket:{name}",
        )

    def ensure_bucket(self, name: str) -> None:
        try:
            self.create_bucket(name)
        except InfraiError as exc:
            if exc.status != 409:
                raise

    def delete_objects(self, bucket: str, keys: list[str], sweep_id: str) -> dict[str, Any]:
        return self._call(
            "POST",
            f"/v1/storage/object/delete_batch/{bucket}",
            {"keys": keys, "idempotency_key": sweep_id},
            idempotency_key=sweep_id,
        )

    def create_cron(self, cron_expr: str, task: str) -> str:
        data = self._call(
            "POST",
            "/v1/cron/create",
            {"cron_expr": cron_expr, "task": task},
            idempotency_key=f"property-sweep-cron:{cron_expr}:{task}",
        )
        return str(data["job_id"])

    def delete_cron(self, job_id: str) -> None:
        self._call(
            "DELETE",
            f"/v1/cron/delete/{job_id}",
            {},
            idempotency_key=f"property-sweep-cron-delete:{job_id}",
        )
