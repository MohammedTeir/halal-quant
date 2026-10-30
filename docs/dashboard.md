# Dashboard

Open `http://127.0.0.1:8000/dashboard` after starting the API and applying migrations.
The dashboard defaults to **English (LTR)**. Select **العربية** in the header for
Arabic (RTL). Switching languages updates navigation, messages, tables, dates and
notification previews without logging out or fetching data again. The language
preference is saved as `halal-quant.language` in browser local storage. If storage
is unavailable, switching still works for the current page.

Authenticate with the configured `DASHBOARD_API_KEY`, not a provider key. Access
keys remain in page memory and are never saved alongside the language preference.
Reloading requires authentication again. Locking clears displayed data and the
cached snapshot. Use HTTPS when exposing the app beyond localhost.

The initial dashboard is read-only: signals, decisions, stored broker observations,
research summaries, audit events and Telegram text previews. Stale account data is
labeled explicitly; a failed latest capture does not fall back to an older one.
Reported cash is distinct from verified settled cash. Research/source/compliance
acceptance and order authorization are not implied by a connected dashboard.
Original stored evidence, identifiers and machine status codes retain their source
values; language switching does not rewrite research records or translate evidence.

`GET /api/v1/notifications/preview` defaults to English. Use `?language=ar` for
Arabic. Each preview includes `language`, selected `text`, and both `texts.en` and
`texts.ar`. These are previews only; no Telegram messages are sent. Persistent
notification delivery remains pending.

The frontend is served by FastAPI on the same origin, with a strict CSP and no
external scripts or fonts. [Arabic operations guide](milestone-7-dashboard.ar.md).
