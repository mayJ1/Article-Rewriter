# Rewrite API behavior

Use this reference only for troubleshooting or client maintenance.

## Contract

- Default base URL: `https://www.qqat.cn/api/v1/open`
- Authentication: `Authorization: Bearer <API Key>`
- Create: `POST /rewrite/tasks`
- Query: `GET /rewrite/tasks/{task_id}`
- Cancel: `POST /rewrite/tasks/{task_id}/cancel`
- Create body: `{"source_text": "...", "intensity": 5}`
- `Idempotency-Key` is required on create. Reuse it only when retrying the same create request.
- Intensity is an integer from `0` through `9`; default is `5`.
- The API is asynchronous and currently supports polling rather than webhooks.

Poll every 2–5 seconds. Stop on `succeeded`, `failed`, `recoverable_failed`, or `cancelled`. Follow `Retry-After` on HTTP 429. Retry network failures and temporary 5xx responses only a limited number of times.

On success, `data.result_text` contains the complete rewritten text. Usage metadata includes `input_chars`, `output_chars`, `total_amount`, and `currency`. Treat the returned amount as authoritative instead of recalculating it.

The upstream service may occasionally persist Unicode replacement characters (`U+FFFD`) inside an otherwise successful result. The portable client reports these and obvious unpaired Markdown markers through `quality_issues`. This is a result-quality signal, not a local UTF-8 decoding failure. Do not automatically create another paid task in response.

## Important errors

| Code | Meaning |
| --- | --- |
| `INVALID_API_KEY` | The configured key is invalid, expired, or rotated. |
| `INSUFFICIENT_API_BALANCE` | The account balance is insufficient. |
| `API_CREDIT_EXPIRED` | The purchased API credit has expired. |
| `API_REQUEST_TOO_LARGE` | The complete article exceeds the current account's single-request limit. |
| `API_CONCURRENCY_LIMITED` | Another task is occupying the available worker slot; retry later. |
| `API_RATE_LIMITED` | Follow `Retry-After`. |
| `API_TASK_NOT_FOUND` | The task ID is unavailable to the configured key. |

Do not log the authorization header, full API Key, or source article. Preserve `request_id` for support diagnostics.
