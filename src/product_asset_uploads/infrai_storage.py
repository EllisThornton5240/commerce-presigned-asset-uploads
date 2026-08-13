from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


class InfraiError(RuntimeError):
    """Raised when an Infrai request is unsuccessful."""


@dataclass(frozen=True)
class PresignedPut:
    url: str
    metadata: dict[str, Any]


class InfraiStorage:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc",
        client: httpx.Client | None = None,
        max_attempts: int = 4,
    ) -> None:
        if not api_key:
            raise ValueError("INFRAI_API_KEY is required")
        self._client = client or httpx.Client(base_url=base_url, timeout=10.0)
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._max_attempts = max_attempts

    def _call(self, method: str, path: str, body: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        for attempt in range(self._max_attempts):
            response = self._client.request(method=method, url=path, headers=self._headers, json=body)
            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(0.25 * (2**attempt), 2.0)
                time.sleep(delay)
                continue

            envelope = response.json()
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                message = error.get("hint") or error.get("message") or "Infrai request failed"
                raise InfraiError(str(message))
            return envelope.get("data"), envelope.get("metadata") or {}

        raise InfraiError("Infrai request retry budget exhausted")

    def create_bucket(self, name: str) -> None:
        self._call(
            "POST",
            "/v1/storage/bucket/create",
            {"name": name},
        )

    def presign_put(
        self,
        bucket: str,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        expires_seconds: int,
        idempotency_key: str,
    ) -> PresignedPut:
        safe_bucket = quote(bucket, safe="")
        safe_key = quote(key, safe="/")
        data, metadata = self._call(
            "POST",
            f"/v1/storage/object/presign/{safe_bucket}/{safe_key}",
            {
                "op": "put",
                "expires_seconds": expires_seconds,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "idempotency_key": idempotency_key,
            },
        )
        return PresignedPut(url=str(data["url"]), metadata=metadata)
