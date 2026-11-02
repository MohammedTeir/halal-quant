# Database readiness — November 2, 2026

**The supplied database is reachable and migration `0009_paper_forward` is already applied.** The earlier development-only `DATABASE_URL_NOT_CONFIGURED` observation is no longer a reason to say the supplied database cannot be inspected. It remains separate from configuring the API/worker hosts. The [redacted inventory](../reports/milestone8-database-readiness-2026-11-02.json) records actual database observations at November 2, 19:11 UTC.

The connection was supplied through hidden input, retained in process memory only, and used with TLS-verified Neon HTTPS SQL through the managed proxy. Each query batch requested a read-only, repeatable-read transaction; PostgreSQL reported `transaction_read_only=on`. No credential, connection hostname, user email, actor identity, session token or raw protocol note appears in the inventory. No database mutation, migration, notification or order was performed. The connection was not saved as local/host configuration.

## Verified existing setup

| Requirement | Actual database observation |
| --- | --- |
| Schema | `0009_paper_forward` |
| Enabled roles | One admin, one operator, one reviewer |
| Paper account | One, mode `forward`, containing all ten candidates |
| Campaign | One, `PENDING_REVIEW`, created October 31 |
| Immutable configuration binding | Protocol account-config hash matches the observed account |
| Protocol thresholds | 20 sessions; 10 completed exits |
| Source receipts | 137 non-synthetic imports; 145 coverage rows |
| Financial/control reviews | Zero control revisions |
| Protocol review | No reviewer, review timestamp or expiry recorded |
| Upstream decisions | Zero signals, decisions and news classifications |
| Observed forward operation | Zero cycles, quotes and orders; no start or heartbeat |

The single journal record is not evidence of trading or forward acceptance. The source imports comprise 38 calendar, 32 corporate-action and 67 news batches; their latest receipt times are October 31. Import counts do not establish freshness, entitlement, complete corporate-action/earnings/FOMC coverage or a running scheduler. Zero recorded critical violations with zero cycles is not evidence of a stable run. Enabled reviewer/operator roles establish account provisioning, not qualified approval.

The public API origin configured in `vercel.json` was also checked: `https://halal-quant.onrender.com/health/ready` returned HTTP 200 with `status=ready`, and `/health/live` returned HTTP 200 with `status=ok`. This establishes basic API availability. It does not identify that API's database connection, deployed source commit, private flags, provider credentials, upstream producer configuration or worker supervision.

## Campaign methodology mismatch

The actual immutable account selects **`paper-equity-screen-proposal-v1`**, the older proposal, rather than the FTSE-assets research proposal. Its universe still includes AAPL, MU and LLY, whose later static financial failures are documented, and seven candidates lacking complete evidence. The protocol has five source-document hashes but no review. Hash presence is not a completed evidence review.

The independently reviewed account-config hash is `1d738dfb7fb9b5232d2cb3d36c42f72956babb34b599530a6385d4a644aa1419`; the pending protocol hash is `a41489138c4e310b2526d4166d9447352274387d4a42dc6286c659f04a519bc7`. These identify the existing draft, not an approved FTSE campaign. It was preserved unchanged. A different methodology or eligible subset requires a fresh isolated account/protocol through the normal operator workflow after evidence supports it, not an in-place JSON edit or direct SQL approval.

## What still has to happen

1. Obtain sufficient primary/qualified evidence to complete company eligibility. The [completion-readiness review](milestone-8-completion-readiness.md) resolves two more debt conditions but leaves the company income/business gaps in the [wider source review](milestone-8-wide-source-review.md). No candidate currently supports approval. At least one fully reviewed eligible instrument is needed; all ten do not have to pass.
2. Have the genuine reviewer assess the methodology and eligible instruments, purification/instrument evidence, campaign policy, source suitability and exact new protocol. Existing roles do not let the assistant impersonate the reviewer or invent those attestations. The current database has none of these control reviews.
3. Configure/verify the actual API and worker hosts, provider/source producers and regular-session scheduling. Refresh and validate source coverage; supply real upstream signals, classifications and decisions through their existing workflows. This database inspection does not establish host environment flags or an always-on worker. No synthetic signal was substituted for a real upstream decision.
4. After the gates pass, run the existing worker and accumulate at least 20 complete regular-market sessions and 20 actual elapsed days, the reviewed completed-exit requirement, restart/recovery evidence, no critical violations and a reconciled flat settled finish. No elapsed coverage exists in this database yet.

The [operations runbook](milestone-8-forward-operations.md) contains the existing authenticated preparation, source, preflight, worker, export and finalization commands. Migration is already satisfied; no speculative production migration or restart was needed. Actual custody and dividend receipts remain live-readiness requirements; the internal ledger checks virtual cash, holdings and settlement.

**Virtual entries remain blocked. Milestone 8 remains incomplete.** Database access has closed a configuration-discovery gap; it cannot supply missing company disclosures, independent approvals or elapsed operation.

Validation: read-only transaction status, schema revision, pending campaign state, absence of cycles/orders, and immutable config binding were checked against actual query results. **Three preflight regression tests passed**, with the existing Starlette/httpx warning. This evidence/documentation change modifies no runtime code or approval gates. Exact preceding-head Actions for `93ea660` passed 717 tests; the new pushed head is verified separately.
