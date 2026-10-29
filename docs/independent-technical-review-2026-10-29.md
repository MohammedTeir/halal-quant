# Independent technical source and policy review — 2026-10-29

**Verdict: conditional acceptance for the stated research/advisory scope; no
production, trading, certified gold-session or blanket publisher-authority approval.**
This completes the separate AI technical review the user selected. The reviewer was
`/root/independent_source_policy_review`, separate from the implementation-author
agent and the project's Gemini classifier. This is **not a human, legal, financial,
Shariah or institutional audit**. The reviewer inherited project context and saw
prior model outcomes; neither blind review nor independent model-family/statistical
independence is claimed.

The base reviewed commit was `56b2b2e`, plus the working-tree gold comparator and
its subsequent corrections. [The machine-readable review](../reports/independent-technical-review-2026-10-29.json)
records exact inspected file hashes, findings and scope. Changes after those hashes
need their own assessment. No Gemini/provider call, secret/config edit, order,
publication or Git push was performed by this reviewer.

## What was independently checked

- Read the actual Finnhub adapter, immutable event/assessment storage, Gemini claim
  and revalidation flow, strict schemas/evidence validation, feed coverage, policy
  restrictions and server decision construction.
- Inspected the actual retained Finnhub observations, not just a synthetic fixture.
  The two archives contain the same 108-event AAPL distribution; they are not 216
  independently corroborated observations.
- Reconstructed the fixed external sample from the pinned original FinancialPhraseBank
  archive and original labels. Recounted **30/30** correct sentiments, ten per class.
- Recounted v5 primary/adversarial results directly from retained outputs: **16/16**
  regression with **8/8** safe attack policies, and **8/8** fresh pilot with **4/4**
  safe attack policies. Verified **12/12** latest real-source HTML/excerpt hashes.
- Reviewed the gold comparison and source snapshot. Confirmed the corrected parser
  accepts the actual XAU/USD table rule and rejects an altered `18:06` rule.
- Reviewed the corrected current provider table. The full suite is run by the
  implementation author/CI; this reviewer did not independently rerun every
  historical acceptance test or authenticate historical network traffic.

Hashes and local timestamps bind retained artifacts; they are not independent
cryptographic attestations of publisher truth, provider traffic or the moment at
which labels were first frozen.

## Source suitability

| Source | Narrow disposition | Important limit |
|---|---|---|
| Federal Reserve direct calendar/releases | Accept for its own calendar/statements under recorded provenance | Not a complete economic calendar; dates/receipt do not establish predictable gold returns or historical availability. |
| BLS direct calendar/releases | Accept for its own scheduled releases/statements under recorded provenance | Current retrieval is not a historical vintage archive; it does not provide all macro/FOMC/earnings events. |
| Issuer releases, including Apple | Conditional primary-claim/advisory use | Issuer promotional framing and financial statements are not independently audited by this project; no return/compliance approval. |
| Finnhub company news/earnings | Conditional intermediary/advisory ingestion only | Actual wrapper URLs/source-name claims do not establish original publisher identity, credibility, permitted reuse or comprehensive target coverage. |
| Alpaca IEX candles/actions | Conditional demonstrated research input | IEX volume/coverage is not consolidated US market liquidity; sample split/session arithmetic does not certify a complete historical action ledger. |
| HistData XAUUSD bid quotes | Conditional structural research input with full provenance/gap flags | Missing volume, unknown quote venue and unresolved session/holiday binding prevent certified research-release/execution claims. |
| OANDA BVI metals-CFD hours | Accept as explicitly labeled diagnostic reference | Current CFD hours are not HistData's source-bound historical schedule and do not approve CFDs, margin or Shariah suitability. |
| FinancialPhraseBank all-agree | Accept for declared noncommercial research sentiment benchmark | Old Helsinki distribution; possible pretraining overlap; no independent event/policy/attack labels or project human sign-off; retain license/README terms. |
| Gemini v5 | Conditional advisory classifier only | Exact schema/citations and diagnostic scores do not verify every assertion, calibrate confidence or authorize action. |

## Findings and required dispositions

**ITR-01 — Medium, open before source-authority release: Finnhub publisher identity
is not independently established.** The retained sample reports Yahoo 86, CNBC 8,
Benzinga 12 and SeekingAlpha 2, but **all 108 URL hosts are `finnhub.io`**. The adapter
copies provider `source` and `url` metadata
([adapter](../services/news_intelligence/providers/finnhub.py):72–79). A known
aggregator's delivery is not equivalent to verified editorial identity for every
underlying article. Preserve intermediary attribution; establish original publisher
URLs/content, permitted use and target coverage before any source-authority promotion.
Do not set source verification true merely because these familiar names occur.

**ITR-02 — Medium, open before gold session certification: no matching historical
source/venue schedule.** The comparator finds 353,940 observed minutes and 300 absent
runs. Against its current regular-hours reference, 14,133 absent minutes fall during
reference-open time, 157,527 during reference-closed time, and 9,459 observed minutes
fall during reference-closed time. These differences do **not** identify true data
loss or true market closure: holidays, quote activity, venue, effective history and
minute-boundary interpretation remain unknown. Its decision to keep every gap
unverified, expose mismatches and return a non-certifying exit status is appropriate.
Obtain source-bound 2025 regular/holiday/exception evidence or a separately assessed
replacement source. Do not infer a daylight-saving correction from apparent patterns.

**ITR-03 — Medium, open before deployed-policy/accuracy claims: sampled agreement is
not policy validation or confidence calibration.** External human sentiment labels
are genuine evidence within their scope, but the benchmark deliberately permits all
event/policy labels and contains no attacks
([benchmark](../services/news_intelligence/external_benchmark.py):64–67). Author-labeled
primary pilots do not become independent policy ground truth because they pass.
The default confidence/relevance/score thresholds and fixed event windows
([policy](../services/decision_engine/policies.py):14–23) are provisional conservative
engineering rules, without demonstrated production calibration or performance.
Before deployment, define representative US/ETF/gold/source-conflict/correction
cases and independent expected policy decisions, then assess failure severity and
calibration on point-in-time histories. This does not block development of Milestone 5.

**ITR-04 — Low, known limitation: exact quotes establish structural grounding, not
semantic truth.** [Quote validation](../services/news_intelligence/classification.py):61–81
checks membership/scope, not whether every sentiment/severity/impact assertion follows
from the evidence. Keep output advisory and include semantic evidence review in
quality evaluation. No automatic source-authority or truth approval follows.

**ITR-05 — Low, resolved during review: rule-to-snapshot binding.** Initially the
comparator checked an HTML hash/status but supplied hardcoded hours without checking
the snapshot's table. The implementation author added
[exact rule verification](../services/market_data/gold_sessions.py):48–55, bounded
fixed-URL acquisition and verification before comparison. The reviewer independently
confirmed acceptance of the actual row and rejection of an altered rule. This fixes
reproducible extraction; it does not establish historical/HistData venue equivalence.

**ITR-06 — Low, resolved during review: obsolete current provider-table claims.** The
current table originally called FOMC acquisition unimplemented and gold selection
unresolved. The reviewer confirmed the corrected
[provider table](data-providers.md) now distinguishes implemented FOMC/actions and
conditional gold reference data. Historical failure reports remain unchanged.

## Policy assessment and authorization boundary

The documented deterministic restrictions are suitable for conservative research
when treated as provisional rules. The parser forbids privileged extra fields,
duplicate JSON keys and nonfinite values; generation pins targets and rechecks source
revisions after inference. Local revision/receipt handling avoids backdating known
corrections into historical availability.

The reviewed source/feed and authority gates remain fail-closed:
[coverage](../services/market_data/coverage.py):70 always leaves provider verification
false; [server evaluation](../services/decision_engine/store.py):189–191 constructs
missing trusted authorities instead of accepting client/model approvals; and
[engine](../services/decision_engine/engine.py):55–61 always returns `authorized=false`.
Model ALLOW therefore cannot supply source, compliance, broker, risk or ownership
approval. No immediate order-authorization bypass was found in these reviewed paths.
This finding is bounded to inspected code, not a whole-system security certification.

The separate AI technical review is complete with **conditional research-only
acceptance**. Human project approval, certified gold closures, representative
production quality, licensing approval for deployment, research profitability and
Shariah/execution approval remain ungranted. A perfect diagnostic score must not be
used to remove the open release conditions above.
