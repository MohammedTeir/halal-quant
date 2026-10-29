# Remaining Milestone 3–4 sign-off requirements

The source-access gaps have now been addressed with actual downloads and validation:

- **Official FOMC:** eight 2026 events imported from the Federal Reserve, with
  date-only timing, observation provenance and scoped coverage.
- **Free gold reference history:** HistData September 2025 XAUUSD bid quotes provide
  validated 1h/4h OHLC datasets. Volume is explicitly unavailable; incomplete buckets
  are omitted and reported. October's conflicting timestamps are rejected.
- **Real-source quality work:** a blind AI-assisted review of primary-source labels
  exposed a v3 policy failure. V4 passes the unchanged 8-case regression and a new
  4-case blind primary/adversarial pilot. Historical failed evidence is retained.

See [source/label review](source-and-label-review.md) for exact evidence and limits.
The older Finnhub 403 results remain historical account-access facts, but no longer
block these replacement source paths. Network access is active; no environment
configuration or publication was changed by the assistant.

## What remains for strict independent completion

The coding assistant reviewed the source facts without consulting Gemini's outputs,
but also authored the implementation and prompt. The review therefore does **not**
establish independence from the implementation author or human approval. The
review artifacts explicitly mark both as false.

A separate domain reviewer must approve source suitability, frozen labels, a
representative held-out evaluation and acceptance criteria. Gold data also needs
broader historical/session/completeness validation before release-quality research:
one structurally valid month and one rejected month do not certify the provider.
Primary-source corporate statements are not independently audited financial truth.

The software and limited live paths are implemented and validated. These independent
review/completeness requirements prevent an honest claim of full external sign-off.
Live trading remains disabled and all candidate decisions deny authorization.
