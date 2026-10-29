# Requirements still preventing complete Milestone 3–4 sign-off

The implemented paths now pass automated acceptance, including a **12/12 live
Gemini v3 synthetic diagnostic**, real-news durable generation/replay, a real
corporate-action audit and target-specific feed checks. This does not replace
missing sources or independent review.

## Data access: concrete blocked operations

The configured Finnhub key successfully reads company news and company earnings,
but returns **HTTP 403** for both:

- `GET /api/v1/forex/candle` for `OANDA:XAU_USD` (spot-gold candles).
- `GET /api/v1/calendar/economic` (broader macro/FOMC calendar).

Repeated requests or changing the model cannot fix these access denials. Either
provide a Finnhub entitlement allowing these resources, or select another source.
For the gold strategy we need verified spot-gold intraday OHLC data (1h/4h), explicit
UTC bar-close timestamps, acquisition/source metadata and declared volume semantics.
A gold ETF is not silently substituted for spot gold. Provider-neutral CSV import
already exists; real source/session validation remains required.

Official FOMC calendar reference:
<https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm>.
`www.federalreserve.gov` is absent from the active managed network allowlist.
Add it through the supported environment settings before this environment can
inspect and validate the official source. No proxy bypass or environment draft
change was performed. An API key is not needed for the public reference, but an
untested calendar parser or guessed meeting time is not acceptance evidence.
Date-only calendar imports are now supported with conservative whole-date windows.

## Independent quality/source review

The passing diagnostic uses developer-authored synthetic labels and was used to
improve prompt v3. It is **not an independent holdout**. The separate real-news
API check demonstrates transport, grounding, durable persistence and replay;
it does not establish classification accuracy.

A domain reviewer must freeze representative real-news/adversarial labels and
source credibility decisions before a separate holdout evaluation. Preserve the
reviewer identity, review time, exact corpus hash, label provenance, model/prompt
versions, per-case outcomes and accepted quality criteria. Review scope and
calendar/action completeness separately. No automated step claims to be that
human reviewer or grants trading permission.

## Implemented evidence

- [Gemini v3 diagnostic](../reports/gemini-v3-diagnostic-2026-10-29.json).
- [Real-news API generation/replay](../reports/gemini-real-news-api-2026-10-29.json).
- [AAPL raw/adjusted split audit](../reports/aapl-live-split-audit-2026-10-29.json).
- [Completion-pass summary](../reports/milestones-3-4-followup-2026-10-29.json).

Milestone 3 remains open for the missing gold/FOMC source validation and complete
source coverage. Milestone 4's implementation and current diagnostic pass; its
independent quality/source-review sign-off remains open. Live trading stays disabled.
