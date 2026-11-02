# Independent filing review: November 2, 2026

All ten candidates remain **NOT_APPROVED**, with no virtual entries authorized. This continues the independent review selected by the user; it does not complete financial or business screening.

## Workspace recovery and evidence

The old offline checkout `/workspace/halal-quant` was left intact at `9991fcf` on branch `work`, including its ignored data and environment. Work continued in a separate checkout, `/workspace/halal-quant-main`, on `main` from the confirmed remote commit. Neither the named uncommitted `scripts/paper_filing_facts.py` nor its tests was found in the accessible workspace or scratch/shared directories. They were reimplemented; this is not a claim of byte-for-byte recovery or recovery from an unavailable machine.

Read-only SEC submissions and the latest eligible financial filing were retrieved for each issuer. The [dated report](../reports/milestone8-filing-facts-2026-11-02.json) records filing identifiers, source URLs, SHA-256 receipts, selected unaggregated numeric facts and business-search excerpts. Raw documents and the full inventory of **11,105 numeric fact occurrences** remain under ignored `data/filing-review-20261102/`. Occurrences include comparative, dimensional and repeated facts; they are not 11,105 independent consolidated inputs. The current filing identifiers match the prior October 31 review; no newer eligible filing was found in the retrieved recent-submissions lists.

The [extractor](../scripts/paper_filing_facts.py) preserves custom concepts, context dates, entity identifiers, dimension attributes/member values, units, source text and decimals. Supported dot-decimal values apply scale and sign without using floating point. Unknown transforms, nil/nonfinite values and missing context/unit references stay unknown. It does not aggregate overlapping facts, certify completeness or implement a general XBRL validator. Text searches are research leads; absent keywords do not prove absence of prohibited revenue. Quarterly filings also do not replace the annual business description and material subsequent disclosures.

## Candidate findings and next review

| Candidate | Numeric occurrences | Independent review finding / unresolved work |
| --- | ---: | --- |
| AAPL | 762 | Current/noncurrent securities and individual instrument contexts are available. Classify instruments without treating all securities as interest-bearing; map services/advertising/content revenue. |
| NVDA | 1,002 | Gross interest has separate quarter and year-to-date contexts. Graphics includes gaming/PC and workstation GPUs; assess actual activities rather than equating gaming hardware with gambling. |
| MSFT | 1,044 | Net investment income does not establish gross interest. Assess gaming/content and other activities; prior adverse/questionable public labels remain unresolved. |
| GOOGL | 1,829 | `InterestIncomeOther` was outside the older selected-concept whitelist. Review its definition and periods before using it. Advertising/content revenue and prior questionable labels require resolution. |
| AMZN | 1,302 | Separate quarter/year-to-date gross interest is available. Reconcile borrowing/lease scope and retail commissions, subscriptions, advertising and media income. Prior questionable labels remain unresolved. |
| TSLA | 1,137 | Gross interest and custom lease/cash-flow interest concepts coexist; do not add them blindly. Assess financing/leasing/insurance income alongside automotive/energy. |
| META | 910 | No separately named gross-interest numeric tag found. Obtain note-level gross income evidence and assess advertising/content revenue; prior questionable labels remain unresolved. |
| AVGO | 1,082 | Current/noncurrent long-term debt components reconcile to the reported total; full screening debt and interest assets still need mapping. Document semiconductor/software activity review. |
| LLY | 783 | Current debt and noncurrent long-term debt are disclosed. Complete debt/investment and pharmaceutical/licensing reviews; litigation/insurance word matches do not establish insurance business revenue. |
| MU | 1,254 | Net investment income cannot fill gross interest. Review investment/debt notes and memory business activities; gaming hardware references do not establish gambling revenue. The earlier corporate-action issue also remains open. |

Every candidate still needs complete same-period debt, cash plus interest-bearing items, receivables/cash and total non-compliant-income mappings, with source definitions and no overlapping totals. Business revenue classification, purification/disposition, instrument evidence and actual qualified methodology/asset review remain pending. The separate total-assets alternative remains a pending proposal. No approved company, methodology, campaign or elapsed forward session is inferred.

## Reproduction and validation

```sh
uv run python -m scripts.paper_filing_facts --archive data/filing-review-NEW --cutoff 2026-11-02
uv run pytest -q tests/paper/test_filing_facts.py
```

Use a new archive directory; existing archives are refused. The ten focused cases cover scaled/signed custom facts with dimensional periods, nil/nonfinite/unsupported values, missing units, overlapping occurrences, all-ten mocked GET-only acquisition, unavailable sources and archive preservation. The extractor makes no application database connections, broker requests, email sends or Telegram calls. No credentials were published. No production review or campaign state was changed.

Local regression verification completed with **694 passed, 2 PostgreSQL-only checks skipped**, and one existing Starlette/httpx deprecation warning. All ten focused extractor tests pass; repository lint, formatting and diff whitespace checks pass. These software checks do not grant screening approval or Milestone 8 acceptance.


## Explicit screening outcomes and context/duplicate checks

The follow-up evaluates existing archived filings without changing their receipt hashes or the original observation timestamp. `outcomes_evaluated_at` records the later inventory evaluation. Exact-context lookups for assets, cash and current receivables succeeded for all ten companies using the filing's period-end, issuer CIK, USD unit and undimensioned scope. Identical repeated disclosures count as one value, not an additive total. This verifies selection from the inventory, not independent completeness or accounting classification.

| Candidate | Financial review | Business review | Overall screening outcome |
| --- | --- | --- | --- |
| AAPL | Insufficient evidence | Insufficient evidence | Insufficient evidence |
| NVDA | Insufficient evidence | Insufficient evidence | Insufficient evidence |
| MSFT | Insufficient evidence | Insufficient evidence | Insufficient evidence |
| GOOGL | Insufficient evidence | Insufficient evidence | Insufficient evidence |
| AMZN | Insufficient evidence | Insufficient evidence | Insufficient evidence |
| TSLA | Insufficient evidence | Insufficient evidence | Insufficient evidence |
| META | Insufficient evidence | Insufficient evidence | Insufficient evidence |
| AVGO | Insufficient evidence | Insufficient evidence | Insufficient evidence |
| LLY | Insufficient evidence | Insufficient evidence | Insufficient evidence |
| MU | Insufficient evidence | Insufficient evidence | Insufficient evidence |

The per-company findings above explain the outstanding work. No complete independent pass or fail determination is established by this inventory. Prior adverse/questionable third-party labels remain unresolved supporting evidence; they are not silently converted into an independent determination. All approvals remain withheld and all virtual entries remain blocked until full financial and business screening and the existing review gates support approval. This research script does not submit reviews or alter the deployed campaign.

The selector requires exact instantaneous or duration dates, issuer, unit and explicit dimensions. It excludes typed dimensions it cannot interpret, rejects reversed request periods, and never substitutes a quarter for year-to-date, one currency for another, shares for money, or a segment for the consolidated issuer. Missing/unsupported values remain unknown, including when an otherwise matching duplicate has a missing value. Conflicting duplicate values return insufficient evidence; conflicting context/unit ID definitions reject the document instead of silently overwriting its definitions. Numeric zero remains distinct from missing data. This remains a bounded inventory helper, not a complete XBRL validator.

The focused screening regression checks pass **30 tests**, including **17 filing-extractor cases** covering periods, USD/EUR/share units, issuers, explicit/typed dimensions, instant/duration distinctions, missing contexts/units, empty/nil/nonfinite values, identical/conflicting/missing duplicate facts and conflicting context/unit definitions.

Follow-up full regression result: **701 passed, 2 PostgreSQL-only checks skipped**, with the existing Starlette/httpx deprecation warning. Repository lint, formatting, report-consistency and diff checks pass. No deployed approvals, campaign state, virtual entries or real messaging were changed by this follow-up.


## Subsequent substantive company review

The [independent company review](milestone-8-independent-company-review.md) supersedes the inventory-only outcome table for current research findings. It applies one explicit FTSE Yasaar v4.6 static methodology, reconciles debt/lease/investment families, finds static financial breaches for AAPL, LLY and MU, and records precise unresolved income/business facts for the remaining candidates. Meta gross interest and Micron's statement-labelled gross interest were found by reading the documents; Microsoft's interest/dividend line was distinguished from an interest-only amount. No complete company pass or approval is inferred. GitHub Actions for `baed1f1` was verified successful with 703 PostgreSQL tests.


Ownership scope clarification: the internal simulator verifies virtual cash, holdings and simulated settlement through its ledger. Real custody and actual dividend receipts belong to live-readiness review, not virtual-entry prerequisites. Full independent financial and business screening remains required before virtual entries. See the updated substantive review for commit-specific CI verification and the separated scopes.
