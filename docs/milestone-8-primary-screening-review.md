# Primary-source screening review: October 31, 2026

The user authorized starting the ten-company evidence review. This checkpoint is technical research: no stock, methodology, source completeness or campaign was approved. The deployed protocol/account remain unchanged.

## Results

SEC submissions and XBRL company facts were obtained for all ten companies. Forty selected historical financial values matched exactly by accession, reporting period, currency and value; four selected values were not covered by an exact SEC company-fact match. None of the covered comparisons was a mismatch. These are selected value checks, not a complete financial-statement reconciliation.

Nine companies have newer quarterly filings than the annual provider snapshot. The current-review inventory therefore also records 81 selected balance-sheet and quarterly/annual income disclosures from the latest financial filing in the fetched SEC recent-submissions list, including amendments when present. They remain separate line items: totals and components can overlap.

| Stock | Latest SEC financial form | Filing date | Selected latest disclosures | Historical exact matches | Historical unavailable matches |
| --- | --- | --- | ---: | ---: | ---: |
| AAPL | [10-Q](https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm) | 2026-07-31 | 9 | 7 | 0 |
| NVDA | [10-Q](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000075/nvda-20260726.htm) | 2026-08-26 | 8 | 5 | 1 |
| MSFT | [10-Q](https://www.sec.gov/Archives/edgar/data/789019/000119312526436133/msft-20260930.htm) | 2026-10-28 | 12 | 0 | 1 |
| GOOGL | [10-Q](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000084/goog-20260930.htm) | 2026-10-29 | 10 | 5 | 0 |
| AMZN | [10-Q](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000040/amzn-20260930.htm) | 2026-10-30 | 11 | 5 | 0 |
| TSLA | [10-Q](https://www.sec.gov/Archives/edgar/data/1318605/000162828026066775/tsla-20260930.htm) | 2026-10-22 | 7 | 4 | 2 |
| META | [10-Q](https://www.sec.gov/Archives/edgar/data/1326801/000162828026066773/meta-20260930.htm) | 2026-10-22 | 7 | 4 | 0 |
| AVGO | [10-Q](https://www.sec.gov/Archives/edgar/data/1730168/000173016826000080/avgo-20260802.htm) | 2026-09-10 | 7 | 4 | 0 |
| LLY | [10-Q](https://www.sec.gov/Archives/edgar/data/59478/000005947826000108/lly-20260930.htm) | 2026-10-29 | 5 | 4 | 0 |
| MU | [10-K](https://www.sec.gov/Archives/edgar/data/723125/000072312526000023/mu-20260903.htm) | 2026-10-09 | 5 | 2 | 0 |

Microsoft's provider annual balance-sheet list was empty; the SEC current-period inventory supplies disclosed balance-sheet candidates without inventing zero balances. Cash-flow borrowing proceeds were excluded from debt balances. Noncontrolling-interest lines were excluded from interest-income candidates. Income periods are separated so year-to-date income is not mistaken for one quarter.

## Proposed denominator window

For review, the draft now proposes a 365-calendar-day interval from **October 31, 2025 through October 30, 2026**, averaging actual closing market capitalizations over verified regular trading sessions. This is a research proposal, not a claim that AAOIFI mandates this window. Historical share counts and corporate actions must be sourced; multiplying all historical prices by today's share count is not accepted as actual historical capitalization. The required series has not been collected or validated, and this proposal has not changed any immutable campaign record.

## Remaining decision gates

The reviewed consolidated debt/interest-bearing-asset mapping, historical denominator series, non-permissible revenue calculation, business activity assessment, purification/disposition instructions and instrument evidence are still missing. A disclosed net investment/nonoperating-income item is not a complete gross non-permissible-revenue numerator. Missing disclosures remain unknown.

Keep the campaign pending. No `AssetApproval`, methodology approval or protocol review was submitted. The earlier qualified compliance/source/performance milestones remain in their documented state, and actual elapsed forward acceptance is not established.

## Reproduction and verification

The [JSON review](../reports/milestone8-screening-review-2026-10-31.json) records source receipts, selected facts, filing identifiers and the proposed window. Raw source archives remain under ignored private `data/`. The [review script](../scripts/paper_screening_review.py) validates the original provider-response hashes before reading SEC data. Run it with explicit source and new output archive paths; it never connects to the application database or orders API.

Six focused tests pass for exact accession/period/unit matching, missing disclosures, conflicting values, future filings, separate debt components and income durations, and a complete mocked SEC acquisition that grants no approval. Lint/format pass. Live SEC probes used GET requests only. No production database changes, real orders, emails or Telegram messages occurred.

[Hosted CI](https://github.com/MohammedTeir/halal-quant/actions/runs/41227037508) passed **673 tests** on PostgreSQL for source `e8b35f7`, including the encrypted backup/isolated restore and existing offline acceptance steps. These checks establish software regression status, not stock approval or forward acceptance.

## Approval request follow-up

The [approval evidence review](milestone-8-approval-review.md) implements partial financial reconciliations and daily-cap averaging checks, records four adverse/questionable public screening results, and documents the historical-data/report access limitations. Approval remains withheld; no missing facts or permissions were bypassed.
