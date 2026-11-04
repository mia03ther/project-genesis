"""Bounded retry receipts and optimistic concurrency for the single local lab."""
from __future__ import annotations

import hashlib
from collections import OrderedDict
from uuid import uuid4

from starlette.responses import Response


class RequestLedger:
    def __init__(self) -> None:
        self.epoch = uuid4().hex
        self.revision = 0
        self.receipts: OrderedDict[str, tuple[str, bytes, int, dict[str, str]]] = OrderedDict()

    @property
    def version(self) -> str:
        return f"{self.epoch}:{self.revision}"

    def fingerprint(self, method: str, path: str, body: bytes) -> str:
        return hashlib.sha256(method.encode() + b'\0' + path.encode() + b'\0' + body).hexdigest()

    def lookup(self, key: str, fingerprint: str) -> Response | None:
        receipt = self.receipts.get(key)
        if receipt is None:
            return None
        original, body, status, headers = receipt
        if original != fingerprint:
            return Response('{"error":{"code":"key-conflict","message":"Use a new Idempotency-Key for a different action."}}',
                            status_code=409, media_type="application/json")
        return Response(body, status_code=status, headers={**headers, "Idempotency-Replayed": "true"})

    def remember(self, key: str, fingerprint: str, body: bytes, status: int, headers: dict[str, str]) -> None:
        self.receipts[key] = fingerprint, body, status, headers
        while len(self.receipts) > 256:
            self.receipts.popitem(last=False)
