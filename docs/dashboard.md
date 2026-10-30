# Dashboard

Open `http://127.0.0.1:8000/dashboard` after starting the API and applying migrations.
The dashboard defaults to **English (LTR)**. Select **العربية** in the header for
Arabic (RTL). Switching languages updates navigation, messages, tables, dates and
notification previews without logging out or fetching data again. The language
preference is saved as `halal-quant.language` in browser local storage. If storage
is unavailable, switching still works for the current page.

Sign in with an invited account. Account & Telegram provides session/password
management, administrator invitations and roles, destination verification,
notification preferences, and delivery status/errors. Recovery is administrator
assisted; no public registration or email transport is exposed. Cookie sessions
resume across reloads and are revoked on password changes, disablement or explicit
revocation. Lock/Sign out clears displayed data and revokes the current session.
The legacy service-key option remains available when configured. Use HTTPS.

Research views include signals, decisions, stored broker observations, research
summaries, audit events and Telegram text previews. Stale account data is labeled;
a failed latest capture does not fall back to an older one. Reported cash is
distinct from verified settled cash. Research/source/compliance acceptance and
order authorization are not implied by a connected dashboard.
Original stored evidence, identifiers and machine status codes retain their source
values; language switching does not rewrite research records or translate evidence.

`GET /api/v1/notifications/preview` defaults to English. Use `?language=ar` for
Arabic. Each preview includes `language`, selected `text`, and both `texts.en` and
`texts.ar`. The preview endpoint never sends messages. Persistent delivery uses a separate
server outbox and configured worker. See [accounts, BotFather and delivery setup](milestone-7-accounts-telegram.md).

The frontend is served by FastAPI on the same origin, with a strict CSP and no
external scripts or fonts. [Arabic operations guide](milestone-7-dashboard.ar.md).
