# Campaign approval review: October 31, 2026

The user requested completing the missing calculations and approving the campaign. The technical checks and external evidence review were performed. **Approval is withheld**: the retrieved data does not support a blanket ten-company approval. No production reviewer action or database write was attempted.

## Public professional screening labels

These are reported labels observed on public pages, not independently certified stock approvals. Musaffa explicitly returned `canViewScreeningReport=false`; its detailed quantitative reports were not accessed. Its price-update date was not treated as a screening date. Zoya public stock headings and canonical pages were checked; generic FAQ text and related-company labels were not treated as the target stock's result.

| Symbol | Zoya reported label | Musaffa reported label | Review treatment |
| --- | --- | --- | --- |
| AAPL | [COMPLIANT](https://zoya.finance/stocks/aapl) | [COMPLIANT](https://musaffa.com/stock/AAPL/) | Favourable labels only; quantitative evidence incomplete |
| NVDA | [COMPLIANT](https://zoya.finance/stocks/nvda) | [COMPLIANT](https://musaffa.com/stock/NVDA/) | Favourable labels only; quantitative evidence incomplete |
| MSFT | [QUESTIONABLE](https://zoya.finance/stocks/msft) | [NON_COMPLIANT](https://musaffa.com/stock/MSFT/) | Hold: adverse/questionable source screen |
| GOOGL | [QUESTIONABLE](https://zoya.finance/stocks/googl) | [QUESTIONABLE](https://musaffa.com/stock/GOOGL/) | Hold: adverse/questionable source screen |
| AMZN | [QUESTIONABLE](https://zoya.finance/stocks/amzn) | [QUESTIONABLE](https://musaffa.com/stock/AMZN/) | Hold: adverse/questionable source screen |
| TSLA | [COMPLIANT](https://zoya.finance/stocks/tsla) | [COMPLIANT](https://musaffa.com/stock/TSLA/) | Favourable labels only; quantitative evidence incomplete |
| META | [QUESTIONABLE](https://zoya.finance/stocks/meta) | [QUESTIONABLE](https://musaffa.com/stock/META/) | Hold: adverse/questionable source screen |
| AVGO | [COMPLIANT](https://zoya.finance/stocks/avgo) | [COMPLIANT](https://musaffa.com/stock/AVGO/) | Favourable labels only; quantitative evidence incomplete |
| LLY | [COMPLIANT](https://zoya.finance/stocks/lly) | [COMPLIANT](https://musaffa.com/stock/LLY/) | Favourable labels only; quantitative evidence incomplete |
| MU | [COMPLIANT](https://zoya.finance/stocks/mu) | [COMPLIANT](https://musaffa.com/stock/MU/) | Favourable labels only; quantitative evidence incomplete |

MSFT is questionable on Zoya and non-compliant on Musaffa. GOOGL, AMZN and META are questionable on both retrieved public pages. AAPL, NVDA, TSLA, AVGO, LLY and MU have favourable public labels on both; that does not provide the missing underlying financial calculations, purification guidance or instrument attestations.

## Accounting work completed

The [calculation helpers](../scripts/paper_screening_calculations.py) reconcile current/noncurrent debt components against the reported long-term total and show differences against carrying-amount disclosures without adding overlapping totals. Three component families reconcile, two differ, and five lack sufficient component/total disclosures. An exact component reconciliation is not a complete consolidated debt mapping. Unknown short-term borrowing/lease scope and carrying-versus-face adjustments remain unresolved; no missing balance is replaced with zero.

Same-period gross interest-income components can be calculated for NVDA, AMZN and TSLA. Net investment/nonoperating income is not substituted for gross interest. These ratios cover disclosed interest only; they are not the complete non-permissible revenue numerator and do not grant a passing screen.

## Historical denominator access

The official Finnhub SDK exposes `/stock/historical-market-cap`. A bounded authenticated AAPL request for the proposed interval returned **HTTP 403**, so no series was retrieved with the configured development credential. The phone credential may have different entitlements; no subscription purchase, credential transfer or authorization bypass was attempted.

The public CompaniesMarketCap Apple page contains 57 observations in the proposed window, with a median seven-calendar-day gap. Its sampling, date conventions and units were not promoted to verified daily session coverage. No interpolation or current-share/current-cap substitution was used.

The averaging helper now validates finite positive USD observations, unique dates, exact expected session coverage and arithmetic against a separately verified calendar. The 365-day daily-capitalization result remains unavailable until an authorized complete source or evidence-backed series is supplied. Calculation software does not establish source truth.

## Approval requirements that remain

- Resolve or hold the four adverse/questionable candidates; do not mark them approved merely to finish the campaign.
- Obtain the underlying quantitative screening reports and documented business/purification review, or complete the equivalent source-backed calculations with an actual qualified methodology review.
- Obtain authorized daily historical capitalization coverage and reconcile the proposed denominator; the proposed 365-day window is not a claim about a mandatory AAOIFI window.
- Review complete debt/interest-asset mappings, instrument evidence and current methodology/policy/asset attestations through the existing role workflow.

A public compliant badge is useful supporting evidence but does not fill `FinancialScreen` fields. The existing backend requires a current qualified-methodology attestation and actual financial inputs; this work preserves that gate. User authorization to approve does not make the missing facts known. No reviewer role was impersonated and no numerical or permission gate was bypassed.

## Verification and provenance

Twelve focused screening tests pass, including six new calculation tests covering overlapping debt totals, discrepancies/missing data, date/currency scope, partial gross income, net-income exclusions and missing/duplicate/nonfinite daily-cap samples. Lint and formatting pass.

The [dated evidence report](../reports/milestone8-approval-evidence-2026-10-31.json) records public page URLs, receipt hashes, labels and partial calculations. Raw public-page snapshots remain under ignored private `data/`. No real broker orders, emails or Telegram messages were sent. No production approval, account/protocol mutation or earlier milestone acceptance was changed.
