# Public methodology alternative and correction

The earlier 365-day market-cap window was an unapproved research proposal. Treating historical-capitalization access as a universal prerequisite was unnecessarily restrictive. Official public methodologies offer an evidence-backed alternative: **total assets**, already available from SEC primary facts for all ten candidates. This fixes the denominator-access requirement for a separately reviewed alternative; it does not reinterpret the existing campaign.

## Sources found by public search

- [LSEG official FTSE Yasaar overview](https://www.lseg.com/en/ftse-russell/indices/global-shariah).
- [Official ground rules v4.6, February 2026](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-yasaar-global-equity-shariah-index-series-ground-rules.pdf), sections 4.3.1–4.4 and periodic review provisions.
- [Published Yasaar endorsement](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/other/ftse-yasaar-shariah-global-equity-index-series-fatwa.pdf), dated February 3, 2025. This endorses the named index methodology; it does not certify this project, its implementation or every stock.
- [Zoya's public methodology explanation](https://help.zoya.finance/en/articles/4189798-how-does-zoya-screen-stocks-for-shariah-compliance) and [methodology comparison](https://blog.zoya.finance/introducing-more-ways-to-screen-for-shariah-compliance-in-zoya/). These describe different denominators and explicitly distinguish independent interpretations from official index determinations.

Receipt hashes are recorded in the [evidence report](../reports/milestone8-public-methodology-alternative-2026-10-31.json). Source PDFs/HTML are archived privately under ignored `data/`; access did not require a subscription or authentication.

## Implemented financial-core support

| Financial condition | Denominator | Boundary |
| --- | --- | --- |
| Debt | Total assets | Strictly below 33.333% |
| Cash plus interest-bearing items | Total assets | Strictly below 33.333% |
| Accounts receivable plus cash | Total assets | Strictly below 50% |
| Total interest and non-compliant activity income | Total revenue | At or below 5% |

The backend now supports an explicit receivables/cash threshold and input, plus a separate income boundary. Missing the fourth input prevents an APPROVED asset submission. The 5% inclusive income rule does not change strict limits for debt, interest items or liquidity. Old methodology/request serialization excludes the new unused fields, preserving existing request hashes and old strict rules.

The generic `interest_assets` input must represent **cash plus interest-bearing items** for this proposal; it cannot be filled with securities alone. A positive gross interest component is only part of total non-compliant income. No field is set to zero just because the source lacks it.

This implements the published **static financial core only**. Official constituent universe rules, quarterly state/buffers, business classifications, source mappings, qualified approvals and index licensing/replication are not inferred. In particular, the published two-successive-quarter monitoring/buffer process is not implemented as an automatic index-membership decision. The proposal remains PENDING.

## Primary financial inputs obtained

Same-issuer, same-filing SEC assets/cash/receivables facts were checked against the archived receipt hashes. Total assets are available for all candidates:

| Candidate | Reported total assets, USD | Date of financial period end |
| --- | ---: | --- |
| AAPL | 383,266,000,000 | 2026-06-27 |
| NVDA | 320,272,000,000 | 2026-07-26 |
| MSFT | 779,403,000,000 | 2026-09-30 |
| GOOGL | 1,003,312,000,000 | 2026-09-30 |
| AMZN | 1,243,390,000,000 | 2026-09-30 |
| TSLA | 157,517,000,000 | 2026-09-30 |
| META | 478,836,000,000 | 2026-09-30 |
| AVGO | 188,148,000,000 | 2026-08-02 |
| LLY | 148,072,000,000 | 2026-09-30 |
| MU | 195,888,000,000 | 2026-09-03 |

The report computes known-component lower bounds for the financial conditions. None of these partial bounds establishes a complete pass. They are not a consolidated debt/interest mapping or an income/business approval. Other-provider public labels are not silently treated as FTSE-method results; different standards can produce different outcomes.

## Separate pending draft

The [proposal](../examples/controls/ftse-assets-methodology-proposal.json) is PENDING, binds the official ground-rules receipt hash and records implementation limits. Preparation accepts an explicit alternative method and requires a fresh account ID. Existing drafts are hash-checked, conflicting options fail, and the old account/protocol are not edited.

Prepare locally without provider calls, approval or database mutation:

```sh
.venv/bin/python -m services.paper.prepare --output data/paper-assets-setup --methodology-proposal examples/controls/ftse-assets-methodology-proposal.json --account-id largecap-assets-forward-20261031
```

Only an explicit `--submit` adds ordinary operator-authenticated account/protocol proposal submission; it still creates no methodology or asset approval. Do not submit an alternative merely to bypass an unresolved business/financial review.

## Evidence and acceptance boundary

Public research can close the denominator-source gap without paid historical capitalization. It has not yet established complete non-compliant business revenue, purification applicability, financial mappings, instrument evidence or qualified per-company approval. The adverse/questionable public screens for MSFT, GOOGL, AMZN and META remain unresolved. Changing a formula does not turn them into approved candidates.

Local verification passed **684 tests with two PostgreSQL-only checks skipped**, including 67 focused controls/paper/API checks. Tests prove missing-input rejection, independent income/liquidity boundaries, legacy serialization, and isolated alternative preparation. Lint/format pass. No production approval, credential/cloud-configuration publication, external order, email or Telegram send occurred. Earlier milestone acceptance and the actual elapsed forward-test requirement remain open as documented.
