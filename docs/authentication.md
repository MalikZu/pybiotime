# Authentication

Pass one of these as `auth=` when you create the client.

| Class | Use it when |
|---|---|
| `TokenAuth("user", "password")` | Default choice. Logs in once for a token that does not expire. |
| `TokenAuth(token="...")` | You already have a token. The client never logs in. |
| `JWTAuth("user", "password")` | You want short-lived tokens. The client logs in again before each one expires. |
| `BasicAuth("user", "password")` | Your licence blocks token logins. Sends the password with every request. |
| `StaffTokenAuth`, `StaffJWTAuth` | You log in as an employee self-service account. |

Use a BioTime system user made for the integration, with only the permissions it needs.

## What the client does for you

- **Logs in lazily**, on the first request.
- **Logs in again once** if the server rejects the token, then retries the request.
- **Pauses logins for 60 seconds** after the server rejects the username or password.
  Retrying a wrong password in a loop can lock the account. During the pause, calls raise
  `LoginSuspendedError` without contacting the server. Change the pause with `login_cooldown=`.

## Secrets

Passwords and tokens never appear in `repr()` or in pybiotime's logs.

Some BioTime responses contain secrets too: employee payloads include a password hash
and the device PIN. Do not log raw responses.
