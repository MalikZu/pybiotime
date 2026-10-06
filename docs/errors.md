# Errors

Every exception derives from `BioTimeError`.

| Exception | When |
|---|---|
| `TransportError` | No response: connection refused, DNS failure, timeout, TLS error. The message names the underlying httpx error, which is not chained: its traceback holds the raw request headers. |
| `FaultPageError` | The server sent a non-JSON page, often HTML with HTTP 200. Usually a wrong path or a server that is starting. |
| `APIError` | Any error response. Has `status_code`, `detail` and `body`. |
| `AuthenticationError` | HTTP 401, or the login was rejected. |
| `LoginSuspendedError` | Logins are paused after rejected credentials. Has `retry_after`. |
| `PermissionDeniedError` | HTTP 403. |
| `LicenseError` | HTTP 403 that mentions the licence. |
| `NotFoundError` | HTTP 404. |
| `BadRequestError` | HTTP 400. `field_errors` maps each field to its messages. |
| `ServerError` | HTTP 5xx. The body is kept out of the message, since it can contain a traceback. |
| `PaginationError` | Pages that repeat or loop. Stops instead of reading forever. |
| `ResponseShapeError` | JSON that does not fit the model. |
| `ReadStateError` | A `read_new` state that does not fit the server. |

## Retries

GET requests are retried twice after a network error or HTTP 502, 503 or 504, with a
short, growing pause. Change the count with `retries=`. Other methods are never retried,
since repeating a write could apply it twice.

## Timeouts

Each request waits up to 60 seconds by default. The first request after the server has
been idle can take more than 30 seconds. Change it with `timeout=`.
