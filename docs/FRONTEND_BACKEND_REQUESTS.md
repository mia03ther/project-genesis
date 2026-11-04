# Frontend → backend requests

The pixel game (`frontend/`) treats the FastAPI lab as the only authority. It never edits
backend code, scenario manifests, grading rules or golden values. The items below are
things the frontend currently works around; none of them block the game today.

Status: open requests, not yet discussed with the backend owner.

## 1. Stable ids for hints and timeline events (i18n)

- **Today:** hint objects are `{index, total, text}`. The UI translates them by keying
  `HINT_ZH` (`frontend/src/game/text.ts`) on the exact English `text`. Editing a hint
  in `scenarios/wrong-recipient/mission.toml` silently drops back to English.
- Timeline events only have English `title`/`detail`, so the evidence book shows them in
  English.
- **Request:** add a stable `id` to each hint and a machine `type` (plus structured
  params such as `evidence_id`, `choice_id`) to timeline events. Optionally add
  `title_zh`/`text_zh` fields in the mission content.

## 2. Localized criterion explanations and choice feedback

- **Today:** `criteria[].explanation`, `decision.summary`, `result.summary` and the
  choice `feedback` are English. The UI shows its own Chinese feedback per strategy id
  and keeps the English backend text under "后端原文" or "裁判细节".
- **Request:** optional `*_zh` fields, or a `?lang=zh-CN` parameter on the mission and
  result endpoints.

## 3. Label of the requested recipient

- **Today:** `variant.request.pay_to` has `address` and `preview` but no `label`. The
  UI picks the parcel destination (Bob's atelier vs the ownerless warehouse) from
  `transaction.to.label`, which only exists when a transaction was sent. For a refused
  request the parcel stays at the terminal, which is correct, but the UI cannot say
  which account the refused request *would* have paid without matching addresses itself.
- **Request:** add `pay_to.label` (`bob` / `unknown` / `null`) to the variant request.

## 4. "No session yet" without an HTTP error

- **Today:** `GET /api/session` returns 404 `no-session` before the first case. The
  frontend handles it, but browsers log a red console error on every first visit.
- **Request (optional):** `GET /api/session` → `200 {"session": null}`, or a
  `GET /api/status` that includes `has_session`.

## 5. Case identity

- **Today:** the UI detects "a new case was opened" with a local counter
  (`useLab().cases`). If another tab restarts the case, this tab only notices through
  `stale-state` on its next action.
- **Request:** a `case_id` (or the process epoch already in `X-Lab-Version`) in the
  session body, so the UI can tell "same case, newer version" from "a different case".

## 6. Distinguish "chain starting" from "chain down"

- **Today:** any 503 is shown as "本地链没有就绪" with a reconnect button.
- **Request:** an error `code` such as `chain-starting` vs `chain-unavailable`, and
  `Retry-After` when a retry is likely to succeed.
