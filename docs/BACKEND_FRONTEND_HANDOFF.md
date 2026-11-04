# Backend handoff for the game frontend

Existing endpoint bodies are unchanged. Optional concurrency headers are now supported on POST /api/session and its actions:

- Generate a UUID `Idempotency-Key` for each intended action. Retrying the same action after a lost response must reuse that key and identical JSON. The backend returns the original response, with `Idempotency-Replayed: true`, without executing again.
- GET /api/session and every executed POST return `X-Lab-Version`. Send the latest version on subsequent POST requests. HTTP 409 `stale-state` means refresh the session before making a new decision. Never automatically retry a replay using a new key.
- Reusing a key with another path/body returns 409 `key-conflict`.
- Receipts are in-memory, limited to the last 256 keys, and disappear when the service restarts. This is bounded retry protection, not durable exactly-once execution. The version contains a random process epoch, so old versions fail after restart.
- Legacy callers without these headers continue working. To receive stale-client protection the frontend must adopt the headers. One local user/process remains the supported mode.

The frontend must distinguish a refused request with no transaction from a mined transaction whose receipt failed. Existing backend results already provide this distinction. No new frontend files were modified for this backend work.
