# Milestones and acceptance tracker

Source: [master blueprint v2](blueprint-v2.md). Python strategy development replaces
mandatory Pine acceptance; Pine remains optional. Status updated 2026-10-30.
Implementation acceptance and independent release sign-off are tracked separately.

| # | Deliverable | Current state | Evidence / remaining acceptance |
|---|---|---|---|
| 1 | Foundation and architecture | Implemented; software acceptance passes | Boot/persistence, credentials, migrations through `0005_feed_coverage`, schema drift, replay and CI checks. Latest local suite: 334 passed. Hosted CI passed for `8afc05d`; check the current commit's run after push. |
| 2 | Three Python strategies; optional Pine | Agreed Python acceptance passes | Long-only causal stock/ETF/gold strategies; nonzero synthetic train/holdout trades, explicit costs, flat reconciliation and byte-identical reports. Pine compilation/parity remains unverified and optional. |
| 3 | Market and news data | Implementation acceptance passes; historical/source sign-off incomplete | Real Alpaca candles/actions, Finnhub news/earnings, BLS and official FOMC ingestion; immutable revisions, point-in-time provenance, scoped freshness, corporate-action and session checks. A normalized 2025 audit validates all 12 months (5,855 1h / 1,263 4h bars), retaining proof of 60 identical duplicates removed. Source/session research-release approval remains unavailable. |
| 4 | AI intelligence and decisions | Implementation acceptance passes; independent quality sign-off incomplete | Strict schemas/evidence/targets, durable Gemini jobs, event policies and deterministic gates; v5 passes 16/16 exposed real-primary/adversarial regression and 8/8 fresh blind pilot. Separate AI technical review now completed with conditional research-only acceptance; publisher identity, gold session binding and representative policy/calibration conditions remain open before deployment. |
| 5 | Compliance and risk | Software implemented and tested for bounded research; full operational sign-off pending | Versioned role attestations, stock-ratio rules, read-only broker/quote capture, loss/peak reconciliation, serialized research holds/kill switch and linked decision revalidation pass. [Current workflow](milestone-5-operations.md). Named qualified review and real cash/settlement/lending/custody proofs remain unprovided; real orders are deferred. |
| 6 | Research and backtesting | Portfolio/replay/optimization software implemented; performance acceptance pending | [Current research workflow](milestone-6-research.md): shared-cash portfolio, PIT compliance/news/macro replay, training-only walk-forward selection, separate portfolio holdout periods with cost stress, technical/buy-and-hold baselines, liquidity proxy, seeded Monte Carlo and explicit gates. Actual 2025 gold diagnostic is blocked by default warm-up history and unavailable volume. Verified representative history and successful untouched out-of-sample performance remain required; broker reconciliation belongs to milestone 8. |
| 7 | Dashboard and Telegram | Complete for the documented deployment; Android hosting limits retained | [2026-10-31 operator evidence](../reports/milestone7-operator-acceptance-2026-10-31.json): deployed accounts/roles/revocation, four private SENT cases, received group delivery, encrypted PostgreSQL 18 isolated restore, off-device backup/separate key confirmation, and supervised restart with 60 seconds of activity. Authenticated dashboard export confirms all four cases and private/group setup history; received Arabic text was supplied. Android uptime is limited; earlier milestone gates remain unchanged. |
| 8 | Paper trading | In progress: internal forward software implemented; actual elapsed acceptance pending | [Implementation](milestone-8-paper-trading.md) and [operator runbook](milestone-8-forward-operations.md): read-only Alpaca data, reviewed decision bridge, autonomous virtual lifecycle/protection, calendar settlement, economic reconciliation, restart evidence and bilingual controls. Configure and review a real campaign, then accumulate the required elapsed sessions; accelerated tests do not establish stable forward acceptance. |
| 9 | Optional live broker integration | Disabled; not started | Compatible structure/broker, independent compliance review and explicit live-readiness approval. |

## Milestone 3 evidence

- Real samples include 17 AAPL IEX daily candles with sourced session checks,
  108 news observations, 313 BLS calendar events, company earnings and actions,
  a 25-bar 2020 split/volume audit and eight official 2026 FOMC dates.
- Immutable source revisions and authoritative server receipt times prevent
  later corrections from silently rewriting historical visibility. Observed-only
  publication provenance never invents historical release timestamps.
- Scoped provider/target/asset/purpose/window coverage fails closed for missing,
  stale, synthetic, unrelated or reduced-window polls. Date-only events restrict
  the whole local date, including DST boundaries.
- [Gold history audit](../reports/gold-history-audit-2025-2026-10-29.json): all twelve
  2025 archives fetched; 11 validate, producing 5,335 complete 1h and 1,151 complete
  4h bars. October conflicts are rejected. Missing volume is explicit, gaps are not
  filled, and derived artifacts are recomputed against retained source bytes.
- **The year-wide structural gate fails**, correctly: one rejected month cannot be
  concealed by summing only valid months. No session/price/liquidity certification
  or continuous-year research approval is implied.

## Milestone 4 evidence

- Strict JSON, source/target binding, exact quotes, no privileged output fields,
  source corrections during inference, claims before network calls, replay and
  bounded transport behavior are covered by automated tests.
- Historical v2/v3/v4 runs, failures and prompt text remain unchanged/readable.
  The larger real-source v4 pilot scored **10/16**. All eight attacks requested
  review, but financial sentiment was inconsistent with the frozen labels.
- V5 explicitly separates year-over-year earnings facts from absolute positive
  accounting levels, macro observations from unsupported gold-return predictions,
  and injected control instructions from financial sentiment.
- V5 passes the unchanged **16/16 regression** and a separately frozen **8/8 fresh
  pilot**. This is a purposive author-labeled sample, not independent approval,
  statistical calibration or representative production accuracy.
- The scorer now requires human review for attack quality acceptance and separately
  measures safe policy containment. A safely contained attack can still fail
  sentiment quality. Category support counts make sample omissions visible.
- An exclusive, hash-bound [review packet](independent-review.md) separates blind
  source/label evidence from model outputs and supplies an unapproved review form.

## Verification and release limits

The current full isolated SQLite suite passes **334 tests** with one existing
Starlette/httpx TestClient deprecation warning. Lint/format checks pass. Hosted CI
uses PostgreSQL and runs migrations, regression tests, synthetic research and mock
Gemini/offline evaluation; it never makes live provider calls. Historical reports
remain historical evidence, not the current milestone state.

The original blueprint's Milestone 3 timestamp/provenance/freshness and Milestone 4
schema/injection/deterministic-policy checks are implemented and pass software
acceptance. The stricter source-completeness and independent-review requirements
recorded during follow-up remain open; **neither milestone has full external
sign-off**. See [exact blockers](completion-requirements.md).

All decisions still deny execution authority. No profitability, paper-trading
readiness, ownership/compliance verification or Shariah approval is claimed.


## Exact-duplicate and external-label follow-up

The original strict gold failure remains unchanged. All repeated October rows are
byte-identical; an explicit lossless normalization with hash/count/timestamp proof
now passes [12/12 annual structural checks](../reports/gold-history-normalized-2025-2026-10-29.json).
It never edits/sorts timestamps or prices; differing duplicates still fail. Source
session completeness and suitability remain separate release gates.

An [external original-human-label benchmark](external-label-evaluation.md) adds
balanced FinancialPhraseBank sentiment checks independent of author labels. It does
not confer human project approval or independently label event/policy/attack behavior.
The published source is limited to noncommercial research, and text is not runtime data.


## User-selected independent technical review and session investigation

The separate AI [review](independent-technical-review-2026-10-29.md) is complete,
with conditional research-only acceptance and three medium release conditions.
The reviewer independently recounted model/source evidence and verified two fixes:
reference table-rule extraction and the obsolete provider table. It found no direct
execution-authority bypass in the inspected paths. It is not human/institutional
approval, blind model-family independence or blanket source authority.

The [gold session investigation](gold-session-review.md) inventories all 300 absent
runs across 353,940 observed minutes, including coverage boundaries, and compares
against a hash-bound, machine-verified official reference table with New York DST.
Provider/2025 holiday binding remains unverified; no reference gap is certified as a
HistData market closure. Full current regression: **334 passed**. Historical
reports preserve their earlier states; the review does not grant execution approval.


## Milestone 5 initial implementation

The [controls increment](milestone-5-controls.md) adds 78 hypothetical engine/API tests;
full regression is **412 passed**. Preview is authenticated/read-only and does not
promote caller facts into real broker/compliance/ownership state. Scope is research
simulation; methodology defaults unselected and no operational approval is granted.


## Milestone 5 stored workflow follow-up

The [stored workflow](milestone-5-operations.md) implements migration `0006_controls`,
separate reviewer/operator/broker-reader credentials, immutable review IDs/hashes,
stable methodology withdrawal, server receipt/as-of history, reviewer-bound
financial ratios and loss reconciliation, durable kill/divestment-review records,
read-only provider capture claims and server-only current control checks. Shared
capacity and linked revalidation lock state before taking the current-time sample.
No stale retry extends reservations or clears a later kill/revocation.

Full local regression: **459 passed**; 47 new checks after the 412-test checkpoint.
Actual paper-account and quote read-only probes succeeded; the account had no
positions/orders, and cash/settlement/lending contract proof remains false.
[Independent AI review](milestone-5-independent-review-2026-10-29.md) rechecked all six
resolved findings; bounded research acceptance does not supply human/Shariah,
custody, source/session, profitability or execution release approval. API role keys
and qualified actors are deliberately not enabled by default. No environment draft
or publication was changed.


## Milestone 7 accounts and delivery software acceptance (historical checkpoint)

The initial accounts/delivery SQLite checkpoint passed **519 tests**; lint/format,
JavaScript syntax, Chromium English/Arabic/mobile account flows, and offline
research/portfolio/mock-Gemini checks pass. The initial accounts/delivery commit
also passed [hosted PostgreSQL CI](https://github.com/MohammedTeir/halal-quant/actions/runs/41073297891).
The final rate-limit follow-up retains the global pause even when one message
exhausts its retry budget; verify that commit's hosted workflow after push.
[Acceptance evidence](../reports/milestone7-accounts-telegram-acceptance-2026-10-30.json)
separates tests from required server/BotFather configuration and real delivery.
Earlier counts above are historical checkpoints; earlier external acceptance
gates remained unchanged. Deployment acceptance was pending at that checkpoint;
see the 2026-10-31 results below.


## Milestone 7 live private-chat delivery (historical checkpoint)

The operator ran the explicitly approved, targeted setup check on Termux. Telegram
returned **SENT**, message ID **4**, in **one attempt**, and the recipient confirmed
seeing it. The disabled-destination guard first refused delivery until settings
were enabled and saved. [Delivery evidence](../reports/milestone7-telegram-delivery-2026-10-30.json)
records user-provided output and confirmation, rather than independent access to
the user's database or chat. This was one labelled setup message; no trading
signal, decision, broker fact or risk-stop event was created for it.

This closes the missing proof of one actual private-chat delivery. It does not
certify all notification types/groups live, dashboard history, deployed role and
session-revocation checks, or continuous Android hosting. Full operational
acceptance was pending at that checkpoint. Earlier milestone gates remain unchanged.


## Remaining deployed acceptance protocol (2026-10-30 checkpoint)

The [operational runbook](milestone-7-operational-acceptance.md) replaces the old
setup-only pending list. It provides disposable-account live checks, encrypted
snapshot backup plus isolated restore, supervisor/heartbeat/restart observation,
approved finite private category/language messages, separately confirmed group
linking/delivery, and a dashboard history export. At this checkpoint those checks
awaited operator outputs; preparation and CI do not count as live execution.
A successful bounded Termux observation retains Android reliability limits.


## Milestone 7 operator results: 2026-10-31

[Current evidence](../reports/milestone7-operator-acceptance-2026-10-31.json)
supersedes the historical pending lists above. The operator supplied passing live
account checks with fixture cleanup, four private SENT category/language cases,
and one group SENT result with explicit receipt confirmation. Dashboard
screenshots show verified destinations, recent worker activity and delivery history.
PostgreSQL 18 encrypted backup/isolated restore matched all 22 tables, removed the
temporary restore database, and never restored over the source. The operator then
confirmed the archive was copied off-device and its key saved separately. A
supervised restart and 60-second observation passed with five heartbeat samples.

The operator subsequently supplied the authenticated dashboard summary, confirming
all four cases, both setup histories, recent delivery activity and restart, plus
the received Arabic test message text. Milestone 7 acceptance is complete for this
documented deployment. Evidence is user-provided, not direct inspection of private
systems. No uninterrupted future uptime, unattended reboot, scheduled backup, or
provider PITR claim follows from these checks. Android can terminate Termux. Earlier
milestone source, qualified review, custody and performance gates remain unchanged;
this update does not authorize orders.
