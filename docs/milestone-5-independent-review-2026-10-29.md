# Milestone 5 independent technical review — 2026-10-29

**Final verdict: accept the bounded research workflow after correction and
independent recheck of six recorded software findings, including the later
author-identified temporal race. No execution-release approval.**

This is a separate AI-agent code/evidence review of the stored controls workflow,
not human, scholarly, institutional, custody or broker execution approval. The
reviewer did not implement these controls. No network/provider calls, credentials,
cloud configuration, orders, commits or pushes were used by this reviewer.

Final disposition and reviewed file hashes are recorded in
[the machine-readable review](../reports/milestone5-independent-review-2026-10-29.json).
The reviewer independently rechecked the final code and new regression cases,
validated the stable-methodology withdrawal contract and rejected a non-New-York
operational policy in an offline pure-contract check. The implementation author
reported 43 focused passing tests (32 operations API + 11 broker); the reviewer did
not rerun the full suite or independently repeat live broker calls.

The scope is role-attested research controls, read-only captures, simulation holds
and decision-time revalidation. It excludes a live/paper order executor, broker
fill/cancel ledger, verified settled-cash/custody contracts and an actual fatwa.

## Findings raised during review

1. **M5-IR-01 — Medium: a stop leg did not establish protection merely by type/price.**
   Pending-buy logic initially accepted canceled/rejected, wrong-symbol or undersized
   stop legs as known risk. Existing-position logic also needed an explicit SELL-side
   check for child legs. Require active accepted/new/partially-filled SELL stops,
   same symbol and sufficient remaining quantity. Otherwise retain unknown risk and
   block entries. The author implemented SELL/us_equity/status/symbol/remaining-quantity filters;
   the reviewer independently inspected those filters and corresponding regression
   cases. **Resolved and reviewed.**
2. **M5-IR-02 — Medium: risk-day scope could disagree with captured activity scope.**
   Broker activity capture starts at New York midnight, while policies initially
   allowed another loss-day timezone without proving the corresponding history.
   The author restricted stored operational policies to New York, retained the
   captured activity day/window and rejects day mismatches. Arbitrary timezone
   hypothetical previews do not become operational evidence. **Resolved and reviewed.**
3. **M5-IR-03 — Medium: revalidation needed the same serialization boundary as writers.**
   Multiple decision-time control reads initially did not acquire the global
   controls lock, allowing concurrent revocation/kill/release to interleave under
   PostgreSQL READ COMMITTED. The author now takes the lock before the first
   decision database read whenever a control-check reference is supplied. The
   reviewer inspected that pre-read lock and the shared writer boundary. **Resolved
   and reviewed.**
4. **M5-IR-04 — Medium: immutable methodology IDs initially lacked withdrawal scope.**
   A new methodology record initially defined a different identity instead of
   revoking an older applicable approval. The author added a stable methodology ID,
   unique revision record ID and APPROVED/PENDING/REVOKED status. Current asset
   approval/revalidation must see the latest effective APPROVED methodology and
   the precise reviewed revision; expired/revoked revisions cannot borrow old approval. The reviewer independently
   exercised the stable-scope/new-record withdrawal contract. **Resolved and reviewed.**
5. **M5-IR-05 — Medium: pending broker orders needed explicit admissibility checks.**
   Unsupported instrument orders or unowned pending SELLs initially could be omitted
   from risk/exposure restrictions. The author retained broker order asset class and
   added fail-closed checks for unsupported/unknown root orders and owned-quantity
   coverage; these code paths and their regressions were independently inspected.
   **Resolved and reviewed for that bounded scope.**
   Nested OCO/bracket compatibility and atomic execution reconciliation remain
   bounded assumptions, not a demonstrated broker order lifecycle.

No result above ever granted execution: the engine and control responses retain
`authorized=false`. The findings concern correctness of research-control passes
and future authority boundaries; current Alpaca buys remain blocked by unavailable
cash/lending/borrowing contract proof.

## Boundaries that were checked

- Reviewer, operator, broker-reader, analyst and dashboard routes have separate
  headers/capabilities; nonempty keys must differ. The server supplies actor and
  receipt time rather than accepting those authorities from request bodies.
- Reviewer records carry immutable request IDs/hashes and effect/expiry windows.
  Latest effective revisions, including rejected/expired tombstones, are selected
  without falling back to older approval. Future-effective records are not current.
- Broker/quote API requests accept refresh IDs/symbols, not caller URLs, balances,
  holdings, settled cash or truth flags. Capture claims commit before bounded
  fixed-host GET requests; failures/RUNNING claims are not automatically recalled.
- Latest failed or ambiguous captures block old success fallback. Current captures
  require observed/completed times available at evaluation and configured freshness.
- Shared capacity checks/reviews/releases are serialized. Holds are short, bounded
  by source/review expiry, exclude their own quantity when revalidated, cannot be
  renewed by replay, and are explicitly simulations rather than broker orders.
- Entry kill/compliance/cash checks do not themselves prevent a fresh, whole-quantity
  owned-exit candidate. Available ownership still accounts for current broker sell
  demand and research reservations. It does not grant permission to sell beyond
  owned availability or to cancel/rearrange live protective orders.
- Primary decision evaluation preserves the unavailable market-data authority and
  rejects mismatched signal/check references. A passing control check cannot supply
  execution authority or turn the configured real Alpaca contract flags true.

## Live evidence and retained limits

Sanitized evidence records successful read-only paper account and IEX quote probes.
The observed account had **zero positions and zero open orders**. Cash-account,
settled-cash, lending-disabled and borrowing-disabled verification flags were all
false. Thus endpoint compatibility is established for that sample; actual owned
sellability, OCO fills, trade settlement, custody and real order lifecycle are not.

Reviewer credentials/identity strings are application attestations, not external
verification of a named scholar's qualifications or financial-statement truth.
Financial screens validate supplied figures against the selected explicit rules;
they do not independently audit filings or choose a religious methodology.
Review scope uses symbol/class; immutable asset-ID/corporate-action continuity
needs consideration before any execution release.

Repeated broker position fields are not an atomic cash/order/fill snapshot.
Loss-state reconciliation remains a reviewer-attested current-day workflow bound
to a captured activity set, not a complete FIFO/settled-cash execution ledger.
Mature paper/live trading still requires Milestone 8/9 reconciliation and explicit
qualified instrument/account/source approvals. Every report remains non-authorizing.


## M5-IR-06 — Author-identified temporal race, resolved and independently rechecked

After the initial review, the implementation author identified a further race:
a timestamp sampled before waiting for the global lock could exclude another
writer's reservation or kill/revocation committed while this request waited.
Serialization must use authoritative server time sampled after acquiring the lock.
The author added fresh `utcnow()` sampling immediately after the shared lock in
review, kill-switch changes, capacity reservation and release. Linked current
`store_evaluation` also refreshes time after the lock and before its first DB read
or default cutoff. The reviewer independently inspected all five paths and the
new deterministic pre-lock-time reservation/kill regression cases. The author
reported **35 passing operations tests** for the updated code; this reviewer did
not independently execute those tests. Explicit `request.as_of` still requests
historical research and is not promoted to current execution authority.

**M5-IR-06 is resolved and independently code-reviewed.** The JSON retains the
prior hashes of the three changed files and pins their re-reviewed hashes. Other
reviewed hashes remain unchanged. This relies on the server's trusted coherent UTC
clock and does not make broker observations atomic or authorize an order.


## Local capture confidentiality follow-up

The author subsequently wrapped settings/database setup, broker capture/read and
sanitized report output in the CLI's expected-error boundary. The reviewer inspected
the two changed files: `services/controls/acquire_broker.py` and
`tests/controls/test_broker.py`. Expected SQLAlchemy/validation/filesystem/broker
errors now exit with a constant generic message rather than interpolating private
exception details into an unhandled traceback. Engine cleanup remains present;
state, read-only operation and `authorized=false` semantics are unchanged.

The added regression injects private database error text and checks that it is not
printed and no report is written. This reviewer inspected that regression and did
not independently execute it. The JSON preserves the two prior hashes and pins
the re-reviewed hashes. This hardening is accepted for the declared expected-error
scope, with the existing six findings remaining resolved and no execution release.
